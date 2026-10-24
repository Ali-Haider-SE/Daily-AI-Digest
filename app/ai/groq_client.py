"""Robust Multi-Account Groq API Client with Automatic Failover and Key Rotation.

Manages multiple Groq API keys with thread-safe rotation, quota/rate-limit tracking,
exponential backoff for transient errors, sanitized diagnostics, and persistent state.
"""
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any, Callable

logger = logging.getLogger("groq_client")

# Failure types
FAILURE_RATE_LIMIT = "rate_limit"         # HTTP 429
FAILURE_DAILY_QUOTA = "daily_quota"       # Daily limit / organization quota exhausted
FAILURE_AUTH_ERROR = "auth_error"         # HTTP 401 / 403
FAILURE_SERVER_ERROR = "server_error"     # HTTP 5xx
FAILURE_NETWORK_ERROR = "network_error"   # Connection / Timeout
FAILURE_INVALID_REQUEST = "invalid_req"   # Bad request / model error (no rotation)

# Default cooldowns (seconds)
DEFAULT_RATE_LIMIT_COOLDOWN = 60          # 1 minute if no header
DEFAULT_DAILY_QUOTA_COOLDOWN = 3600 * 4   # 4 hours
DEFAULT_SERVER_ERROR_BACKOFF = 2.0        # seconds base
# Per-minute (TPM/RPM) 429s clear within about a minute. Wait and retry the SAME key
# instead of failing over, so a short rate limit never becomes a long provider cooldown.
MAX_INLINE_RATE_LIMIT_WAIT = 120          # only wait inline when Groq asks for <= 120s
MAX_INLINE_RATE_LIMIT_RETRIES = 4         # waits per request before giving up on the key

@dataclass
class KeyInfo:
    key_id: str             # e.g., "key_1", "key_2"
    secret_key: str         # raw API key (never printed or exported in diagnostics)
    status: str = "active"  # "active", "rate_limited", "quota_exhausted", "auth_failed"
    last_failure_type: Optional[str] = None
    last_failure_time: Optional[datetime] = None
    cooldown_until: Optional[datetime] = None
    error_details: Optional[str] = None

@dataclass
class UsageStats:
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    quota_switches: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    stages_completed: List[str] = field(default_factory=list)
    stages_failed: List[str] = field(default_factory=list)

class AllKeysExhaustedError(Exception):
    """Raised when all configured Groq keys are exhausted or unavailable."""
    pass

class NonRetryableGroqError(Exception):
    """Raised for malformed requests or invalid models where cycling keys is not appropriate."""
    pass

