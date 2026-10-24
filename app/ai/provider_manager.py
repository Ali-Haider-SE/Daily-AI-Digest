"""Multi-Provider AI Client & Automatic Failover Manager.

Manages automatic failover across multiple LLM providers:
1. Groq (with multi-key rotation and rate-limit tracking)
2. Google Gemini API (using official google-genai SDK)
3. Mistral API (OpenAI-compatible chat completions)
4. Extensible for additional providers

Shared across summarization (news, jobs) with persistent
state, structured JSON support, sanitized logs, and usage token tracking.
"""
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any, Callable

import httpx

from app.ai.groq_client import (
    GroqClientManager,
    AllKeysExhaustedError,
    NonRetryableGroqError,
    get_groq_manager
)

logger = logging.getLogger("provider_manager")

# Standardized error types
ERR_RATE_LIMIT = "rate_limit"         # HTTP 429
ERR_DAILY_QUOTA = "daily_quota"       # Daily/organization limit exhausted
ERR_AUTH = "auth_error"               # HTTP 401/403
ERR_SERVER = "server_error"           # HTTP 5xx
ERR_NETWORK = "network_error"         # Timeout / connection
ERR_INVALID_REQ = "invalid_request"   # 400 / invalid model (non-retryable)

DEFAULT_RATE_LIMIT_COOLDOWN = 60          # 1 minute default
DEFAULT_DAILY_QUOTA_COOLDOWN = 3600 * 4   # 4 hours
DEFAULT_RETRY_BACKOFF = 1.5               # seconds base

@dataclass
class ProviderUsage:
    requests: int = 0
    successful: int = 0
    failed: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

@dataclass
class CompletionResult:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    provider: str = ""
    model: str = ""

    # Emulate OpenAI-like response object for backward compatibility
    @property
    def choices(self):
        class _Choice:
            def __init__(self, c):
                self.message = _Message(c)
        class _Message:
            def __init__(self, c):
                self.content = c
        return [_Choice(self.content)]

    @property
    def usage(self):
        class _Usage:
            def __init__(self, p, c):
                self.prompt_tokens = p
                self.completion_tokens = c
        return _Usage(self.prompt_tokens, self.completion_tokens)


class AllProvidersExhaustedError(Exception):
    """Raised when all configured AI providers are exhausted or unavailable."""
    pass


