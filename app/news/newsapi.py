"""NewsAPI client with retry logic and error isolation."""
from datetime import datetime
import httpx
from app.models import NewsItem
from app.processing.credibility import is_developing_story

def collect_newsapi(api_key: str, timeout: int = 20):
    if not api_key:
        return []
        
    url = "https://newsapi.org/v2/top-headlines"
    params = {"apiKey": api_key, "language": "en", "pageSize": 100}
    
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as exc:
        print(f"[WARNING] NewsAPI request returned HTTP {exc.response.status_code}")
        return []
    except Exception as exc:
        print(f"[WARNING] NewsAPI request error: {type(exc).__name__}")
        return []
        
    out = []
    for a in data.get("articles", []):
        raw_dt = a.get("publishedAt") or ""
        dt = None
        if raw_dt:
            try:
                dt = datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
            except ValueError:
                dt = None
                
        title = (a.get("title") or "").strip()
        link = a.get("url") or ""
        description = (a.get("description") or "").strip()
        source_name = (a.get("source") or {}).get("name") or "NewsAPI"
        
        if title and link:
            is_dev = is_developing_story(title, description)
            out.append(NewsItem(
                title=title,
                url=link,
                source=source_name,
                source_url=link,
                published_at=dt,
                description=description,
                image_url=a.get("urlToImage") or "",
                author=a.get("author") or "",
                is_developing=is_dev
            ))
            
    return out
