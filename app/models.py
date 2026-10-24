from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    source_url: str = ""
    published_at: Optional[datetime] = None
    description: str = ""
    category: str = "Global"
    image_url: str = ""
    author: str = ""
    credibility_score: int = 50
    credibility_label: str = "Verification Pending"
    importance_score: float = 0.0
    rank_score: float = 0.0
    summary: str = ""
    why_it_matters: str = ""
    source_count: int = 1
    corroboration_count: int = 1
    is_developing: bool = False
    content_hash: str = ""
    created_at: Optional[datetime] = None


@dataclass
class JobItem:
    title: str
    company: str
    url: str
    location: str = ""
    description: str = ""
    source: str = ""
    published_at: Optional[datetime] = None
    experience: str = ""
    experience_level: str = ""
    job_type: str = ""
    employment_type: str = ""
    remote: bool = False
    country: str = ""
    skills: List[str] = field(default_factory=list)
    degree_requirements: str = ""
    match_score: int = 0
    relevance_score: int = 0
    match_label: str = ""
    content_hash: str = ""
    created_at: Optional[datetime] = None

    # Extended fields for table view
    salary: str = ""               # e.g. "PKR 50,000/month" or "Not disclosed"
    work_mode: str = ""            # "Remote", "Hybrid", "On-site"
    responsibilities: str = ""     # 1-3 sentence plain-English summary
    key_skills: str = ""           # Main technical skills / technologies
    deadline: str = ""             # Application deadline or "Not specified"

