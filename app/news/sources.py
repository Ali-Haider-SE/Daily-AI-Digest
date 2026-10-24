"""News sources registry with credibility baselines, categories, and country relevance."""

RSS_SOURCES = [
    {
        "name": "Dawn",
        "url": "https://www.dawn.com/feeds/home",
        "credibility": 90,
        "region": "Pakistan",
        "category": "Pakistan"
    },
    {
        "name": "Dawn Business",
        "url": "https://www.dawn.com/feeds/business",
        "credibility": 90,
        "region": "Pakistan",
        "category": "Finance & Economy"
    },
    {
        "name": "The Guardian World",
        "url": "https://www.theguardian.com/world/rss",
        "credibility": 92,
        "region": "Global",
        "category": "Global"
    },
    {
        "name": "The Guardian Tech",
        "url": "https://www.theguardian.com/technology/rss",
        "credibility": 90,
        "region": "Global",
        "category": "Technology / AI"
    },
    {
        "name": "The Guardian Business",
        "url": "https://www.theguardian.com/uk/business/rss",
        "credibility": 90,
        "region": "Global",
        "category": "Finance & Economy"
    },
    {
        "name": "TechCrunch",
        "url": "https://techcrunch.com/feed/",
        "credibility": 85,
        "region": "Global",
        "category": "Technology / AI"
    },
    {
        "name": "Ars Technica",
        "url": "https://feeds.arstechnica.com/arstechnica/index",
        "credibility": 85,
        "region": "Global",
        "category": "Technology / AI"
    },
    {
        "name": "MIT Technology Review",
        "url": "https://www.technologyreview.com/feed/",
        "credibility": 90,
        "region": "Global",
        "category": "Technology / AI"
    },
    {
        "name": "NASA Breaking News",
        "url": "https://www.nasa.gov/rss/dyn/breaking_news.rss",
        "credibility": 95,
        "region": "Global",
        "category": "Science & Inventions"
    },
    {
        "name": "BBC News",
        "url": "https://feeds.bbci.co.uk/news/rss.xml",
        "credibility": 92,
        "region": "Global",
        "category": "Global"
    },
    {
        "name": "BBC World",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "credibility": 92,
        "region": "Global",
        "category": "Global"
    },
    {
        "name": "Al Jazeera",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "credibility": 88,
        "region": "Middle East / Global",
        "category": "Wars & Geopolitics"
    }
]

# For backwards compatibility
RSS_FEEDS = [(s["name"], s["url"]) for s in RSS_SOURCES]
