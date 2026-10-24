"""Himalayas.app public API collector — vetted remote tech jobs."""
import re
from datetime import datetime
import httpx
from app.models import JobItem


def clean_html(raw: str) -> str:
    if not raw:
        return ""
    clean = re.sub(r"<[^>]+>", " ", raw)
    return " ".join(clean.split())


def collect_himalayas(timeout: int = 20):
    """Fetch remote software jobs from Himalayas public API."""
    url = "https://himalayas.app/jobs/api"
    params = {
        "q": "software engineer OR developer OR intern OR python OR javascript",
        "limit": 50,
    }
    headers = {"User-Agent": "DailyIntelligenceDigest/1.0"}
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(url, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        print(f"[WARNING] Himalayas collection failed: {exc}")
        return []

    out = []
    for x in (data.get("jobs") or []):
        title = (x.get("title") or "").strip()
        company = (x.get("companyName") or x.get("company", {}).get("name", "")).strip()
        link = x.get("applicationLink") or x.get("url") or ""
        desc = clean_html(x.get("description") or "")
        salary_min = x.get("salaryMin") or x.get("salary_min")
        salary_max = x.get("salaryMax") or x.get("salary_max")
        currency = x.get("salaryCurrency") or "USD"
        req_location = (x.get("locationRestrictions") or ["Worldwide"])[0] if isinstance(x.get("locationRestrictions"), list) else "Worldwide"
        skills = x.get("skills") or []
        if isinstance(skills, list):
            skills = [s.get("name", s) if isinstance(s, dict) else s for s in skills]

        if not title or not link:
            continue

        salary = "Not disclosed"
        if salary_min and salary_max:
            salary = f"{currency} {salary_min:,}–{salary_max:,}/year"
        elif salary_min:
            salary = f"{currency} {salary_min:,}+/year"

        raw_date = x.get("createdAt") or x.get("publishedAt") or ""
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
            location=req_location,
            description=desc[:2000],
            source="Himalayas",
            published_at=dt,
            job_type="Full-time",
            employment_type="Full-time",
            remote=True,
            skills=skills,
            salary=salary,
            work_mode="Remote",
        ))

    return out
