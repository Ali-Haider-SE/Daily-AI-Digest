"""Ranking and filtering engine for intelligence news and tech jobs."""
import re
from datetime import datetime, timezone
from typing import List
from app.models import NewsItem, JobItem


# Category importance baseline multipliers
CATEGORY_WEIGHTS = {
    "Pakistan": 12,
    "Wars & Geopolitics": 10,
    "Finance & Economy": 9,
    "Technology / AI": 9,
    "Trade": 8,
    "Science & Inventions": 7,
    "Global": 6,
}

def rank_news(items: List[NewsItem]) -> List[NewsItem]:
    """
    Deterministically rank news items combining:
    - Base credibility
    - Category geopolitical/national significance
    - Recency decay
    - Corroboration bonus (multiple sources reporting)
    """
    now = datetime.now(timezone.utc)
    for x in items:
        base = x.credibility_score * 0.45
        cat_score = CATEGORY_WEIGHTS.get(x.category, 6) * 2.5
        corroboration = min(x.corroboration_count * 5, 20)
        
        recency = 0
        if x.published_at:
            # Ensure published_at is timezone-aware
            dt = x.published_at if x.published_at.tzinfo else x.published_at.replace(tzinfo=timezone.utc)
            age_hours = max((now - dt).total_seconds() / 3600, 0)
            if age_hours < 6:
                recency = 15
            elif age_hours < 12:
                recency = 10
            elif age_hours < 24:
                recency = 5
        else:
            recency = 5  # default if unknown
            
        x.rank_score = round(base + cat_score + corroboration + recency, 2)
        x.importance_score = x.rank_score
        
    return sorted(items, key=lambda x: x.rank_score, reverse=True)


ENTRY_TERMS = [
    "intern", "internship", "graduate", "fresh graduate", "entry level",
    "junior", "trainee", "associate", "apprentice", "0 years", "0-1 years", "0-2 years"
]

TECH_TERMS = [
    "software", "developer", "computer science", "information technology",
    "it ", "data engineer", "data science", "qa", "quality assurance",
    "devops", "cloud", "cyber", "machine learning", "frontend", "backend",
    "full stack", "fullstack", "python", "javascript", "react", "fastapi"
]

EXCLUDED_OR_SENIOR_TERMS = [
    "senior", "staff", "principal", "lead", "head of", "director", "manager",
    "vp ", "5+ years", "7+ years", "10+ years", "phd required",
    "sales executive", "medical representative", "nurse", "civil engineer"
]


def score_job(j: JobItem) -> JobItem:
    """Calculate job match score for student/fresh graduate computer science/software engineering."""
    text = f"{j.title} {j.description} {j.experience} {j.employment_type}".lower()
    score = 0

    # Entry level qualification
    if any(term in text for term in ENTRY_TERMS):
        score += 55
        j.experience_level = "Entry Level / Internship"
    elif "1 year" in text or "junior" in j.title.lower():
        score += 40
        j.experience_level = "Junior (0-1 yr)"
    else:
        j.experience_level = "Early Career"

    # Computing / Software relevance
    if any(term in text for term in TECH_TERMS):
        score += 35

    # Location suitability: Pakistan or Remote
    loc = f"{j.location} {j.country}".lower()
    if j.remote or "remote" in text or "worldwide" in loc:
        score += 15
        j.remote = True
    elif "pakistan" in loc or "pk" in loc or any(city in loc for city in ["karachi", "lahore", "islamabad", "rawalpindi"]):
        score += 15

    # Penalize senior roles or completely unrelated fields
    if any(term in text for term in EXCLUDED_OR_SENIOR_TERMS):
        score -= 55

    j.match_score = max(0, min(score, 100))
    j.relevance_score = j.match_score

    if score >= 75:
        j.match_label = "Strong match"
    elif score >= 55:
        j.match_label = "Possible match"
    else:
        j.match_label = "Low match"

    return j


def _enrich_work_mode(j: JobItem) -> JobItem:
    """Infer and set work_mode if not already set."""
    if j.work_mode:
        return j
    text = f"{j.title} {j.description} {j.location}".lower()
    if "remote" in text or "worldwide" in text:
        j.work_mode = "Remote"
        j.remote = True
    elif "hybrid" in text:
        j.work_mode = "Hybrid"
    else:
        j.work_mode = "On-site"
    return j


def _is_english_text(text: str) -> bool:
    """Detect non-English scripts (Cyrillic, Arabic, Chinese/Japanese/Korean, non-English Latin accents)."""
    if not text:
        return True
    # Non-English Unicode script ranges (Cyrillic, Arabic/Urdu, CJK, Devanagari, etc.)
    if re.search(r'[\u0400-\u04FF\u0600-\u06FF\u4E00-\u9FFF\u3040-\u30FF\u0900-\u097F]', text):
        return False
    # Common non-English stop words found in foreign job titles / descriptions (German, French, Spanish, Dutch, etc.)
    foreign_stopwords = {
        "entwickler", "ingenieur", "stelle", "stellenangebot", "vollzeit", "teilzeit",
        "développeur", "ingénieur", "emploi", "stage", "desarrollador", "ingeniero", "oferta"
    }
    words = set(re.findall(r'\b[a-zA-Zäöüßéèàáóúñ]+\b', text.lower()))
    if words.intersection(foreign_stopwords):
        return False
    return True


def filter_jobs(jobs: List[JobItem], min_score: int = 55, max_jobs: int = 30) -> List[JobItem]:
    """Filter, enrich, and sort tech jobs by student / fresh graduate relevance.

    Returns at most max_jobs qualifying opportunities, ranked by match score then recency.
    Filters out any non-English job postings.
    """
    now = datetime.now(timezone.utc)

    # Filter out non-English listings (checking title and description)
    english_jobs = [
        j for j in jobs
        if _is_english_text(j.title) and _is_english_text((j.description or "")[:300])
    ]

    enriched = [_enrich_work_mode(score_job(j)) for j in english_jobs]
    qualified = [j for j in enriched if j.match_score >= min_score]


    def _sort_key(j):
        recency_bonus = 0
        if j.published_at:
            dt = j.published_at if j.published_at.tzinfo else j.published_at.replace(tzinfo=timezone.utc)
            age_days = max((now - dt).total_seconds() / 86400, 0)
            if age_days < 3:
                recency_bonus = 10
            elif age_days < 7:
                recency_bonus = 5
            elif age_days < 14:
                recency_bonus = 2
        return (j.match_score + recency_bonus, j.match_score)

    ranked = sorted(qualified, key=_sort_key, reverse=True)
    return ranked[:max_jobs]
