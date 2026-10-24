"""Comprehensive web application test suite covering Flask endpoints, static assets, and 404 handling."""
import pytest
from app.web.application import app

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_web_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.content_type.startswith("text/html")
    assert b"Daily Intelligence Digest" in response.data

def test_web_digest_date(client):
    response = client.get("/digest/2026-10-07")
    assert response.status_code == 200
    assert response.content_type.startswith("text/html")
    assert b"2026-10-07" in response.data or b"PKT" in response.data

def test_web_static_css(client):
    response = client.get("/static/css/dashboard.css")
    assert response.status_code == 200
    assert "text/css" in response.content_type

def test_web_static_js(client):
    response = client.get("/static/js/dashboard.js")
    assert response.status_code == 200
    assert "javascript" in response.content_type

def test_web_not_found(client):
    response = client.get("/nonexistent/endpoint/12345")
    assert response.status_code == 404
    assert response.content_type.startswith("text/html")
