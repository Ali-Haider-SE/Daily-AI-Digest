from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv(override=True)
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

@dataclass(frozen=True)
class Settings:
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_app_password: str = os.getenv("SMTP_APP_PASSWORD", "")
    email_from: str = os.getenv("EMAIL_FROM", "")
    email_to: str = os.getenv("EMAIL_TO", "")
    
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_api_key_2: str = os.getenv("GROQ_API_KEY_2", "")
    groq_api_key_3: str = os.getenv("GROQ_API_KEY_3", "")
    groq_api_key_4: str = os.getenv("GROQ_API_KEY_4", "")
    groq_model: str = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
    groq_max_retries_per_op: int = int(os.getenv("GROQ_MAX_RETRIES_PER_OP", "2"))

    # Multi-Provider Failover Settings
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    mistral_api_key: str = os.getenv("MISTRAL_API_KEY", "")
    mistral_model: str = os.getenv("MISTRAL_MODEL", "mistral-small-latest")

    ai_provider_priority: str = os.getenv("AI_PROVIDER_PRIORITY", "groq,gemini,mistral")
    ai_auto_failover: bool = os.getenv("AI_AUTO_FAILOVER", "true").lower() in ("true", "1", "yes")
    ai_max_retries_per_provider: int = int(os.getenv("AI_MAX_RETRIES_PER_PROVIDER", "2"))

    @property
    def provider_priority_list(self) -> list:
        """Return parsed lowercase list of configured provider priorities."""
        raw = self.ai_provider_priority or "groq,gemini,mistral"
        return [p.strip().lower() for p in raw.split(",") if p.strip()]

    @property
    def groq_api_keys(self) -> list:
        """Return list of non-empty configured Groq API keys in order (primary first)."""
        keys = []
        for candidate in [self.groq_api_key, self.groq_api_key_2, self.groq_api_key_3, self.groq_api_key_4]:
            cand = candidate.strip() if candidate else ""
            if cand and cand not in keys:
                keys.append(cand)
        # Also discover any GROQ_API_KEY_N in env beyond 4 if configured
        i = 5
        while True:
            extra = os.getenv(f"GROQ_API_KEY_{i}", "").strip()
            if not extra:
                break
            if extra not in keys:
                keys.append(extra)
            i += 1
        return keys
    
    news_api_key: str = os.getenv("NEWS_API_KEY", "")
    

    database_path: Path = Path(os.getenv("DATABASE_PATH", str(DATA_DIR / "digest.db")))
    request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "20"))
    max_news_items: int = int(os.getenv("MAX_NEWS_ITEMS", "150"))
    max_job_items: int = int(os.getenv("MAX_JOB_ITEMS", "100"))
    max_scholarship_items: int = int(os.getenv("MAX_SCHOLARSHIP_ITEMS", "10"))
    min_credibility_score: int = int(os.getenv("MIN_CREDIBILITY_SCORE", "55"))
    top_stories_count: int = int(os.getenv("TOP_STORIES_COUNT", "5"))
    
    # Web server and public link settings
    web_host: str = os.getenv("WEB_HOST", "127.0.0.1")
    web_port: int = int(os.getenv("WEB_PORT", "8000"))
    # PUBLIC_BASE_URL is prioritized for email links, with web_base_url as fallback.
    # Must use non-empty string or fallback to web_base_url so links never resolve to hostless "digest/...".
    public_base_url: str = (os.getenv("PUBLIC_BASE_URL") or "").strip() or os.getenv("WEB_BASE_URL", "http://127.0.0.1:8000")
    web_base_url: str = os.getenv("WEB_BASE_URL", "http://127.0.0.1:8000")

settings = Settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
