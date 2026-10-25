"""AI / software / IT launches and articles collector.

Reads a few official tech feeds, keeps only recent items, and tags them with
the category "AI & Tech Launches". A feed that fails is skipped (it never
breaks the pipeline).
"""
from datetime import datetime, timezone, timedelta
from typing import List

from app.models import NewsItem
from app.news.rss import collect_rss
from app.processing.deduplicator import deduplicate

CATEGORY = "AI & Tech Launches"
MAX_AGE_DAYS = 3

# NOTE: feed URLs are standard public feeds, but a feed can change or go down.
# If one stops working it is simply skipped.
TECH_SOURCES = [
    {"name": "OpenAI News", "url": "https://openai.com/news/rss.xml", "credibility": 85},
    {"name": "Google Blog AI", "url": "https://blog.google/technology/ai/rss/", "credibility": 85},
    {"name": "GitHub Blog", "url": "https://github.blog/feed/", "credibility": 85},
    {"name": "Hacker News", "url": "https://news.ycombinator.com/rss", "credibility": 70},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "credibility": 80},
]


def collect_tech_launches(timeout: int = 15, max_items: int = 8) -> List[NewsItem]:
    sources = [dict(s, category=CATEGORY, region="Global") for s in TECH_SOURCES]
    items = collect_rss(sources=sources, timeout=timeout)

    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    recent = []
    for x in items:
        if x.published_at is None or x.published_at >= cutoff:
            x.category = CATEGORY
            recent.append(x)

    unique = deduplicate(recent)
    unique.sort(
        key=lambda x: (x.credibility_score, x.published_at or cutoff),
        reverse=True,
    )
    return unique[:max_items]
