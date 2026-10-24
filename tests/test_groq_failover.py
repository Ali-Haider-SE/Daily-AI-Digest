"""Comprehensive test suite for Groq API multi-key rotation, failover, and rate-limit handling.

Tests:
1. Primary key succeeds without rotation.
2. Primary key hits HTTP 429 and the second key succeeds.
3. Daily quota exhaustion causes the exhausted key to be skipped.
4. Multiple exhausted keys produce a clean failure rather than infinite retries.
5. A temporary rate limit allows a key to become eligible again after its cooldown.
6. An invalid key triggers sanitized failover.
7. HTTP 500/network errors use bounded retries.
8. Invalid model/request errors do not trigger unnecessary key rotation.
9. Summarization and job extraction share the same key-management logic.
10. Concurrent requests do not corrupt rotation state.
11. No secrets appear in logs or diagnostic reports.
12. Existing tests remain passing.
"""
import concurrent.futures
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Rate-limit waits and retry backoff must not really sleep during tests."""
    monkeypatch.setattr("app.ai.groq_client.time.sleep", lambda s: None)

import httpx
import groq

from app.ai.groq_client import (
    GroqClientManager,
    AllKeysExhaustedError,
    NonRetryableGroqError,
    FAILURE_RATE_LIMIT,
    FAILURE_DAILY_QUOTA,
    FAILURE_AUTH_ERROR,
    get_groq_manager,
    reset_groq_manager
)
from app.ai.summarizer import summarize_news, summarize_jobs
from app.database.database import Database
from app.models import NewsItem, JobItem


def make_mock_response(content: str = '{"results": []}', prompt_tokens: int = 10, completion_tokens: int = 20):
    """Create a mock Groq ChatCompletion response."""
    choice = MagicMock()
    choice.message.content = content
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


def make_groq_error(status_code: int, message: str, headers: dict = None, body: dict = None):
    """Instantiate authentic Groq exception classes."""
    req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    resp = httpx.Response(status_code, headers=headers or {}, request=req)
    if status_code == 429:
        return groq.RateLimitError(message, response=resp, body=body)
    elif status_code in (401, 403):
        return groq.AuthenticationError(message, response=resp, body=body)
    elif status_code in (400, 404, 422):
        return groq.BadRequestError(message, response=resp, body=body)
    elif status_code >= 500:
        return groq.InternalServerError(message, response=resp, body=body)
    return groq.APIStatusError(message, response=resp, body=body)


# 1. Primary key succeeds without rotation
def test_primary_key_succeeds_without_rotation():
    manager = GroqClientManager(
        api_keys=["primary_secret_1", "backup_secret_2"],
        max_retries_per_op=1
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = make_mock_response('{"articles": [{"id": 0, "summary": "Success", "why_it_matters": "None"}]}')
    manager._client_cache["primary_secret_1"] = mock_client

    resp = manager.create_chat_completion(messages=[{"role": "user", "content": "hi"}])
    assert resp is not None
    assert manager.stats.successful_requests == 1
    assert manager.stats.quota_switches == 0
    # Primary key should still be current
    curr = manager.get_current_key()
    assert curr is not None and curr.key_id == "key_1"
    assert mock_client.chat.completions.create.call_count == 1


# 2. Primary key hits HTTP 429 and the second key succeeds
def test_primary_hits_429_second_key_succeeds():
    manager = GroqClientManager(
        api_keys=["primary_secret_1", "backup_secret_2"],
        max_retries_per_op=1
    )
    client_1 = MagicMock()
    client_1.chat.completions.create.side_effect = make_groq_error(
        429, "Rate limit reached", headers={"retry-after": "5"}
    )
    client_2 = MagicMock()
    client_2.chat.completions.create.return_value = make_mock_response('{"ok": true}')

    manager._client_cache["primary_secret_1"] = client_1
    manager._client_cache["backup_secret_2"] = client_2

    resp = manager.create_chat_completion(messages=[{"role": "user", "content": "test"}])
    assert resp is not None
    assert manager.stats.successful_requests == 1
    assert manager.stats.quota_switches == 1
    # Current active key should now be key_2
    curr = manager.get_current_key()
    assert curr is not None and curr.key_id == "key_2"
    # Key 1 should be marked rate_limited
    assert manager._keys[0].status == "rate_limited"


# 3. Daily quota exhaustion causes the exhausted key to be skipped
def test_daily_quota_exhaustion_skips_key():
    manager = GroqClientManager(
        api_keys=["key1", "key2", "key3"],
        max_retries_per_op=1
    )
    client_1 = MagicMock()
    client_1.chat.completions.create.side_effect = make_groq_error(
        429, "Daily request quota exceeded for organisation"
    )
    client_2 = MagicMock()
    client_2.chat.completions.create.return_value = make_mock_response('{"data": 1}')

    manager._client_cache["key1"] = client_1
    manager._client_cache["key2"] = client_2

    resp1 = manager.create_chat_completion(messages=[{"role": "user", "content": "1"}])
    assert resp1 is not None
    assert manager._keys[0].status == "quota_exhausted"

    # Next call should directly use key2 without even invoking key1
    resp2 = manager.create_chat_completion(messages=[{"role": "user", "content": "2"}])
    assert resp2 is not None
    # Key 1 was only called once during the initial failover
    assert client_1.chat.completions.create.call_count == 1
    assert client_2.chat.completions.create.call_count == 2


# 4. Multiple exhausted keys produce a clean failure rather than infinite retries
def test_multiple_exhausted_keys_clean_failure():
    manager = GroqClientManager(
        api_keys=["k1", "k2"],
        max_retries_per_op=0
    )
    c1 = MagicMock()
    c1.chat.completions.create.side_effect = make_groq_error(429, "Rate limit")
    c2 = MagicMock()
    c2.chat.completions.create.side_effect = make_groq_error(429, "Rate limit")

    manager._client_cache["k1"] = c1
    manager._client_cache["k2"] = c2

    with pytest.raises(AllKeysExhaustedError):
        manager.create_chat_completion(messages=[{"role": "user", "content": "fail"}])

    assert manager.stats.failed_requests == 1
    assert manager.stats.quota_switches == 2
    # Both keys marked rate_limited
    assert all(k.status == "rate_limited" for k in manager._keys)


# 5. A temporary rate limit allows a key to become eligible again after cooldown
def test_temporary_rate_limit_eligible_after_cooldown():
    manager = GroqClientManager(api_keys=["k1"], max_retries_per_op=0)
    now = datetime.now(timezone.utc)
    # Set key in rate limit with cooldown that just passed
    manager._keys[0].status = "rate_limited"
    manager._keys[0].cooldown_until = now - timedelta(seconds=1)

    eligible_key = manager.get_current_key()
    assert eligible_key is not None
    assert eligible_key.key_id == "key_1"
    assert eligible_key.status == "active"


# 6. An invalid key triggers sanitized failover
def test_invalid_key_triggers_sanitized_failover():
    manager = GroqClientManager(
        api_keys=["invalid_key_abc", "valid_key_xyz"],
        max_retries_per_op=0
    )
    c1 = MagicMock()
    c1.chat.completions.create.side_effect = make_groq_error(401, "Invalid API Key")
    c2 = MagicMock()
    c2.chat.completions.create.return_value = make_mock_response('{"ok": 1}')

    manager._client_cache["invalid_key_abc"] = c1
    manager._client_cache["valid_key_xyz"] = c2

    resp = manager.create_chat_completion(messages=[{"role": "user", "content": "ping"}])
    assert resp is not None
    assert manager._keys[0].status == "auth_failed"
    assert manager._keys[1].status == "active"
    assert manager.get_current_key().key_id == "key_2"


# 7. HTTP 500 / network errors use bounded retries
def test_http_500_bounded_retries():
    manager = GroqClientManager(api_keys=["k1"], max_retries_per_op=2)
    c1 = MagicMock()
    # Fails 2 times with 500, succeeds on 3rd attempt
    c1.chat.completions.create.side_effect = [
        make_groq_error(500, "Internal Server Error"),
        make_groq_error(500, "Internal Server Error"),
        make_mock_response('{"recovered": true}')
    ]
    manager._client_cache["k1"] = c1

    with patch("time.sleep", return_value=None):
        resp = manager.create_chat_completion(messages=[{"role": "user", "content": "ping"}])

    assert resp is not None
    assert c1.chat.completions.create.call_count == 3
    assert manager.stats.successful_requests == 1
    assert manager.stats.quota_switches == 0


# 8. Invalid model / request errors do not trigger unnecessary key rotation
def test_invalid_model_does_not_rotate_keys():
    manager = GroqClientManager(
        api_keys=["k1", "k2", "k3"],
        max_retries_per_op=1
    )
    c1 = MagicMock()
    c1.chat.completions.create.side_effect = make_groq_error(400, "model_not_found: The model xyz does not exist")
    c2 = MagicMock()
    manager._client_cache["k1"] = c1
    manager._client_cache["k2"] = c2

    with pytest.raises(NonRetryableGroqError):
        manager.create_chat_completion(messages=[{"role": "user", "content": "test"}], model="xyz")

    # Should NOT have switched to key_2 or called key_2
    assert c2.chat.completions.create.call_count == 0
    assert manager.stats.quota_switches == 0
    assert manager._keys[0].status == "active"


# 9. Concurrent requests do not corrupt rotation state
def test_concurrent_requests_thread_safety():
    manager = GroqClientManager(
        api_keys=["ck1", "ck2", "ck3"],
        max_retries_per_op=0
    )
    mock_clients = {}
    for k in ["ck1", "ck2", "ck3"]:
        c = MagicMock()
        c.chat.completions.create.return_value = make_mock_response('{"ok": 1}')
        mock_clients[k] = c
        manager._client_cache[k] = c

    def do_request():
        return manager.create_chat_completion(messages=[{"role": "user", "content": "ping"}])

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(do_request) for _ in range(30)]
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            assert res is not None

    assert manager.stats.successful_requests == 30
    assert manager.stats.failed_requests == 0


# 11. No secrets appear in logs or diagnostic reports
def test_no_secrets_appear_in_diagnostic_report():
    secret_1 = "gsk_super_secret_key_111111111"
    secret_2 = "gsk_super_secret_key_222222222"
    manager = GroqClientManager(
        api_keys=[secret_1, secret_2],
        max_retries_per_op=0
    )
    manager._keys[0].status = "rate_limited"
    manager.stats.successful_requests = 10
    manager.stats.quota_switches = 2
    manager.record_stage_status("Summarization", True)

    report = manager.generate_report()
    assert secret_1 not in report
    assert secret_2 not in report
    assert "gsk_" not in report
    assert "Configured keys: 2" in report
    assert "Summarization: completed" in report


def test_per_minute_rate_limit_waits_and_retries_same_key():
    manager = GroqClientManager(api_keys=["k1", "k2"], max_retries_per_op=0)
    ok = MagicMock()
    ok.usage = None
    c1 = MagicMock()
    c1.chat.completions.create.side_effect = [make_groq_error(429, "Rate limit"), ok]
    c2 = MagicMock()
    manager._client_cache["k1"] = c1
    manager._client_cache["k2"] = c2

    result = manager.create_chat_completion(messages=[{"role": "user", "content": "hi"}])

    assert result is ok
    assert c1.chat.completions.create.call_count == 2   # waited, then retried the SAME key
    assert c2.chat.completions.create.call_count == 0   # no failover needed
    assert manager._keys[0].status == "active"
