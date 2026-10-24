"""Production-ready Flask Web Application for Daily Intelligence Digest."""
import logging
from pathlib import Path
from flask import Flask, render_template, request, jsonify, abort, send_from_directory

from app.config import settings
from app.database.database import Database
from app.email.renderer import format_digest_date

BASE = Path(__file__).resolve().parent.parent.parent

# Initialize Flask with explicit template and static paths
app = Flask(
    __name__,
    template_folder=str(BASE / "templates"),
    static_folder=str(BASE / "static"),
    static_url_path="/static"
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("digest_web")

CATEGORIES = [
    "Pakistan",
    "Scholarships & Schemes",
    "Global",
    "Wars & Geopolitics",
    "Finance & Economy",
    "Trade",
    "Technology / AI",
    "Science & Inventions"
]

def get_digest_payload(date_req=None):
    """Fetch structured digest from SQLite database or construct clean default state."""
    db = Database(settings.database_path)
    digest_data = None
    try:
        if date_req:
            digest_data = db.get_digest(date_req)
        if not digest_data:
            digest_data = db.get_latest_digest()
    finally:
        db.close()

    if not digest_data:
        date_info = format_digest_date()
        digest_data = {
            "date_full": date_info["full_date"],
            "time_pkt": date_info["time_pkt"],
            "iso_date": date_info["iso_date"],
            "top_stories": [],
            "news": {},
            "jobs": []
        }
    return digest_data

@app.route("/")
def index():
    """Render the latest intelligence digest."""
    return render_digest_page()

@app.route("/digest/<date_str>")
def view_digest(date_str):
    """Render a specific historical date's digest."""
    return render_digest_page(date_str)

def render_digest_page(date_req=None):
    digest_data = get_digest_payload(date_req)

    return render_template(
        "web_digest.html",
        date_full=digest_data.get("date_full"),
        time_pkt=digest_data.get("time_pkt"),
        iso_date=digest_data.get("iso_date"),
        top_stories=digest_data.get("top_stories", []),
        news=digest_data.get("news", {}),
        jobs=digest_data.get("jobs", []),
        categories=CATEGORIES,
    )

@app.errorhandler(404)
def not_found(e):
    return render_template(
        "web_digest.html",
        date_full="Resource Not Found",
        time_pkt="404",
        iso_date="",
        top_stories=[],
        news={},
        jobs=[],
        categories=[],
    ), 404

@app.errorhandler(500)
def server_error(e):
    logger.error(f"Internal server error: {e}")
    return jsonify({"error": "Internal Server Error"}), 500

def run_server(host: str = "127.0.0.1", port: int = 8000):
    """Run Flask WSGI development/production server."""
    print(f"[INFO] Daily Intelligence Digest Web Server listening on http://{host}:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    run_server(settings.web_host, settings.web_port)
