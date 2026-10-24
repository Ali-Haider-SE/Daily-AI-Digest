"""Email HTML renderer for Daily Intelligence Digest with table-based email client compatibility."""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import datetime
import zoneinfo
from typing import List, Dict
from app.models import NewsItem, JobItem

BASE = Path(__file__).resolve().parent.parent.parent
env = Environment(
    loader=FileSystemLoader(BASE / "templates"),
    autoescape=select_autoescape(["html", "xml"])
)

def format_digest_date(dt: datetime = None) -> Dict[str, str]:
    """Format full date, weekday, time, and timezone according to Asia/Karachi (PKT)."""
    try:
        pkt = zoneinfo.ZoneInfo("Asia/Karachi")
    except Exception:
        import datetime as dt_module
        pkt = dt_module.timezone(dt_module.timedelta(hours=5), name="PKT")
        
    if dt is None:
        now = datetime.now(pkt)
    else:
        now = dt.astimezone(pkt) if dt.tzinfo else dt.replace(tzinfo=pkt)
        
    return {
        "full_date": now.strftime("%A, %B %d, %Y"),
        "time_pkt": now.strftime("%I:%M %p PKT"),
        "iso_date": now.strftime("%Y-%m-%d"),
        "weekday": now.strftime("%A")
    }

def render_digest(
    news: List[NewsItem],
    jobs: List[JobItem],
    top_stories: List[NewsItem],
    web_base_url: str = "http://127.0.0.1:8000"
) -> str:
    """Render responsive, accessible, cross-client HTML email."""
    date_info = format_digest_date()
    grouped = {}
    for x in news:
        grouped.setdefault(x.category, []).append(x)
        
    categories = [
        "Pakistan"
    ]
    
    clean_base_url = (web_base_url or "").strip().rstrip("/")
    if not clean_base_url:
        clean_base_url = "http://127.0.0.1:8000"

    template = env.get_template("daily_digest.html")
    return template.render(
        date_full=date_info["full_date"],
        time_pkt=date_info["time_pkt"],
        iso_date=date_info["iso_date"],
        top_stories=top_stories,
        news=grouped,
        jobs=jobs,
        categories=categories,
        web_base_url=clean_base_url
    )
