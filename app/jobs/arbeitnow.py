"""Arbeitnow RSS/API collector — international remote & entry-level tech jobs.

Arbeitnow provides a free public JSON API for job listings with no authentication
required. It focuses on international remote roles with visa sponsorship options.
"""
import re
from datetime import datetime
import httpx
from app.models import JobItem


def clean_html(raw: str) -> str:
    if not raw:
        return ""
    clean = re.sub(r"<[^>]+>", " ", raw)
    return " ".join(clean.split())


def collect_arbeitnow(timeout: int = 20):
    """Fetch remote tech jobs from Arbeitnow public API."""
    url = "https://www.arbeitnow.com/api/job-board-api"
    headers = {"User-Agent": "DailyIntelligenceDigest/1.0"}
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(url, headers=headers)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        print(f"[WARNING] Arbeitnow collection failed: {exc}")
        return []

    tech_keywords = {
        "software", "developer", "engineer", "python", "javascript", "react",
        "node", "backend", "frontend", "fullstack", "devops", "cloud", "data",
        "machine learning", "ai", "web", "java", "typescript", "go", "php",
        "android", "ios", "flutter", "mobile", "intern", "graduate", "junior",
    }

    out = []
    for x in (data.get("data") or []):
        title = (x.get("title") or "").strip()
        company = (x.get("company_name") or "").strip()
        link = x.get("url") or ""
        tags = [t.lower() for t in (x.get("tags") or [])]
        desc = clean_html(x.get("description") or "")
        remote = x.get("remote", False)
        location = (x.get("location") or "Remote").strip()

        if not title or not link:
            continue

        tag_match = any(t in tech_keywords for t in tags)
        title_match = any(t in title.lower() for t in tech_keywords)
        desc_match = any(t in desc.lower()[:400] for t in tech_keywords)
        if not (tag_match or title_match or desc_match):
            continue

        raw_date = x.get("created_at") or ""
        dt = None
        if raw_date:
            try:
                dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            except Exception:
                dt = None

        out.append(JobItem(
            title=title,
            company=company or "Confidential",
            url=link,
            location=location,
            description=desc[:2000],
            source="Arbeitnow",
            published_at=dt,
            job_type="Full-time",
            employment_type="Full-time",
            remote=remote or "remote" in location.lower(),
            skills=tags,
            salary="Not disclosed",
            work_mode="Remote" if remote else "On-site",
        ))

    return out
