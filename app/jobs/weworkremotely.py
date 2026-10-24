"""We Work Remotely RSS feed collector — curated remote tech jobs."""
import re
from datetime import datetime
import feedparser
from app.models import JobItem


def clean_html(raw: str) -> str:
    if not raw:
        return ""
    clean = re.sub(r"<[^>]+>", " ", raw)
    return " ".join(clean.split())


# WWR publishes separate RSS feeds per category
WWR_FEEDS = [
    ("https://weworkremotely.com/categories/remote-programming-jobs.rss", "Programming"),
    ("https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss", "DevOps"),
    ("https://weworkremotely.com/categories/remote-data-science-jobs.rss", "Data Science"),
]


def collect_weworkremotely(timeout: int = 20):
    """Fetch remote jobs from We Work Remotely official RSS feeds."""
    out = []
    for feed_url, category in WWR_FEEDS:
        try:
            import socket
            socket.setdefaulttimeout(timeout)
            parsed = feedparser.parse(feed_url)
            entries = parsed.get("entries", [])
        except Exception as exc:
            print(f"[WARNING] We Work Remotely ({category}) feed failed: {exc}")
            continue

        for entry in entries:
            title_raw = entry.get("title", "")
            # WWR titles often include company: "Company: Title"
            if ": " in title_raw:
                parts = title_raw.split(": ", 1)
                company = parts[0].strip()
                title = parts[1].strip()
            else:
                title = title_raw.strip()
                company = ""

            link = entry.get("link", "")
            desc = clean_html(entry.get("summary", ""))
            region = entry.get("region") or entry.get("tags", [{}])[0].get("term", "Worldwide") if entry.get("tags") else "Worldwide"

            raw_pub = entry.get("published", "")
            dt = None
            if raw_pub:
                try:
                    import email.utils
                    parsed_dt = email.utils.parsedate_to_datetime(raw_pub)
                    dt = parsed_dt
                except Exception:
                    dt = None

            if title and link:
                out.append(JobItem(
                    title=title,
                    company=company or "Confidential",
                    url=link,
                    location=str(region),
                    description=desc[:2000],
                    source="We Work Remotely",
                    published_at=dt,
                    job_type="Full-time",
                    employment_type="Full-time",
                    remote=True,
                    salary="Not disclosed",
                    work_mode="Remote",
                ))

    return out
