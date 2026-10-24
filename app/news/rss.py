"""RSS feed collector supporting custom user-agent headers, retries, and isolated parsing."""
from datetime import datetime, timezone
import time
import urllib.request
import feedparser
from app.models import NewsItem
from app.news.sources import RSS_SOURCES
from app.processing.credibility import is_developing_story

STANDARD_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 (DailyIntelligenceDigest/2.0; +https://github.com)"
)

def fetch_feed_content(url: str, timeout: int = 15, max_retries: int = 2) -> bytes:
    """Fetch raw feed bytes with a realistic browser User-Agent and gentle backoff."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": STANDARD_USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        }
    )
    
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:
            last_err = exc
            if attempt < max_retries:
                time.sleep(1.0 * (attempt + 1))  # Exponential backoff (1s, 2s)
                
    raise last_err

def collect_rss(sources=None, timeout=15):
    """Safely collect news articles from all configured RSS feeds with total exception isolation."""
    if sources is None:
        sources = RSS_SOURCES
        
    items = []
    for meta in sources:
        name = meta.get("name", "Unknown Source")
        url = meta.get("url", "")
        base_cat = meta.get("category", "Global")
        base_cred = meta.get("credibility", 70)
        
        if not url:
            continue
            
        try:
            # 1. First attempt robust fetch with realistic headers
            raw_data = None
            try:
                raw_data = fetch_feed_content(url, timeout=timeout)
            except Exception as fetch_exc:
                # Log non-fatal warning and fall back to feedparser direct
                raw_data = None
                
            # 2. Parse feed either from raw content or direct URL fallback
            if raw_data:
                feed = feedparser.parse(raw_data)
            else:
                feed = feedparser.parse(url)
                
            if feed.bozo and not feed.entries:
                print(f"[INFO] Skipping unavailable or malformed feed for {name}")
                continue
                
            for e in feed.entries[:35]:
                title = (e.get("title") or "").strip()
                link = (e.get("link") or "").strip()
                if not title or not link:
                    continue
                
                # Safe date parsing
                dt = None
                parsed = e.get("published_parsed") or e.get("updated_parsed")
                if parsed:
                    try:
                        dt = datetime(*parsed[:6], tzinfo=timezone.utc)
                    except Exception:
                        dt = None
                
                # Image extraction
                image_url = ""
                if "media_content" in e and len(e["media_content"]) > 0:
                    image_url = e["media_content"][0].get("url", "")
                elif "media_thumbnail" in e and len(e["media_thumbnail"]) > 0:
                    image_url = e["media_thumbnail"][0].get("url", "")
                elif "enclosures" in e and len(e["enclosures"]) > 0:
                    image_url = e["enclosures"][0].get("href", "")
                    
                author = e.get("author", "")
                description = (e.get("summary") or e.get("description") or "").strip()
                
                # Clean html tags from description if simple
                if "<" in description and ">" in description:
                    import re
                    description = re.sub(r"<[^>]+>", "", description).strip()
                
                is_dev = is_developing_story(title, description)
                
                items.append(NewsItem(
                    title=title,
                    url=link,
                    source=name,
                    source_url=url,
                    published_at=dt,
                    description=description,
                    category=base_cat,
                    image_url=image_url,
                    author=author,
                    credibility_score=base_cred,
                    is_developing=is_dev
                ))
        except Exception as exc:
            print(f"[WARNING] RSS collection skipped for {name}: {exc}")
            continue
            
    return items
