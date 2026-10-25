"""Main orchestration pipeline for Daily Intelligence Digest."""
import argparse
from datetime import datetime, timezone
from dataclasses import asdict
from typing import Dict, Any, List

from app.config import settings
from app.news.collector import collect_news
from app.jobs.collector import collect_jobs
from app.processing.categorizer import categorize
from app.processing.credibility import score_source, label_score, is_developing_story
from app.processing.deduplicator import deduplicate, content_hash
from app.processing.ranking import rank_news, filter_jobs
from app.ai.summarizer import summarize_news, summarize_jobs
from app.database.database import Database
from app.email.renderer import render_digest, format_digest_date
from app.email.sender import send_email

def serialize_item(item) -> Dict[str, Any]:
    """Safely convert dataclass item with datetimes to JSON-serializable dictionary."""
    d = asdict(item)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d

def run(dry_run: bool = False, force_send: bool = False):
    print("[INFO] ========================================================")
    print("[INFO] Starting Daily Intelligence Digest Pipeline")
    print(f"[INFO] Mode: {'DRY RUN' if dry_run else 'PRODUCTION EXECUTION'}")
    
    date_info = format_digest_date()
    print(f"[INFO] Digest Date: {date_info['full_date']} ({date_info['time_pkt']})")
    
    # 1. Collect news
    print("[INFO] Collecting news from configured RSS feeds and APIs...")
    raw_news = collect_news(settings)
    print(f"[INFO] Total raw news items collected: {len(raw_news)}")

    # 2. Categorize and score credibility
    for x in raw_news:
        x.category = categorize(x.title, x.description)
        x.is_developing = is_developing_story(x.title, x.description)
        x.credibility_score = score_source(x.source, x.url, x.is_developing, x.corroboration_count)
        x.credibility_label = label_score(x.credibility_score, x.is_developing)

    # 3. Deduplicate
    unique_news = deduplicate(raw_news)
    print(f"[INFO] Deduplicated to {len(unique_news)} distinct stories.")

    # 4. Filter by minimum credibility and rank
    qualified_news = [x for x in unique_news if x.credibility_score >= settings.min_credibility_score]
    ranked_news = rank_news(qualified_news)
    top_stories = ranked_news[:settings.top_stories_count]

    # 5. Collect and score jobs
    print("[INFO] Collecting entry-level computing & software engineering jobs...")
    raw_jobs = collect_jobs(settings)
    for j in raw_jobs:
        j.content_hash = content_hash(f"{j.title} {j.company}", j.url)
    filtered_jobs = filter_jobs(raw_jobs)
    print(f"[INFO] Qualified {len(filtered_jobs)} matching entry-level/intern opportunities.")

    # 7. Database deduplication and history ledger
    db = Database(settings.database_path)
    new_news = [x for x in ranked_news if not db.already_sent(x.content_hash)]
    new_jobs = [j for j in filtered_jobs if not db.already_sent(j.content_hash)]
    
    # If in dry run or force_send, allow all current items so preview is rich
    candidate_news = ranked_news if (dry_run or force_send) else new_news
    display_jobs = filtered_jobs if (dry_run or force_send) else new_jobs
    display_top = top_stories if (dry_run or force_send) else [x for x in top_stories if not db.already_sent(x.content_hash)]

    # Filter strictly for Pakistan news
    # Require category == 'Pakistan' or 'pakistan' in text/source region
    pakistan_candidates = [
        x for x in candidate_news
        if x.category == "Pakistan" or "pakistan" in f"{x.title} {x.description} {x.source}".lower()
    ]

    # Rank and select top 5 to 10 Pakistan stories (minimum 5 if enough exist, capped at 10)
    # If fewer than 5 exist, take all genuine Pakistan stories found
    if len(pakistan_candidates) >= 10:
        display_news = pakistan_candidates[:10]
    elif len(pakistan_candidates) >= 5:
        display_news = pakistan_candidates[:len(pakistan_candidates)]
    else:
        display_news = pakistan_candidates

    # Only Pakistan news is included; no separate Top 5 section
    display_top = []

    # Scholarships & government schemes (fresh items + always-listed official portals)
    from app.scholarships.collector import collect_scholarships, official_portal_items
    print("[INFO] Collecting Pakistan scholarships & government schemes...")
    fresh_schol = collect_scholarships(settings.request_timeout, settings.max_scholarship_items)
    new_schol = [x for x in fresh_schol if not db.already_sent(x.content_hash)]
    display_schol = fresh_schol if (dry_run or force_send) else new_schol
    portal_items = official_portal_items()
    print(f"[INFO] Scholarships: {len(display_schol)} fresh items + {len(portal_items)} official portals.")

    # AI & Tech launches / new articles (only items not sent before)
    from app.tech.collector import collect_tech_launches
    print("[INFO] Collecting AI / software / IT launches and articles...")
    fresh_tech = collect_tech_launches(settings.request_timeout)
    new_tech = [x for x in fresh_tech if not db.already_sent(x.content_hash)]
    display_tech = fresh_tech if (dry_run or force_send) else new_tech
    print(f"[INFO] Tech launches: {len(display_tech)} items.")

    # 6. AI Summarization & Contextual Analysis (Multi-Provider Failover)
    from app.ai.provider_manager import get_provider_manager
    ai_mgr = get_provider_manager(
        provider_priority=settings.provider_priority_list,
        gemini_api_key=settings.gemini_api_key,
        gemini_model=settings.gemini_model,
        mistral_api_key=settings.mistral_api_key,
        mistral_model=settings.mistral_model,
        auto_failover=settings.ai_auto_failover,
        db_path=settings.database_path
    )

    print(f"[INFO] Running AI summarization on {len(display_news)} intelligence items (provider priority: {', '.join(ai_mgr.priority)})...")
    summarize_news(display_news + display_schol + display_tech, model=settings.groq_model, provider_manager=ai_mgr)
    # Attach scholarships (after AI, so portals keep their fixed text)
    display_news = display_news + display_schol + display_tech + portal_items
    summarize_jobs(display_jobs, model=settings.groq_model, provider_manager=ai_mgr)

    # Group news for storage
    news_by_category = {}
    for item in display_news:
        news_by_category.setdefault(item.category, []).append(serialize_item(item))

    # Save digest package into SQLite database
    digest_record = {
        "date_full": date_info["full_date"],
        "time_pkt": date_info["time_pkt"],
        "iso_date": date_info["iso_date"],
        "top_stories": [serialize_item(s) for s in display_top],
        "news": news_by_category,
        "jobs": [serialize_item(j) for j in display_jobs]
    }

    db.save_digest(
        digest_date=date_info["iso_date"],
        news_count=len(display_news),
        jobs_count=len(display_jobs),
        digest_data=digest_record,
        status="completed",
        email_status="dry_run" if dry_run else "sent"
    )

    # 8. Render HTML email (Self-contained standalone digest)
    print("[INFO] Rendering self-contained HTML digest...")
    html = render_digest(
        news=display_news,
        jobs=display_jobs,
        top_stories=display_top,
        web_base_url=settings.public_base_url
    )

    attachment_filename = f"daily_digest_{date_info['iso_date']}.html"

    # 9. Handle Dry Run vs Production Send
    print("\n" + ai_mgr.generate_report() + "\n")

    if dry_run:
        out = settings.database_path.parent / attachment_filename
        out.write_text(html, encoding="utf-8")
        db.close()
        print(f"[SUCCESS] Dry run complete! Digest rendered to: {out}")
        return

    if not new_news and not new_jobs and not new_schol and not new_tech and not force_send:
        db.close()
        print("[INFO] No new qualifying intelligence stories or jobs found since last run. Skipping email dispatch.")
        return

    # 10. Send via Gmail SMTP with HTML file attachment
    try:
        print(f"[INFO] Dispatching digest via Gmail SMTP to {settings.email_to} with attachment {attachment_filename}...")
        resp = send_email(
            smtp_username=settings.smtp_username,
            smtp_app_password=settings.smtp_app_password,
            email_from=settings.email_from,
            email_to=settings.email_to,
            html=html,
            date_string=date_info["full_date"],
            attachment_html=html,
            attachment_filename=attachment_filename
        )
        print(f"[SUCCESS] Email delivered successfully. Response: {resp}")
        
        # Mark sent items in database ledger
        for x in new_news:
            db.mark_sent(x.content_hash, "news", x.title, x.url)
        for j in new_jobs:
            db.mark_sent(j.content_hash, "job", j.title, j.url)
        for x in new_schol:
            db.mark_sent(x.content_hash, "scholarship", x.title, x.url)
        for x in new_tech:
            db.mark_sent(x.content_hash, "tech", x.title, x.url)
    except Exception as exc:
        print(f"[ERROR] Email delivery failed: {exc}")
    finally:
        db.close()

    print("[INFO] Pipeline finished successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily Intelligence Digest Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Generate digest without sending email")
    parser.add_argument("--force-send", action="store_true", help="Send email even if items were previously seen")
    args = parser.parse_args()
    
    run(dry_run=args.dry_run, force_send=args.force_send)
