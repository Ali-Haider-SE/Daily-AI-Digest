"""Database persistence module for intelligence items, jobs, and digests."""
import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with self.conn:
            # Sent items / deduplication ledger
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS sent_items (
                    content_hash TEXT PRIMARY KEY,
                    item_type TEXT,
                    title TEXT,
                    url TEXT,
                    sent_at TEXT NOT NULL
                )
            """)
            
            # Historical digests catalog
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS digests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    digest_date TEXT UNIQUE,
                    generated_at TEXT NOT NULL,
                    news_count INTEGER DEFAULT 0,
                    jobs_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    email_status TEXT DEFAULT 'unsent',
                    digest_json TEXT
                )
            """)
            
            # Groq key failover & quota state tracking
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS groq_key_state (
                    key_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'active',
                    last_failure_type TEXT,
                    last_failure_time TEXT,
                    cooldown_until TEXT,
                    error_details TEXT,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # Multi-provider failover & quota state tracking
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_provider_state (
                    provider TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'active',
                    last_failure_type TEXT,
                    last_failure_time TEXT,
                    cooldown_until TEXT,
                    error_details TEXT,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # Indexes
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_sent_hash ON sent_items(content_hash)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_digest_date ON digests(digest_date)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_groq_key_id ON groq_key_state(key_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_provider ON ai_provider_state(provider)")

    def already_sent(self, content_hash: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM sent_items WHERE content_hash=?", (content_hash,))
        return cur.fetchone() is not None

    def mark_sent(self, content_hash: str, item_type: str, title: str, url: str):
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO sent_items (content_hash, item_type, title, url, sent_at) VALUES (?, ?, ?, ?, ?)",
                (content_hash, item_type, title, url, datetime.now(timezone.utc).isoformat())
            )

    def save_digest(self, digest_date: str, news_count: int, jobs_count: int, digest_data: Dict[str, Any], status: str = "completed", email_status: str = "sent"):
        with self.conn:
            self.conn.execute("""
                INSERT INTO digests (digest_date, generated_at, news_count, jobs_count, status, email_status, digest_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(digest_date) DO UPDATE SET
                    generated_at=excluded.generated_at,
                    news_count=excluded.news_count,
                    jobs_count=excluded.jobs_count,
                    status=excluded.status,
                    email_status=excluded.email_status,
                    digest_json=excluded.digest_json
            """, (
                digest_date,
                datetime.now(timezone.utc).isoformat(),
                news_count,
                jobs_count,
                status,
                email_status,
                json.dumps(digest_data)
            ))

    def get_digest(self, digest_date: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.execute("SELECT * FROM digests WHERE digest_date=?", (digest_date,))
        row = cur.fetchone()
        if row and row["digest_json"]:
            return json.loads(row["digest_json"])
        return None

    def get_latest_digest(self) -> Optional[Dict[str, Any]]:
        cur = self.conn.execute("SELECT * FROM digests ORDER BY digest_date DESC LIMIT 1")
        row = cur.fetchone()
        if row and row["digest_json"]:
            return json.loads(row["digest_json"])
        return None

    def get_groq_key_state(self, key_id: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.execute("SELECT * FROM groq_key_state WHERE key_id=?", (key_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def set_groq_key_state(
        self,
        key_id: str,
        status: str,
        last_failure_type: Optional[str] = None,
        last_failure_time: Optional[str] = None,
        cooldown_until: Optional[str] = None,
        error_details: Optional[str] = None
    ):
        with self.conn:
            self.conn.execute("""
                INSERT INTO groq_key_state (key_id, status, last_failure_type, last_failure_time, cooldown_until, error_details, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key_id) DO UPDATE SET
                    status=excluded.status,
                    last_failure_type=excluded.last_failure_type,
                    last_failure_time=excluded.last_failure_time,
                    cooldown_until=excluded.cooldown_until,
                    error_details=excluded.error_details,
                    updated_at=excluded.updated_at
            """, (
                key_id,
                status,
                last_failure_type,
                last_failure_time,
                cooldown_until,
                error_details,
                datetime.now(timezone.utc).isoformat()
            ))

    def get_all_groq_key_states(self) -> Dict[str, Dict[str, Any]]:
        cur = self.conn.execute("SELECT * FROM groq_key_state")
        rows = cur.fetchall()
        return {r["key_id"]: dict(r) for r in rows}

    def get_provider_state(self, provider: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.execute("SELECT * FROM ai_provider_state WHERE provider=?", (provider,))
        row = cur.fetchone()
        return dict(row) if row else None

    def set_provider_state(
        self,
        provider: str,
        status: str,
        last_failure_type: Optional[str] = None,
        last_failure_time: Optional[str] = None,
        cooldown_until: Optional[str] = None,
        error_details: Optional[str] = None
    ):
        with self.conn:
            self.conn.execute("""
                INSERT INTO ai_provider_state (provider, status, last_failure_type, last_failure_time, cooldown_until, error_details, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET
                    status=excluded.status,
                    last_failure_type=excluded.last_failure_type,
                    last_failure_time=excluded.last_failure_time,
                    cooldown_until=excluded.cooldown_until,
                    error_details=excluded.error_details,
                    updated_at=excluded.updated_at
            """, (
                provider,
                status,
                last_failure_type,
                last_failure_time,
                cooldown_until,
                error_details,
                datetime.now(timezone.utc).isoformat()
            ))

    def get_all_provider_states(self) -> Dict[str, Dict[str, Any]]:
        cur = self.conn.execute("SELECT * FROM ai_provider_state")
        rows = cur.fetchall()
        return {r["provider"]: dict(r) for r in rows}

    def close(self):
        self.conn.close()
