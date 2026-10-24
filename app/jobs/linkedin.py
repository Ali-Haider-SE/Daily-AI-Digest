"""LinkedIn job collector — entry-level & internship software/computing opportunities."""
import re
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from app.models import JobItem


def clean_html(raw: str) -> str:
    if not raw:
        return ""
    clean = re.sub(r"<[^>]+>", " ", raw)
    return " ".join(clean.split())


def collect_linkedin(timeout: int = 15) -> list[JobItem]:
    """Fetch public LinkedIn job listings for Pakistan and Remote software roles."""
    search_queries = [
        ("software engineer intern", "Pakistan"),
        ("junior developer", "Pakistan"),
        ("software engineer", "Remote"),
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    out: list[JobItem] = []
    seen_urls = set()

    for keywords, location in search_queries:
        url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        params = {
            "keywords": keywords,
            "location": location,
            "start": 0,
        }

        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                r = client.get(url, params=params, headers=headers)
                if r.status_code != 200:
                    continue
                
                soup = BeautifulSoup(r.text, "html.parser")
                cards = soup.find_all("div", class_="job-search-card")

                for card in cards:
                    title_el = card.find("h3") or card.find("h3", class_="base-search-card__title")
                    company_el = card.find("h4") or card.find("a", class_="hidden-nested-link")
                    location_el = card.find("span", class_="job-search-card__location")
                    link_el = card.find("a", class_="base-card__full-link") or card.find("a")
                    time_el = card.find("time")

                    title = title_el.text.strip() if title_el else ""
                    company = company_el.text.strip() if company_el else "LinkedIn Recruiter"
                    loc = location_el.text.strip() if location_el else location
                    link = link_el["href"].split("?")[0] if (link_el and link_el.has_attr("href")) else ""

                    if not title or not link or link in seen_urls:
                        continue
                    seen_urls.add(link)

                    raw_date = time_el.get("datetime") if (time_el and time_el.has_attr("datetime")) else ""
                    dt = None
                    if raw_date:
                        try:
                            dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                        except Exception:
                            dt = None

                    is_remote = "remote" in loc.lower() or "remote" in title.lower()

                    out.append(JobItem(
                        title=title,
                        company=company,
                        url=link,
                        location=loc,
                        description=f"{title} position at {company} in {loc}.",
                        source="LinkedIn",
                        published_at=dt,
                        job_type="Full-time" if "intern" not in title.lower() else "Internship",
                        employment_type="Full-time" if "intern" not in title.lower() else "Internship",
                        remote=is_remote,
                        skills=["Software Engineering", "IT"],
                        salary="Not disclosed",
                        work_mode="Remote" if is_remote else ("On-site" if "hybrid" not in loc.lower() else "Hybrid"),
                    ))
        except Exception as exc:
            print(f"[WARNING] LinkedIn query for '{keywords}' in '{location}' failed: {exc}")

    return out
