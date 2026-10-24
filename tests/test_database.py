"""Unit tests for SQLite database persistence and sent ledger."""
from pathlib import Path
from app.database.database import Database

def test_database_lifecycle(tmp_path: Path):
    db_file = tmp_path / "test_digest.db"
    db = Database(db_file)

    # Test sent ledger
    assert not db.already_sent("hash123")
    db.mark_sent("hash123", "news", "Test Headline", "https://example.com/1")
    assert db.already_sent("hash123")

    # Test digest catalog
    digest_data = {
        "date_full": "Wednesday, October 07, 2026",
        "time_pkt": "05:00 AM PKT",
        "iso_date": "2026-10-07",
        "top_stories": [],
        "news": {},
        "jobs": []
    }
    db.save_digest("2026-10-07", 10, 5, digest_data)
    retrieved = db.get_digest("2026-10-07")
    assert retrieved is not None
    assert retrieved["iso_date"] == "2026-10-07"
    assert retrieved["time_pkt"] == "05:00 AM PKT"

    latest = db.get_latest_digest()
    assert latest is not None
    assert latest["iso_date"] == "2026-10-07"

    db.close()