class AIProviderManager:
    """Orchestrates automatic fallback across configured AI providers."""

    def __init__(
        self,
        provider_priority: Optional[List[str]] = None,
        groq_manager: Optional[GroqClientManager] = None,
        gemini_api_key: str = "",
        gemini_model: str = "gemini-3.8-flash",
        mistral_api_key: str = "",
        mistral_model: str = "mistral-small-latest",
        max_retries_per_provider: int = 2,
        auto_failover: bool = True,
        db_path: Optional[Any] = None
    ):
        self._lock = threading.RLock()
        self.groq_manager = groq_manager or get_groq_manager(db_path=db_path)
        self.gemini_api_key = gemini_api_key.strip()
        self.gemini_model = gemini_model.strip() or "gemini-2.5-flash"
        self.mistral_api_key = mistral_api_key.strip()
        self.mistral_model = mistral_model.strip() or "mistral-small-latest"
        self.max_retries = max(0, max_retries_per_provider)
        self.auto_failover = auto_failover
        self.db_path = db_path

        # Raw priority list
        self.priority = provider_priority or ["groq", "gemini", "mistral"]

        # Provider cooldown and status tracking: {provider_name: {"status": ..., "cooldown_until": ...}}
        self._provider_status: Dict[str, Dict[str, Any]] = {}
        self.usage_by_provider: Dict[str, ProviderUsage] = {}
        self.provider_switches: int = 0
        self.stages_completed: List[str] = []
        self.stages_failed: List[str] = []

        self._restore_provider_states()

    def _get_db(self):
        if not self.db_path:
            return None
        try:
            from app.database.database import Database
            return Database(self.db_path)
        except Exception:
            return None

    def _restore_provider_states(self):
        """Restore cooldown / status from persistent SQLite db."""
        db = self._get_db()
        if not db:
            return
        try:
            states = db.get_all_provider_states()
            now = datetime.now(timezone.utc)
            with self._lock:
                for prov, rec in states.items():
                    status = rec.get("status", "active")
                    cd_str = rec.get("cooldown_until")
                    cd_dt = None
                    if cd_str:
                        try:
                            cd_dt = datetime.fromisoformat(cd_str)
                            if now >= cd_dt:
                                status = "active"
                                cd_dt = None
                        except Exception:
                            pass
                    self._provider_status[prov] = {
                        "status": status,
                        "cooldown_until": cd_dt,
                        "error_details": rec.get("error_details")
                    }
        except Exception as exc:
            logger.debug(f"Could not restore provider states from DB: {exc}")
        finally:
            try:
                db.close()
            except Exception:
                pass

    def _persist_provider_state(self, provider: str, status: str, failure_type: str, cooldown_until: Optional[datetime], detail: str):
        db = self._get_db()
        if not db:
            return
        try:
            db.set_provider_state(
                provider=provider,
                status=status,
                last_failure_type=failure_type,
                last_failure_time=datetime.now(timezone.utc).isoformat(),
                cooldown_until=cooldown_until.isoformat() if cooldown_until else None,
                error_details=detail
            )
        except Exception as exc:
            logger.debug(f"Could not persist provider state: {exc}")
        finally:
            try:
                db.close()
            except Exception:
                pass

    def is_provider_configured(self, provider: str) -> bool:
        """Check if required credentials are present for the given provider."""
        p = provider.lower()
        if p == "groq":
            return bool(self.groq_manager and self.groq_manager.key_count > 0)
        elif p == "gemini":
            return bool(self.gemini_api_key)
        elif p == "mistral":
            return bool(self.mistral_api_key)
        return False

    def is_provider_eligible(self, provider: str, now: Optional[datetime] = None) -> bool:
        """Check if provider is configured and not in cooldown."""
        if not self.is_provider_configured(provider):
            return False

        now_dt = now or datetime.now(timezone.utc)
        p = provider.lower()
        with self._lock:
            info = self._provider_status.get(p)
            if not info:
                return True
            status = info.get("status", "active")
            if status == "active":
                return True
            if status == "auth_failed":
                return False
            cd = info.get("cooldown_until")
            if cd and now_dt >= cd:
                info["status"] = "active"
                info["cooldown_until"] = None
                return True
            return False

    def mark_provider_failure(self, provider: str, failure_type: str, cooldown_secs: Optional[float], detail: str):
        p = provider.lower()
        with self._lock:
            now = datetime.now(timezone.utc)
            if failure_type == ERR_AUTH:
                status = "auth_failed"
                cd_dt = None
            elif failure_type in (ERR_RATE_LIMIT, ERR_DAILY_QUOTA):
                status = "quota_exhausted" if failure_type == ERR_DAILY_QUOTA else "rate_limited"
                secs = cooldown_secs if cooldown_secs is not None else (
                    DEFAULT_DAILY_QUOTA_COOLDOWN if failure_type == ERR_DAILY_QUOTA else DEFAULT_RATE_LIMIT_COOLDOWN
                )
                cd_dt = now + timedelta(seconds=secs)
            else:
                status = "cooldown"
                cd_dt = now + timedelta(seconds=cooldown_secs or 30)

            self._provider_status[p] = {
                "status": status,
                "cooldown_until": cd_dt,
                "error_details": detail
            }
            self._persist_provider_state(p, status, failure_type, cd_dt, detail)

    def _groq_cooldown_from_keys(self):
        """Use the real per-key cooldowns (e.g. 11s) instead of a blanket 4-hour provider cooldown."""
        now = datetime.now(timezone.utc)
        remaining = []
        daily = False
        for k in getattr(self.groq_manager, "_keys", []):
            cd = getattr(k, "cooldown_until", None)
            if cd and cd > now:
                remaining.append((cd - now).total_seconds())
                if getattr(k, "status", "") == "quota_exhausted":
                    daily = True
        if remaining:
            return (ERR_DAILY_QUOTA if daily else ERR_RATE_LIMIT), max(min(remaining), 5.0)
        return ERR_DAILY_QUOTA, DEFAULT_DAILY_QUOTA_COOLDOWN

    def _call_groq(self, messages: List[Dict[str, str]], model: Optional[str], **kwargs) -> CompletionResult:
        m = model or self.groq_manager.default_model
        resp = self.groq_manager.create_chat_completion(
            messages=messages,
            model=m,
            **kwargs
        )
        content = resp.choices[0].message.content or ""
        p_tokens = getattr(resp.usage, "prompt_tokens", 0) or 0
        c_tokens = getattr(resp.usage, "completion_tokens", 0) or 0
        return CompletionResult(content=content, prompt_tokens=p_tokens, completion_tokens=c_tokens, provider="groq", model=m)

    def _call_gemini(self, messages: List[Dict[str, str]], model: Optional[str], temperature: float = 0.2, max_completion_tokens: int = 750, **kwargs) -> CompletionResult:
        from google import genai
        from google.genai import types

        m = model or self.gemini_model
        client = genai.Client(api_key=self.gemini_api_key)

        # Convert OpenAI-style messages into Gemini prompt
        system_instruction = None
        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if role == "system":
                system_instruction = text
            elif role == "user":
                contents.append(text)
            elif role == "assistant":
                contents.append(text)

        full_prompt = "\n\n".join(contents)

        cfg_kwargs: Dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_completion_tokens,
        }
        if system_instruction:
            cfg_kwargs["system_instruction"] = system_instruction
        if kwargs.get("response_format") and kwargs["response_format"].get("type") == "json_object":
            cfg_kwargs["response_mime_type"] = "application/json"

        config = types.GenerateContentConfig(**cfg_kwargs)
        response = client.models.generate_content(
            model=m,
            contents=full_prompt,
            config=config
        )

        content = response.text or ""
        # Token usage if available
        usage_meta = getattr(response, "usage_metadata", None)
        p_tokens = getattr(usage_meta, "prompt_token_count", 0) if usage_meta else 0
        c_tokens = getattr(usage_meta, "candidates_token_count", 0) if usage_meta else 0

        return CompletionResult(content=content, prompt_tokens=p_tokens, completion_tokens=c_tokens, provider="gemini", model=m)

    def _call_openai_compatible(
        self,
        endpoint_url: str,
        api_key: str,
        provider_name: str,
        default_model: str,
        messages: List[Dict[str, str]],
        model: Optional[str],
        temperature: float = 0.2,
        max_completion_tokens: int = 750,
        response_format: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
        **kwargs
    ) -> CompletionResult:
        """Call Mistral or any standard OpenAI-compatible completions endpoint via httpx."""
        m = model or default_model
        payload: Dict[str, Any] = {
            "model": m,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_completion_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        with httpx.Client(timeout=timeout) as client:
            resp = client.post(endpoint_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices", [])
        if not choices:
            raise ValueError(f"No choices returned from {provider_name}")

        content = choices[0].get("message", {}).get("content", "") or ""
        usage = data.get("usage", {})
        p_tokens = usage.get("prompt_tokens", 0) or 0
        c_tokens = usage.get("completion_tokens", 0) or 0

        return CompletionResult(content=content, prompt_tokens=p_tokens, completion_tokens=c_tokens, provider=provider_name, model=m)

    def _call_mistral(self, messages: List[Dict[str, str]], model: Optional[str], **kwargs) -> CompletionResult:
        return self._call_openai_compatible(
            endpoint_url="https://api.mistral.ai/v1/chat/completions",
            api_key=self.mistral_api_key,
            provider_name="mistral",
            default_model=self.mistral_model,
            messages=messages,
            model=model,
            **kwargs
        )

    def _classify_provider_error(self, exc: Exception) -> tuple[str, Optional[float], str]:
        """Classify any exception from Gemini, Mistral, etc."""
        status_code = getattr(exc, "status_code", None)
        resp = getattr(exc, "response", None)
        if resp is not None and status_code is None:
            status_code = getattr(resp, "status_code", None)

        exc_str = str(exc).lower()
        headers = getattr(resp, "headers", {}) if resp else {}

        retry_after: Optional[float] = None
        for h_key in ["retry-after", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"]:
            val = headers.get(h_key)
            if val:
                try:
                    retry_after = max(float(str(val).strip().rstrip("s")), 1.0)
                    break
                except Exception:
                    pass

        if status_code in (401, 403) or "unauthenticated" in exc_str or "invalid api key" in exc_str:
            return ERR_AUTH, None, f"HTTP {status_code or 401}: Authentication failure"
        if status_code == 429 or "resourceexhausted" in exc_str or "rate limit" in exc_str or "quota" in exc_str:
            is_daily = any(q in exc_str for q in ["daily", "per day", "quota exceeded", "billing", "monthly"])
            if is_daily:
                return ERR_DAILY_QUOTA, retry_after or DEFAULT_DAILY_QUOTA_COOLDOWN, "Daily/organization quota exhausted"
            return ERR_RATE_LIMIT, retry_after or DEFAULT_RATE_LIMIT_COOLDOWN, f"HTTP 429: Rate limit (cooldown: {int(retry_after or DEFAULT_RATE_LIMIT_COOLDOWN)}s)"
        if status_code in (400, 404, 422) or "not found" in exc_str or "invalid model" in exc_str or "invalidargument" in exc_str:
            return ERR_INVALID_REQ, None, f"HTTP {status_code or 400}: Malformed request or model not found"
        if status_code and 500 <= status_code < 600 or "server error" in exc_str or "internal" in exc_str:
            return ERR_SERVER, None, f"HTTP {status_code}: Internal Server Error"
        if any(term in exc_str for term in ["timeout", "connection", "connect", "unreachable"]):
            return ERR_NETWORK, None, "Network/timeout failure"

        return ERR_SERVER, None, f"{type(exc).__name__}: {str(exc)[:120]}"

    def create_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        **kwargs
    ) -> CompletionResult:
        """Execute chat completion with automatic failover across providers."""
        now = datetime.now(timezone.utc)

        # Build list of eligible providers in priority order
        eligible = [p for p in self.priority if self.is_provider_eligible(p, now)]
        if not eligible:
            # Check configured
            configured = [p for p in self.priority if self.is_provider_configured(p)]
            if not configured:
                raise AllProvidersExhaustedError("No AI providers configured with valid credentials.")
            raise AllProvidersExhaustedError(
                f"All configured AI providers ({', '.join(configured)}) are currently exhausted or unavailable."
            )

        attempted_providers = []

        for prov_idx, provider in enumerate(eligible):
            attempted_providers.append(provider)
            p_usage = self.usage_by_provider.setdefault(provider, ProviderUsage())
            p_usage.requests += 1

            # Dispatcher
            call_fn: Optional[Callable] = None
            if provider == "groq":
                call_fn = lambda: self._call_groq(messages, model=model, **kwargs)
            elif provider == "gemini":
                call_fn = lambda: self._call_gemini(messages, model=model, **kwargs)
            elif provider == "mistral":
                call_fn = lambda: self._call_mistral(messages, model=model, **kwargs)
            else:
                logger.warning(f"Unsupported provider in priority: {provider}")
                continue

            # Bounded retry loop for transient failures
            provider_succeeded = False
            for attempt in range(self.max_retries + 1):
                try:
                    result = call_fn()
                    p_usage.successful += 1
                    p_usage.prompt_tokens += result.prompt_tokens
                    p_usage.completion_tokens += result.completion_tokens
                    provider_succeeded = True
                    return result

                except AllKeysExhaustedError as exc:
                    # Groq keys all exhausted
                    logger.warning(f"[Provider] All Groq keys exhausted. Failing over...")
                    _ftype, _cd = self._groq_cooldown_from_keys()
                    self.mark_provider_failure("groq", _ftype, _cd, str(exc))
                    p_usage.failed += 1
                    with self._lock:
                        self.provider_switches += 1
                    break  # break retry loop, move to next provider

                except NonRetryableGroqError as exc:
                    # Invalid model on Groq: do not rotate
                    p_usage.failed += 1
                    raise

                except Exception as exc:
                    ftype, cooldown_secs, detail = self._classify_provider_error(exc)

                    # Non-retryable invalid model / bad request: report configuration error
                    if ftype == ERR_INVALID_REQ:
                        logger.error(f"[Provider] Invalid request/model on {provider}: {detail}")
                        p_usage.failed += 1
                        self.mark_provider_failure(provider, ftype, None, detail)
                        if not self.auto_failover:
                            raise
                        # If auto failover is on, switch to next provider with clean log
                        with self._lock:
                            self.provider_switches += 1
                        break

                    # Rate limit or quota exhaustion: mark and fail over immediately
                    if ftype in (ERR_RATE_LIMIT, ERR_DAILY_QUOTA):
                        logger.warning(f"[Provider] {provider.upper()} quota/rate limit ({detail}). Failing over...")
                        p_usage.failed += 1
                        self.mark_provider_failure(provider, ftype, cooldown_secs, detail)
                        with self._lock:
                            self.provider_switches += 1
                        break

                    # Auth error: mark invalid and fail over
                    if ftype == ERR_AUTH:
                        logger.warning(f"[Provider] {provider.upper()} auth error ({detail}). Failing over...")
                        p_usage.failed += 1
                        self.mark_provider_failure(provider, ftype, None, detail)
                        with self._lock:
                            self.provider_switches += 1
                        break

                    # Transient server / network error: retry with backoff
                    if ftype in (ERR_SERVER, ERR_NETWORK):
                        if attempt < self.max_retries:
                            backoff = (2 ** attempt) * DEFAULT_RETRY_BACKOFF
                            logger.info(f"[Provider] Transient error on {provider} ({detail}), retry {attempt + 1}/{self.max_retries} in {backoff:.1f}s...")
                            time.sleep(backoff)
                            continue
                        else:
                            logger.warning(f"[Provider] {provider.upper()} retries exhausted ({detail}). Failing over...")
                            p_usage.failed += 1
                            self.mark_provider_failure(provider, ftype, 60, detail)
                            with self._lock:
                                self.provider_switches += 1
                            break

            if provider_succeeded:
                break

            if not self.auto_failover:
                raise AllProvidersExhaustedError(f"Provider {provider} failed and auto-failover is disabled.")

        raise AllProvidersExhaustedError(
            f"All attempted providers ({', '.join(attempted_providers)}) failed or were exhausted."
        )

    def record_stage_status(self, stage_name: str, success: bool):
        """Record stage completion status for report."""
        with self._lock:
            if success:
                if stage_name not in self.stages_completed:
                    self.stages_completed.append(stage_name)
                if stage_name in self.stages_failed:
                    self.stages_failed.remove(stage_name)
            else:
                if stage_name not in self.stages_failed:
                    self.stages_failed.append(stage_name)

    def generate_report(self) -> str:
        """Produce a comprehensive, sanitized diagnostic summary across all providers."""
        with self._lock:
            now = datetime.now(timezone.utc)
            lines = [
                "AI Provider Failover Report",
                "---------------------------",
                f"Configured priority: {', '.join(self.priority)}",
                f"Auto-failover enabled: {'yes' if self.auto_failover else 'no'}",
                f"Provider switches: {self.provider_switches}",
            ]

            lines.append("\nProvider Status:")
            for p in self.priority:
                is_cfg = self.is_provider_configured(p)
                if not is_cfg:
                    lines.append(f"  • {p.upper():<10}: not configured (requires API key)")
                    continue
                info = self._provider_status.get(p, {})
                status = info.get("status", "active")
                cd = info.get("cooldown_until")
                u = self.usage_by_provider.get(p, ProviderUsage())

                stat_label = status
                if cd and now < cd:
                    rem = int((cd - now).total_seconds())
                    stat_label = f"{status} (cooldown {rem}s)"
                elif p == "groq":
                    # Check individual Groq key counts
                    avail = sum(1 for k in self.groq_manager._keys if self.groq_manager._is_key_eligible(k, now))
                    stat_label = f"active ({avail}/{len(self.groq_manager._keys)} keys available)"

                lines.append(f"  • {p.upper():<10}: {stat_label} | Requests: {u.successful}/{u.requests} ok | Tokens: {u.prompt_tokens + u.completion_tokens}")

            lines.append("\nPipeline Stages:")
            for s in ["Summarization"]:
                if s in self.stages_completed:
                    lines.append(f"  • {s}: completed")
                elif s in self.stages_failed:
                    lines.append(f"  • {s}: failed")

            return "\n".join(lines)


# Global singleton
_global_provider_manager: Optional[AIProviderManager] = None
_prov_lock = threading.Lock()

def get_provider_manager(
    provider_priority: Optional[List[str]] = None,
    gemini_api_key: Optional[str] = None,
    gemini_model: Optional[str] = None,
    mistral_api_key: Optional[str] = None,
    mistral_model: Optional[str] = None,
    auto_failover: Optional[bool] = None,
    db_path: Optional[Any] = None
) -> AIProviderManager:
    """Get or initialize global AI provider manager."""
    global _global_provider_manager
    with _prov_lock:
        if _global_provider_manager is None:
            from app.config import settings
            resolved_prio = provider_priority or settings.provider_priority_list
            resolved_gemini_key = gemini_api_key if gemini_api_key is not None else settings.gemini_api_key
            resolved_gemini_model = gemini_model or settings.gemini_model
            resolved_mistral_key = mistral_api_key if mistral_api_key is not None else settings.mistral_api_key
            resolved_mistral_model = mistral_model or settings.mistral_model
            resolved_auto = auto_failover if auto_failover is not None else settings.ai_auto_failover
            resolved_db = db_path if db_path is not None else settings.database_path

            _global_provider_manager = AIProviderManager(
                provider_priority=resolved_prio,
                gemini_api_key=resolved_gemini_key,
                gemini_model=resolved_gemini_model,
                mistral_api_key=resolved_mistral_key,
                mistral_model=resolved_mistral_model,
                max_retries_per_provider=settings.ai_max_retries_per_provider,
                auto_failover=resolved_auto,
                db_path=resolved_db
            )
        return _global_provider_manager

def reset_provider_manager(
    provider_priority: Optional[List[str]] = None,
    groq_manager: Optional[GroqClientManager] = None,
    gemini_api_key: str = "",
    gemini_model: str = "gemini-3.8-flash",
    mistral_api_key: str = "",
    mistral_model: str = "mistral-small-latest",
    auto_failover: bool = True,
    db_path: Optional[Any] = None
) -> AIProviderManager:
    """Reset the global AI provider manager (useful for testing)."""
    global _global_provider_manager
    with _prov_lock:
        _global_provider_manager = AIProviderManager(
            provider_priority=provider_priority or ["groq", "gemini", "mistral"],
            groq_manager=groq_manager,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            mistral_api_key=mistral_api_key,
            mistral_model=mistral_model,
            auto_failover=auto_failover,
            db_path=db_path
        )
        return _global_provider_manager
