"""Comprehensive test suite for processing, credibility, deduplication, ranking, and date formatting."""
from datetime import datetime, timezone, timedelta
from app.models import NewsItem, JobItem
from app.processing.categorizer import categorize
from app.processing.credibility import score_source, label_score, is_developing_story
from app.processing.deduplicator import deduplicate, content_hash
from app.processing.ranking import rank_news, score_job, filter_jobs
from app.email.renderer import format_digest_date

def test_categorization_sectors():
    assert categorize("Pakistan inflation hit record high", "SBP rate cut") == "Pakistan"
    assert categorize("Israel and Hezbollah missile strikes", "Military conflict in Middle East") == "Wars & Geopolitics"
    assert categorize("Federal Reserve interest rate hike", "Central bank monetary policy stocks") == "Finance & Economy"
    assert categorize("Customs tariff imposed on automobile imports", "Trade shipping and WTO guidelines") == "Trade"
    assert categorize("OpenAI reveals next generation reasoning LLM model", "Artificial intelligence semiconductor chip") == "Technology / AI"
    assert categorize("NASA James Webb telescope discovers exoplanet atmosphere", "Quantum physics breakthrough discovery") == "Science & Inventions"
    assert categorize("Generic local community announcement", "Local town council meeting") == "Global"

def test_credibility_scoring_and_labels():
    # Reputable journalism — should yield "Authentic News"
    score_reuters = score_source("Reuters", "https://www.reuters.com/world/article")
    assert score_reuters >= 85
    assert label_score(score_reuters) == "Authentic News"

    # Official government
    score_gov = score_source("Finance Ministry", "https://finance.gov.pk/press-release")
    assert score_gov >= 65

    # Developing story — should yield "Conflicting Reports"
    score_dev = score_source("Reuters", "https://www.reuters.com/breaking", is_developing=True)
    assert score_dev <= 75
    assert label_score(score_dev, is_developing=True) == "Conflicting Reports"

    # Low-credibility source — should yield "Verification Pending"
    score_low = score_source("Random Blog", "https://randomblog.net/article")
    assert label_score(score_low) == "Verification Pending"

    # Old labels must never be returned
    assert label_score(score_reuters) != "High confidence"
    assert label_score(score_reuters) != "Medium confidence"
    assert label_score(score_dev, is_developing=True) != "Developing"

def test_developing_story_detection():
    assert is_developing_story("Breaking: Earthquake hits coastal region", "Live updates incoming") is True
    assert is_developing_story("Annual fiscal budget report", "Stable audited report") is False

def test_deduplication_and_corroboration():
    item1 = NewsItem(
        title="Pakistan signs bilateral trade agreement with China",
        url="https://dawn.com/news/123",
        source="Dawn",
        description="Short brief"
    )
    item2 = NewsItem(
        title="Pakistan signs bilateral trade agreement with China!",
        url="https://brecorder.com/news/456",
        source="Business Recorder",
        description="Much more detailed brief with complete economic indicators and analysis."
    )
    results = deduplicate([item1, item2])
    assert len(results) == 1
    assert results[0].corroboration_count == 2
    assert results[0].source_count == 2
    # Enriched description from item2 preserved
    assert "detailed brief" in results[0].description

def test_ranking_determinism():
    now = datetime.now(timezone.utc)
    pak_story = NewsItem(
        title="Pakistan economic reform approved",
        url="https://dawn.com/1",
        source="Dawn",
        category="Pakistan",
        credibility_score=90,
        published_at=now - timedelta(hours=2),
        corroboration_count=2
    )
    global_old = NewsItem(
        title="Minor global update",
        url="https://other.com/2",
        source="Other",
        category="Global",
        credibility_score=60,
        published_at=now - timedelta(hours=30),
        corroboration_count=1
    )
    ranked = rank_news([global_old, pak_story])
    assert ranked[0].title == pak_story.title
    assert ranked[0].rank_score > ranked[1].rank_score

def test_job_matching_and_filtering():
    good_intern = JobItem(
        title="Software Engineer Intern",
        company="Systems Ltd",
        url="https://systems.com/careers/intern",
        location="Lahore, Pakistan",
        description="Fresh graduate or final year student in BS Computer Science or Software Engineering. Python, Git.",
        remote=False
    )
    good_remote = JobItem(
        title="Junior Python Developer",
        company="Remote Corp",
        url="https://remotecorp.com/jobs/1",
        location="Worldwide",
        description="Entry level 0-1 years experience in Python, web APIs. Remote anywhere.",
        remote=True
    )
    senior_role = JobItem(
        title="Principal Software Architect",
        company="Global Tech",
        url="https://global.com/lead",
        location="Karachi",
        description="10+ years experience leading distributed systems teams. Director level.",
        remote=False
    )
    unrelated_sales = JobItem(
        title="Medical Sales Representative",
        company="Pharma Ltd",
        url="https://pharma.com/sales",
        location="Islamabad",
        description="Field sales executive for pharmaceuticals.",
        remote=False
    )

    foreign_german = JobItem(
        title="Softwareentwickler (m/w/d) Python Vollzeit",
        company="Berlin Tech GmbH",
        url="https://berlintech.de/jobs/1",
        location="Berlin",
        description="Wir suchen einen erfahrenen Entwickler für unsere Softwarelösungen.",
        remote=True
    )

    scored_intern = score_job(good_intern)
    assert scored_intern.match_score >= 70
    assert scored_intern.match_label == "Strong match"

    filtered = filter_jobs([good_intern, good_remote, senior_role, unrelated_sales, foreign_german])
    assert good_intern in filtered
    assert good_remote in filtered
    assert senior_role not in filtered
    assert unrelated_sales not in filtered
    assert foreign_german not in filtered


def test_date_formatting_pkt():
    date_info = format_digest_date()
    assert "PKT" in date_info["time_pkt"]
    assert any(day in date_info["full_date"] for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
    assert len(date_info["iso_date"].split("-")) == 3
