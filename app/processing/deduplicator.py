"""Deduplication module with corroboration counting."""
import hashlib
import re
from difflib import SequenceMatcher
from typing import List
from app.models import NewsItem

def norm(s: str) -> str:
    """Normalize text by lowercasing and stripping non-alphanumeric chars."""
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).strip()

def content_hash(title: str, url: str) -> str:
    """Generate deterministic SHA256 hash from normalized title and clean URL."""
    clean_url = (url or "").split("?")[0].strip().lower()
    return hashlib.sha256(f"{norm(title)}|{clean_url}".encode("utf-8")).hexdigest()

def deduplicate(items: List[NewsItem], similarity_threshold: float = 0.82) -> List[NewsItem]:
    """
    Deduplicate news items while aggregating corroborating sources.
    If multiple reputable sources report the same story, preserve the primary
    and increment corroboration_count / source_count.
    """
    out: List[NewsItem] = []
    for item in items:
        key = norm(item.title)
        if not key:
            continue
        
        found = False
        for old in out:
            old_key = norm(old.title)
            # Check title similarity or identical core URL
            ratio = SequenceMatcher(None, key, old_key).ratio()
            same_url = (item.url.split("?")[0].lower() == old.url.split("?")[0].lower()) if item.url and old.url else False
            
            if ratio >= similarity_threshold or same_url:
                old.source_count += 1
                old.corroboration_count += 1
                # If the new item has a richer description or higher initial reputation, preserve it
                if len(item.description or "") > len(old.description or ""):
                    old.description = item.description
                if not old.image_url and item.image_url:
                    old.image_url = item.image_url
                found = True
                break
                
        if not found:
            item.content_hash = content_hash(item.title, item.url)
            out.append(item)
            
    return out
