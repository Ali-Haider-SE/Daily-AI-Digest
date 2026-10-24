"""Remotive remote job collector for worldwide computing and software roles."""
from datetime import datetime
import re
import httpx
from app.models import JobItem


def clean_html(raw_html: str) -> str:
    """Strip basic HTML tags from descriptions."""
    if not raw_html:
        return ""
    clean = re.sub(r"<[^>]+>", " ", raw_html)
    return " ".join(clean.split())


# Fetch multiple Remotive categories to improve entry-level coverage
REMOTIVE_CATEGORIES = [
    "software-dev",
    "data",
    "devops",
    "qa",
]


def collect_remotive(timeout: int = 20):
    out = []
    seen_urls = set()

    for category in REMOTIVE_CATEGORIES:
        try:
            with httpx.Client(timeout=timeout) as client:
                r = client.get(
                    "https://remotive.com/api/remote-jobs",
                    params={"category": category, "limit": 50}
                )
                r.raise_for_status()
                data = r.json()
        except Exception as exc:
            print(f"[WARNING] Remotive collection failed (category={category}): {exc}")
            continue

        for x in data.get("jobs", []):
            title = (x.get("title") or "").strip()
            link = x.get("url") or ""
            if not title or not link or link in seen_urls:
                continue
            seen_urls.add(link)

            company = (x.get("company_name") or "").strip()
            req_loc = (x.get("candidate_required_location") or "Worldwide").strip()
            desc = clean_html(x.get("description") or "")
            tags = x.get("tags") or []
            salary_raw = x.get("salary") or ""

            # Normalize salary
            salary = salary_raw.strip() if salary_raw and salary_raw.strip() else "Not disclosed"

            raw_pub = x.get("publication_date") or ""
            dt = None
            if raw_pub:
                try:
                    dt = datetime.fromisoformat(raw_pub.replace("Z", "+00:00"))
                except Exception:
                    dt = None

            job_type = x.get("job_type", "Full-time")

            out.append(JobItem(
                title=title,
                company=company,
                url=link,
                location=req_loc,
                description=desc[:2000],
                source="Remotive",
                published_at=dt,
                job_type=job_type,
                employment_type=job_type,
                remote=True,
                skills=tags if isinstance(tags, list) else [],
                salary=salary,
                work_mode="Remote",
            ))

    return out