class GroqClientManager:
    """Thread-safe manager for multi-account Groq API rotation and failover."""

    def __init__(
        self,
        api_keys: Optional[List[str]] = None,
        default_model: str = "qwen/qwen3.8-27b",
        max_retries_per_op: int = 2,
        db_path: Optional[Any] = None
    ):
        self._lock = threading.RLock()
        self.default_model = default_model
        self.max_retries_per_op = max(0, max_retries_per_op)
        self.db_path = db_path

        # Resolve configured keys
        resolved_keys = api_keys if api_keys is not None else []
        self._keys: List[KeyInfo] = []
        for idx, k in enumerate(resolved_keys, start=1):
            k_clean = str(k).strip()
            if k_clean:
                self._keys.append(KeyInfo(key_id=f"key_{idx}", secret_key=k_clean))

        self._active_index = 0
        self.stats = UsageStats()
        self._client_cache: Dict[str, Any] = {}

        # Restore states from database if available
        self._restore_states_from_db()

    @property
    def key_count(self) -> int:
        with self._lock:
            return len(self._keys)

    def _get_db_connection(self):
        if not self.db_path:
            return None
        try:
            from app.database.database import Database
            return Database(self.db_path)
        except Exception:
            return None

    def _restore_states_from_db(self):
        """Restore key state from persistent database if available."""
        if not self.db_path:
            return
        db = self._get_db_connection()
        if not db:
            return
        try:
            states = db.get_all_groq_key_states()
            now = datetime.now(timezone.utc)
            with self._lock:
                for k in self._keys:
                    rec = states.get(k.key_id)
                    if rec:
                        status = rec.get("status", "active")
                        cd_str = rec.get("cooldown_until")
                        cd_dt = None
                        if cd_str:
                            try:
                                cd_dt = datetime.fromisoformat(cd_str)
                            except Exception:
                                pass
                        
                        # Check if cooldown has expired
                        if cd_dt and now >= cd_dt:
                            status = "active"
                            cd_dt = None

                        k.status = status
                        k.last_failure_type = rec.get("last_failure_type")
                        k.cooldown_until = cd_dt
                        k.error_details = rec.get("error_details")
        except Exception as exc:
            logger.debug(f"Could not restore Groq key states from DB: {exc}")
        finally:
            try:
                db.close()
            except Exception:
                pass

    def _persist_key_state(self, key_info: KeyInfo):
        """Persist key state to SQLite database."""
        if not self.db_path:
            return
        db = self._get_db_connection()
        if not db:
            return
        try:
            db.set_groq_key_state(
                key_id=key_info.key_id,
                status=key_info.status,
                last_failure_type=key_info.last_failure_type,
                last_failure_time=key_info.last_failure_time.isoformat() if key_info.last_failure_time else None,
                cooldown_until=key_info.cooldown_until.isoformat() if key_info.cooldown_until else None,
                error_details=key_info.error_details
            )
        except Exception as exc:
            logger.debug(f"Could not persist Groq key state for {key_info.key_id}: {exc}")
        finally:
            try:
                db.close()
            except Exception:
                pass

    def _is_key_eligible(self, k: KeyInfo, now: datetime) -> bool:
        if k.status == "active":
            return True
        if k.status == "auth_failed":
            return False  # Permanent invalid key until reset
        if k.cooldown_until:
            if now >= k.cooldown_until:
                k.status = "active"
                k.cooldown_until = None
                self._persist_key_state(k)
                return True
            return False
        return False

    def get_current_key(self) -> Optional[KeyInfo]:
        """Return the current eligible key, or rotate to the next available key."""
        with self._lock:
            if not self._keys:
                return None
            now = datetime.now(timezone.utc)
            # Check current active index first
            curr = self._keys[self._active_index % len(self._keys)]
            if self._is_key_eligible(curr, now):
                return curr

            # Search forward for next eligible key
            total = len(self._keys)
            for i in range(1, total + 1):
                idx = (self._active_index + i) % total
                candidate = self._keys[idx]
                if self._is_key_eligible(candidate, now):
                    self._active_index = idx
                    return candidate

            return None

    def _get_underlying_client(self, secret_key: str):
        if secret_key in self._client_cache:
            return self._client_cache[secret_key]
        try:
            from groq import Groq
            # max_retries=0 so GroqClientManager handles retries and rotation explicitly
            client = Groq(api_key=secret_key, max_retries=0)
            self._client_cache[secret_key] = client
            return client
        except Exception as exc:
            logger.warning(f"Failed to instantiate Groq SDK: {exc}")
            raise

    def parse_error(self, exc: Exception) -> tuple[str, Optional[float], str]:
        """Classify Groq exception into failure type, cooldown seconds, and sanitized description.
        
        Returns: (failure_type, cooldown_seconds_or_none, sanitized_summary)
        """
        status_code = getattr(exc, "status_code", None)
        exc_str = str(exc).lower()
        resp = getattr(exc, "response", None)
        headers = getattr(resp, "headers", {}) if resp else {}

        # Parse retry-after header if present
        retry_after: Optional[float] = None
        for h_key in ["retry-after", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"]:
            val = headers.get(h_key)
            if val:
                try:
                    val_str = str(val).strip().rstrip("s")
                    retry_after = max(float(val_str), 1.0)
                    break
                except (ValueError, TypeError):
                    pass

        # 1. Authentication / Permission errors (HTTP 401, 403)
        if status_code in (401, 403) or "authentication" in exc_str or "invalid api key" in exc_str:
            return FAILURE_AUTH_ERROR, None, f"HTTP {status_code or 401}: Authentication/Authorization failure"

        # 2. Rate limit or quota exhaustion (HTTP 429)
        if status_code == 429 or "rate limit" in exc_str or "quota" in exc_str:
            # Check if this is a daily quota or token-per-day exhaustion
            # NOTE: Groq's per-minute 429 messages also contain "settings/billing" (upgrade hint),
            # so "billing" must NOT count as a daily-quota marker. Explicit per-minute wording wins.
            is_per_minute = any(q in exc_str for q in ["per minute", "(tpm)", "(rpm)", "per second"])
            is_daily = (not is_per_minute) and any(
                q in exc_str for q in ["daily", "per day", "(tpd)", "(rpd)", "quota exceeded", "monthly"]
            )
            if is_daily:
                cd = retry_after if retry_after else DEFAULT_DAILY_QUOTA_COOLDOWN
                return FAILURE_DAILY_QUOTA, cd, "Daily/Organization quota exhausted"
            else:
                cd = retry_after if retry_after else DEFAULT_RATE_LIMIT_COOLDOWN
                return FAILURE_RATE_LIMIT, cd, f"HTTP 429: Rate limit reached (cooldown: {int(cd)}s)"

        # 3. Model not found or malformed request (HTTP 400, 404, 422)
        if status_code in (400, 404, 422) or "model_not_found" in exc_str or "invalid request" in exc_str:
            return FAILURE_INVALID_REQUEST, None, f"HTTP {status_code or 400}: Malformed request / Invalid model"

        # 4. Server errors (HTTP 5xx)
        if status_code and 500 <= status_code < 600 or "internal server error" in exc_str:
            return FAILURE_SERVER_ERROR, None, f"HTTP {status_code}: Internal Server Error"

        # 5. Connection / Network / Timeout errors
        conn_terms = ["connection", "timeout", "timed out", "unreachable", "name resolution"]
        if any(c in exc_str for c in conn_terms):
            return FAILURE_NETWORK_ERROR, None, "Network connection or timeout failure"

        # Default fallback
        return FAILURE_SERVER_ERROR, None, f"API error: {type(exc).__name__}"

    def mark_key_failure(self, key_id: str, failure_type: str, cooldown_secs: Optional[float], detail: str):
        """Update key state in memory and persistence."""
        with self._lock:
            now = datetime.now(timezone.utc)
            for k in self._keys:
                if k.key_id == key_id:
                    k.last_failure_type = failure_type
                    k.last_failure_time = now
                    k.error_details = detail

                    if failure_type == FAILURE_AUTH_ERROR:
                        k.status = "auth_failed"
                        k.cooldown_until = None
                    elif failure_type == FAILURE_DAILY_QUOTA:
                        k.status = "quota_exhausted"
                        cd = cooldown_secs if cooldown_secs is not None else DEFAULT_DAILY_QUOTA_COOLDOWN
                        k.cooldown_until = now + timedelta(seconds=cd)
                    elif failure_type == FAILURE_RATE_LIMIT:
                        k.status = "rate_limited"
                        cd = cooldown_secs if cooldown_secs is not None else DEFAULT_RATE_LIMIT_COOLDOWN
                        k.cooldown_until = now + timedelta(seconds=cd)
                    
                    self._persist_key_state(k)
                    break

    def create_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_completion_tokens: int = 750,
        response_format: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Any:
        """Execute a chat completion request with automatic key failover and safe retries."""
        model_name = model or self.default_model

        with self._lock:
            self.stats.total_requests += 1

        if not self._keys:
            with self._lock:
                self.stats.failed_requests += 1
            raise AllKeysExhaustedError("No Groq API keys configured.")

        # Set of key IDs attempted during this operation to prevent infinite loops
        attempted_keys = set()

        while True:
            current_key = self.get_current_key()
            if not current_key or current_key.key_id in attempted_keys:
                with self._lock:
                    self.stats.failed_requests += 1
                raise AllKeysExhaustedError(
                    f"All configured Groq keys ({len(self._keys)}) are exhausted or unavailable."
                )

            key_id = current_key.key_id
            secret = current_key.secret_key
            client = self._get_underlying_client(secret)

            # Bounded retry loop for transient network/server errors on THIS key
            transient_retries = self.max_retries_per_op
            switch_to_next_key = False

            attempt = 0
            rate_limit_waits = 0
            while attempt <= transient_retries:
                try:
                    call_kwargs: Dict[str, Any] = {
                        "model": model_name,
                        "messages": messages,
                        "temperature": temperature,
                        "max_completion_tokens": max_completion_tokens,
                    }
                    if response_format:
                        call_kwargs["response_format"] = response_format
                    call_kwargs.update(kwargs)

                    response = client.chat.completions.create(**call_kwargs)

                    # Success: record tokens and return
                    with self._lock:
                        self.stats.successful_requests += 1
                        usage = getattr(response, "usage", None)
                        if usage:
                            pt = getattr(usage, "prompt_tokens", 0) or 0
                            ct = getattr(usage, "completion_tokens", 0) or 0
                            self.stats.total_prompt_tokens += pt
                            self.stats.total_completion_tokens += ct

                    return response

                except Exception as exc:
                    ftype, cooldown_secs, detail = self.parse_error(exc)

                    # 1. Invalid model / request: DO NOT rotate keys!
                    if ftype == FAILURE_INVALID_REQUEST:
                        logger.error(f"[Groq] Non-retryable request error on {key_id}: {detail}")
                        with self._lock:
                            self.stats.failed_requests += 1
                        raise NonRetryableGroqError(f"Groq request rejected ({detail})") from exc

                    # 2a. Short per-minute rate limit: wait it out and retry the same key
                    if (
                        ftype == FAILURE_RATE_LIMIT
                        and cooldown_secs is not None
                        and cooldown_secs <= MAX_INLINE_RATE_LIMIT_WAIT
                        and rate_limit_waits < MAX_INLINE_RATE_LIMIT_RETRIES
                    ):
                        rate_limit_waits += 1
                        wait_s = cooldown_secs + 2
                        logger.warning(
                            f"[Groq] Per-minute rate limit on {key_id}. Waiting {wait_s:.0f}s "
                            f"then retrying (wait {rate_limit_waits}/{MAX_INLINE_RATE_LIMIT_RETRIES})..."
                        )
                        print(f"[Groq] Rate limit hit, waiting {wait_s:.0f}s and retrying ({rate_limit_waits}/{MAX_INLINE_RATE_LIMIT_RETRIES})...")
                        time.sleep(wait_s)
                        continue

                    # 2b. Daily quota (or repeated rate limit): mark key and rotate immediately!
                    if ftype in (FAILURE_RATE_LIMIT, FAILURE_DAILY_QUOTA):
                        logger.warning(f"[Groq] Quota/Rate limit on {key_id} ({detail}). Failing over...")
                        self.mark_key_failure(key_id, ftype, cooldown_secs, detail)
                        with self._lock:
                            self.stats.quota_switches += 1
                        attempted_keys.add(key_id)
                        switch_to_next_key = True
                        break  # Break inner retry loop to try next key

                    # 3. Authentication / Invalid key: mark key invalid and rotate immediately
                    if ftype == FAILURE_AUTH_ERROR:
                        logger.warning(f"[Groq] Authentication error on {key_id} ({detail}). Failing over...")
                        self.mark_key_failure(key_id, ftype, None, detail)
                        with self._lock:
                            self.stats.quota_switches += 1
                        attempted_keys.add(key_id)
                        switch_to_next_key = True
                        break  # Break inner loop to try next key

                    # 4. Transient network / 5xx error: bounded retry with backoff
                    if ftype in (FAILURE_SERVER_ERROR, FAILURE_NETWORK_ERROR):
                        if attempt < transient_retries:
                            backoff = (2 ** attempt) * DEFAULT_SERVER_ERROR_BACKOFF
                            logger.info(f"[Groq] Transient error on {key_id} ({detail}), retry {attempt + 1}/{transient_retries} in {backoff:.1f}s...")
                            time.sleep(backoff)
                            attempt += 1
                            continue
                        else:
                            # Transient retries exhausted for this key, failover to next key if available
                            logger.warning(f"[Groq] Transient retries exhausted on {key_id} ({detail}). Failing over...")
                            self.mark_key_failure(key_id, ftype, 30, detail)
                            attempted_keys.add(key_id)
                            switch_to_next_key = True
                            break

            if switch_to_next_key:
                continue

    def record_stage_status(self, stage_name: str, success: bool):
        """Record stage completion status for diagnostic report."""
        with self._lock:
            if success:
                if stage_name not in self.stats.stages_completed:
                    self.stats.stages_completed.append(stage_name)
                if stage_name in self.stats.stages_failed:
                    self.stats.stages_failed.remove(stage_name)
            else:
                if stage_name not in self.stats.stages_failed:
                    self.stats.stages_failed.append(stage_name)

    def generate_report(self) -> str:
        """Produce a sanitized diagnostic report suitable for console output and logs."""
        with self._lock:
            now = datetime.now(timezone.utc)
            keys_total = len(self._keys)
            keys_avail = sum(1 for k in self._keys if self._is_key_eligible(k, now))
            keys_rl = sum(1 for k in self._keys if k.status == "rate_limited" and not self._is_key_eligible(k, now))
            keys_qd = sum(1 for k in self._keys if k.status == "quota_exhausted" and not self._is_key_eligible(k, now))
            keys_auth = sum(1 for k in self._keys if k.status == "auth_failed")

            lines = [
                "Groq API report",
                "---------------",
                f"Configured keys: {keys_total}",
                f"Keys available: {keys_avail}",
                f"Keys rate-limited: {keys_rl + keys_qd}",
                f"Keys with authentication errors: {keys_auth}",
                f"Successful requests: {self.stats.successful_requests}",
                f"Quota-related switches: {self.stats.quota_switches}",
                f"Failed requests: {self.stats.failed_requests}",
            ]

            # Stage statuses
            all_stages = set(self.stats.stages_completed + self.stats.stages_failed)
            # Standard order if present
            ordered_stages = ["Summarization"]
            for s in ordered_stages:
                if s in self.stats.stages_completed:
                    lines.append(f"{s}: completed")
                elif s in self.stats.stages_failed:
                    lines.append(f"{s}: failed")

            for s in sorted(all_stages):
                if s not in ordered_stages:
                    status = "completed" if s in self.stats.stages_completed else "failed"
                    lines.append(f"{s}: {status}")

            if self.stats.total_prompt_tokens > 0 or self.stats.total_completion_tokens > 0:
                lines.append(f"Prompt tokens recorded: {self.stats.total_prompt_tokens}")
                lines.append(f"Completion tokens recorded: {self.stats.total_completion_tokens}")

            return "\n".join(lines)


# Global singleton instance for shared key state across summarization and web endpoints
_global_groq_manager: Optional[GroqClientManager] = None
_manager_lock = threading.Lock()

def get_groq_manager(
    api_keys: Optional[List[str]] = None,
    model: Optional[str] = None,
    max_retries: Optional[int] = None,
    db_path: Optional[Any] = None
) -> GroqClientManager:
    """Get or initialize the shared global Groq client manager."""
    global _global_groq_manager
    with _manager_lock:
        if _global_groq_manager is None:
            from app.config import settings
            resolved_keys = api_keys if api_keys is not None else settings.groq_api_keys
            resolved_model = model or settings.groq_model
            resolved_retries = max_retries if max_retries is not None else settings.groq_max_retries_per_op
            resolved_db = db_path if db_path is not None else settings.database_path

            _global_groq_manager = GroqClientManager(
                api_keys=resolved_keys,
                default_model=resolved_model,
                max_retries_per_op=resolved_retries,
                db_path=resolved_db
            )
        return _global_groq_manager

def reset_groq_manager(
    api_keys: Optional[List[str]] = None,
    model: Optional[str] = None,
    max_retries: Optional[int] = None,
    db_path: Optional[Any] = None
) -> GroqClientManager:
    """Reset the shared global Groq client manager (useful for testing or re-configuration)."""
    global _global_groq_manager
    with _manager_lock:
        _global_groq_manager = GroqClientManager(
            api_keys=api_keys if api_keys is not None else [],
            default_model=model or "qwen/qwen3.8-27b",
            max_retries_per_op=max_retries if max_retries is not None else 2,
            db_path=db_path
        )
        return _global_groq_manager
