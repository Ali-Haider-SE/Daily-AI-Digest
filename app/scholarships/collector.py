"""Pakistan scholarships & government schemes collector.

Two layers:
1. Fresh items: HEC announcements page (official) + Google News RSS searches
   for scholarship / youth-scheme headlines from Pakistani outlets.
2. Evergreen official portals (HEC, PMYP, NAVTTC...) that are always listed so the
   section is never empty and readers always have the official apply links.

Every network call is isolated: a failing source never breaks the pipeline.
"""
import re
import time
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import List

import feedparser
from bs4 import BeautifulSoup

from app.models import NewsItem
from app.news.rss import fetch_feed_content
from app.processing.credibility import score_source, label_score
from app.processing.deduplicator import content_hash

CATEGORY = "Scholarships & Schemes"
MAX_AGE_DAYS = 45

HEC_ANNOUNCEMENTS_URL = "https://www.hec.gov.pk/english/HECAnnouncements"

# Searches run on Google News RSS (Pakistan edition), last 30 days.
NEWS_QUERIES = [
    "HEC scholarship",
    "Benazir Undergraduate Scholarship",
    "Ehsaas scholarship",
    "Prime Minister Youth Programme",
    "PM Youth Laptop Scheme",
    "NAVTTC training programme",
    "fully funded scholarship Pakistani students",
]

RELEVANT = re.compile(
    r"scholarship|fellowship|stipend|bursary|financial aid|laptop scheme|youth programme|"
    r"youth loan|ehsaas|benazir|navttc|pmyp|hec\b|apply now|applications? (open|invited)",
    re.I,
)

# Always-listed official portals (verify links occasionally; government sites move pages).
OFFICIAL_PORTALS = [
    ("HEC Scholarship Portal — apply for HEC local & overseas scholarships",
     "https://scholarship.hec.gov.pk", "HEC (Official)",
     "Official online application portal of the Higher Education Commission for scholarship programmes."),
    ("HEC Announcements — latest scholarship & test notices",
     "https://www.hec.gov.pk/english/HECAnnouncements", "HEC (Official)",
     "Official HEC notice board: new scholarship calls, deadlines and HAT/USAT test updates."),
    ("Benazir Undergraduate Scholarship (HEC)",
     "https://www.hec.gov.pk/english/scholarshipsgrants/Ehsaas/Pages/default.aspx", "HEC (Official)",
     "Need-based undergraduate scholarship programme for students from low-income families."),
    ("Allama Muhammad Iqbal Scholarship (HEC)",
     "https://www.hec.gov.pk/english/scholarshipsgrants/CAFC/Pages/default.aspx", "HEC (Official)",
     "Fully funded undergraduate study scholarship offered through HEC."),
    ("HEC Need Based Scholarship",
     "https://www.hec.gov.pk/english/scholarshipsgrants/nbs/pages/downloads.aspx", "HEC (Official)",
     "Need-based scholarship for students at public sector universities; forms and guidelines."),
    ("Prime Minister's Youth Programme (PMYP)",
     "https://www.pmyp.gov.pk", "PMYP (Official)",
     "Federal youth programme: laptop scheme, skills, loans and other youth initiatives."),
    ("PM Youth Laptop Scheme portal",
     "https://laptop.pmyp.gov.pk", "PMYP (Official)",
     "Application and merit-list portal for the Prime Minister's Youth Laptop Scheme."),
    ("NAVTTC — National Vocational & Technical Training Commission",
     "https://www.navttc.gov.pk", "NAVTTC (Official)",
     "Government skills-training programmes and courses for youth."),
]


def _clean(text: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", text or "").split())


def _finish(item: NewsItem, base_cred: int = None) -> NewsItem:
    item.category = CATEGORY
    item.content_hash = content_hash(item.title, item.url)
    score = score_source(item.source, item.url)
    item.credibility_score = max(score, base_cred) if base_cred else score
    item.credibility_label = label_score(item.credibility_score, False)
    return item


def collect_hec_announcements(timeout: int = 15, limit: int = 10) -> List[NewsItem]:
    """Best-effort scrape of scholarship-related links on the official HEC notice page."""
    items: List[NewsItem] = []
    try:
        html = fetch_feed_content(HEC_ANNOUNCEMENTS_URL, timeout=timeout, max_retries=1)
        soup = BeautifulSoup(html, "html.parser")
        seen = set()
        for a in soup.find_all("a", href=True):
            text = _clean(a.get_text())
            if len(text) < 15 or not re.search(r"scholar|fellowship|stipend|hat\b|apply|funded", text, re.I):
                continue
            url = urllib.parse.urljoin(HEC_ANNOUNCEMENTS_URL, a["href"])
            if url in seen:
                continue
            seen.add(url)
            items.append(_finish(NewsItem(
                title=text[:200], url=url, source="HEC (Official)",
                source_url=HEC_ANNOUNCEMENTS_URL,
                description="Official HEC announcement. Open the link for eligibility, dates and how to apply.",
            ), base_cred=90))
            if len(items) >= limit:
                break
    except Exception as exc:
        print(f"[INFO] HEC announcements page unavailable: {exc}")
    return items


def collect_scholarship_news(timeout: int = 15, per_query: int = 6) -> List[NewsItem]:
    """Scholarship / youth-scheme headlines from Google News RSS (Pakistan edition)."""
    items: List[NewsItem] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    for q in NEWS_QUERIES:
        url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(f"{q} when:30d")
               + "&hl=en-PK&gl=PK&ceid=PK:en")
        try:
            feed = feedparser.parse(fetch_feed_content(url, timeout=timeout, max_retries=1))
        except Exception as exc:
            print(f"[INFO] Scholarship news query '{q}' skipped: {exc}")
            continue
        for e in feed.entries[:per_query]:
            title = (e.get("title") or "").strip()
            link = (e.get("link") or "").strip()
            publisher = ((e.get("source") or {}).get("title") or "").strip()
            if publisher and title.endswith(f" - {publisher}"):
                title = title[: -len(f" - {publisher}")].strip()
            if not title or not link or not RELEVANT.search(title):
                continue
            dt = None
            parsed = e.get("published_parsed")
            if parsed:
                try:
                    dt = datetime(*parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    dt = None
            if dt and dt < cutoff:
                continue
            items.append(_finish(NewsItem(
                title=title, url=link, source=publisher or "Google News",
                source_url=url, published_at=dt,
                description=_clean(e.get("summary") or "") if publisher == "" else title,
            )))
        time.sleep(0.3)
    return items


def collect_scholarships(timeout: int = 15, max_items: int = 10) -> List[NewsItem]:
    """Fresh scholarship/scheme items, deduplicated by title, official HEC first, newest next."""
    hec = collect_hec_announcements(timeout)
    news = collect_scholarship_news(timeout)
    news.sort(key=lambda x: x.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    out, seen_titles = [], set()
    for x in hec + news:
        key = re.sub(r"[^a-z0-9]", "", x.title.lower())[:60]
        if key in seen_titles:
            continue
        seen_titles.add(key)
        out.append(x)
    return out[:max_items]


def official_portal_items() -> List[NewsItem]:
    """Evergreen official links (always shown, never marked as 'already sent')."""
    items = []
    for title, url, source, desc in OFFICIAL_PORTALS:
        it = _finish(NewsItem(title=title, url=url, source=source, source_url=url, description=desc),
                     base_cred=95)
        it.summary = desc
        it.why_it_matters = "Official source: always confirm deadlines and eligibility here before applying."
        items.append(it)
    return items
