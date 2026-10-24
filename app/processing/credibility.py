"""Credibility assessment module for news sources and articles."""
from urllib.parse import urlparse
import re

# Reputable mainstream journalism organizations
HIGH_REPUTATION_SOURCES = {
    "reuters", "associated press", "ap news", "bbc", "bbc news", "bbc world",
    "al jazeera", "dawn", "business recorder", "financial times", "bloomberg",
    "the wall street journal", "wsj", "the guardian", "afp", "nasa", "nature", "science"
}

# Domain TLDs with high public trust/vetting
OFFICIAL_DOMAINS = {".gov", ".edu", ".gov.pk", ".edu.pk", ".org.pk", ".mil"}

# Recognized tech/science journalism
SPECIALIZED_TECH_SCIENCE = {
    "techcrunch", "ars technica", "mit technology review", "wired", "the verge", "ieee spectrum"
}

# Keywords indicating breaking / unverified / developing stories
DEVELOPING_PATTERNS = [
    r"\bdeveloping story\b",
    r"\bbreaking\b",
    r"\bunconfirmed reports\b",
    r"\bas it happens\b",
    r"\blive updates\b",
    r"\binitial reports\b",
    r"\bearly reports\b"
]

def is_developing_story(title: str, description: str) -> bool:
    """Detect if an article represents an actively developing situation."""
    text = f"{title} {description}".lower()
    for pat in DEVELOPING_PATTERNS:
        if re.search(pat, text):
            return True
    return False

def score_source(source: str, url: str, is_developing: bool = False, corroboration_count: int = 1) -> int:
    """Calculate an objective credibility score (0-100) based on source reputation and verification signals."""
    score = 50
    text = f"{source} {url}".lower()
    domain = urlparse(url).netloc.lower()

    # Reputable journalism
    if any(s in text for s in HIGH_REPUTATION_SOURCES) or any(s in domain for s in HIGH_REPUTATION_SOURCES):
        score += 35
    elif any(s in text for s in SPECIALIZED_TECH_SCIENCE) or any(s in domain for s in SPECIALIZED_TECH_SCIENCE):
        score += 25

    # Official / academic domains
    if any(domain.endswith(d) for d in OFFICIAL_DOMAINS):
        score += 15

    # Corroboration boost (independent confirmations)
    if corroboration_count >= 3:
        score += 10
    elif corroboration_count == 2:
        score += 5

    # Developing stories carry inherent volatility
    if is_developing:
        score = min(score, 75)

    return max(0, min(score, 100))

def label_score(score: int, is_developing: bool = False) -> str:
    """Return a reader-friendly verification label based on source credibility checks.

    Labels reflect the checks performed by this application, not an absolute guarantee
    that every detail in a story is correct.
    """
    if is_developing:
        # Actively developing stories may carry conflicting early reports
        return "Conflicting Reports"
    if score >= 85:
        # High-reputation sources with corroboration — strongest verification signal
        return "Authentic News"
    if score >= 70:
        # Credible source but limited independent corroboration
        return "Authentic News"
    if score >= 55:
        # Source found but insufficient corroboration to verify independently
        return "Verification Pending"
    return "Verification Pending"
