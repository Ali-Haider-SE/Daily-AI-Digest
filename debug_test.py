"""Diagnostic tests for web server and main page.

Network operations are encapsulated in test functions and skipped if the local
server is not running, ensuring that ordinary pytest execution does not fail.
"""
import urllib.request
import pytest

def is_server_running(url: str = "http://127.0.0.1:8000/") -> bool:
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=1.0) as r:
            return r.status in (200, 404, 503)
    except Exception:
        return False

@pytest.mark.skipif(not is_server_running(), reason="Local server not running on http://127.0.0.1:8000")
def test_main_page():
    req = urllib.request.Request('http://127.0.0.1:8000/')
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.status == 200
        body = r.read().decode('utf-8')
        assert "Daily Intelligence Digest" in body
        assert "btn-translate-item" not in body
        assert "اردو میں پڑھیں" not in body

