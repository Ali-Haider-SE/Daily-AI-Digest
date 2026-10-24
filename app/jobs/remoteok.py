"""Remote OK public API collector — fully remote software engineering roles."""
import re
from datetime import datetime, timezone
import httpx
from app.models import JobItem


def clean_html(raw: str) -> str:
    if not raw:
        return ""
    clean = re.sub(r"<[^>]+>", " ", raw)
    return " ".join(clean.split())


def collect_remoteok(timeout: int = 20):
    """Fetch jobs from Remote OK public API (no auth required)."""
    url = "https://remoteok.com/api"
    headers = {"User-Agent": "DailyIntelligenceDigest/1.0 (+https://github.com)"}
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(url, headers=headers)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        print(f"[WARNING] RemoteOK collection failed: {exc}")
        return []

    tech_tags = {
        "software", "developer", "engineer", "python", "javascript", "react",
        "node", "backend", "frontend", "fullstack", "devops", "data", "ml",
        "ai", "cloud", "it", "cyber", "web", "java", "typescript", "go",
        "rails", "ruby", "php", "mobile", "android", "ios", "flutter",
    }

    out = []
    for x in data:
        if not isinstance(x, dict):
            continue
        title = (x.get("position") or "").strip()
        company = (x.get("company") or "").strip()
        link = x.get("url") or ""
        tags = [t.lower() for t in (x.get("tags") or [])]
        desc = clean_html(x.get("description") or "")
        salary_min = x.get("salary_min")
        salary_max = x.get("salary_max")

        if not title or not link:
            continue

        # Filter: must look like a tech role
        tag_match = any(t in tech_tags for t in tags)
        title_match = any(t in title.lower() for t in tech_tags)
        if not tag_match and not title_match:
            continue

        # Build salary string
        salary = "Not disclosed"
        if salary_min and salary_max:
            salary = f"${salary_min:,}–${salary_max:,}/year (USD)"
        elif salary_min:
            salary = f"${salary_min:,}+/year (USD)"

        raw_date = x.get("date") or ""
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
            location="Worldwide",
            description=desc[:2000],
            source="RemoteOK",
            published_at=dt,
            job_type="Full-time",
            employment_type="Full-time",
            remote=True,
            skills=tags,
            salary=salary,
            work_mode="Remote",
        ))

    return out
