"""Rozee.pk RSS feed collector — Pakistan's largest job portal.

Rozee.pk provides public RSS feeds for job categories without requiring authentication.
This collector fetches IT/Software job listings relevant to fresh graduates and students.
"""
import re
from datetime import datetime
import feedparser
from app.models import JobItem


def clean_html(raw: str) -> str:
    if not raw:
        return ""
    clean = re.sub(r"<[^>]+>", " ", raw)
    return " ".join(clean.split())


# Rozee.pk RSS feeds for IT/computing categories
ROZEE_FEEDS = [
    "https://www.rozee.pk/rss/jobs/f/2",   # IT/Software
    "https://www.rozee.pk/rss/jobs/f/5",   # Engineering/Technology
]


def collect_rozee(timeout: int = 25):
    """Fetch IT/Software jobs from Rozee.pk RSS feeds."""
    import socket
    out = []
    for feed_url in ROZEE_FEEDS:
        try:
            socket.setdefaulttimeout(timeout)
            parsed = feedparser.parse(feed_url)
            entries = parsed.get("entries", [])
        except Exception as exc:
            print(f"[WARNING] Rozee.pk feed ({feed_url}) failed: {exc}")
            continue

        for entry in entries:
            title = (entry.get("title") or "").strip()
            link = entry.get("link", "")
            desc = clean_html(entry.get("summary") or entry.get("description") or "")
            company_tag = entry.get("author") or entry.get("tags", [{}])[0].get("term", "") if entry.get("tags") else ""
            company = company_tag.strip() if company_tag else ""

            raw_pub = entry.get("published", "")
            dt = None
            if raw_pub:
                try:
                    import email.utils
                    dt = email.utils.parsedate_to_datetime(raw_pub)
                except Exception:
                    dt = None

            if title and link:
                out.append(JobItem(
                    title=title,
                    company=company or "Confidential",
                    url=link,
                    location="Pakistan",
                    description=desc[:2000],
                    source="Rozee.pk",
                    published_at=dt,
                    job_type="Full-time",
                    employment_type="Full-time",
                    remote=False,
                    country="PK",
                    salary="Not disclosed",
                    work_mode="On-site",
                ))

    return out
