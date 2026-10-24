"""News classification module mapping stories into core intelligence sectors."""
import re

CATEGORIES = [
    "Pakistan",
    "Global",
    "Wars & Geopolitics",
    "Finance & Economy",
    "Trade",
    "Technology / AI",
    "Science & Inventions"
]

KEYWORDS = {
    "Pakistan": [
        "pakistan", "islamabad", "karachi", "lahore", "peshawar", "quetta",
        "rawalpindi", "abbottabad", "multan", "faisalabad", "pakistani",
        "sbp", "state bank of pakistan", "fbr", "senate of pakistan",
        "national assembly", "shehbaz", "asif zardari"
    ],
    "Wars & Geopolitics": [
        "war", "military", "missile", "ceasefire", "conflict", "troops",
        "nato", "ukraine", "russia", "gaza", "israel", "iran", "syria",
        "lebanon", "geopolitics", "pentagon", "defense", "defence",
        "airstrike", "nuclear", "security council", "unsc", "sanctions"
    ],
    "Finance & Economy": [
        "finance", "economy", "economic", "inflation", "interest rate",
        "central bank", "banking", "stocks", "market", "currency", "rupee",
        "dollar", "investment", "recession", "gdp", "debt", "imf",
        "world bank", "federal reserve", "treasury", "bonds"
    ],
    "Trade": [
        "trade", "tariff", "tariffs", "export", "import", "customs",
        "supply chain", "shipping", "wto", "bilateral trade", "fta",
        "free trade", "freight", "cargo", "port", "logistics"
    ],
    "Technology / AI": [
        "artificial intelligence", "ai", "technology", "software", "chip",
        "semiconductor", "robot", "robotics", "cyber", "cybersecurity",
        "cloud", "microsoft", "google", "apple", "openai", "nvidia",
        "machine learning", "deep learning", "llm", "computing", "algorithm"
    ],
    "Science & Inventions": [
        "science", "scientific", "research", "discovery", "invention",
        "space", "nasa", "esa", "physics", "biology", "quantum",
        "experiment", "astronomy", "telescope", "climate science", "genetics",
        "cure", "breakthrough", "fusion", "james webb"
    ]
}

def categorize(title: str, description: str) -> str:
    """Categorize an article into one of the major digest intelligence sections."""
    text = f"{title} {description}".lower()
    
    scores = {}
    for c, ks in KEYWORDS.items():
        score = 0
        for k in ks:
            # Word boundary regex search
            matches = len(re.findall(r"\b" + re.escape(k) + r"\b", text))
            # Headline matches carry double weight
            title_matches = len(re.findall(r"\b" + re.escape(k) + r"\b", (title or "").lower()))
            score += matches + (title_matches * 2)
        scores[c] = score

    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    return "Global"
