"""Quick fix script: test Gemini and clear stale provider states."""
import os
from dotenv import load_dotenv
load_dotenv()

# Test Gemini with configured model
print("=== Testing Gemini ===")
gkey = os.getenv("GEMINI_API_KEY", "")
try:
    from google import genai
    client = genai.Client(api_key=gkey)
    resp = client.models.generate_content(model="gemini-2.5-flash", contents="Test prompt: Respond with 'OK'")
    print(f"Gemini works! Response: {resp.text}")
except Exception as e:
    print(f"Gemini error: {e}")

# Clear stale provider states
print()
print("=== Clearing stale data ===")
from app.database.database import Database
from pathlib import Path
db_path = Path(os.getenv("DATABASE_PATH", "data/digest.db"))
print(f"DB path: {db_path}")
db = Database(db_path)

# Clear provider cooldowns
try:
    db.conn.execute("DELETE FROM ai_provider_state")
    db.conn.commit()
    print("Cleared provider states")
except Exception as e:
    print(f"No provider state table or error: {e}")

# Also clear sent history so we get fresh content for testing
try:
    count = db.cursor.execute("SELECT COUNT(*) FROM sent_items").fetchone()[0]
    print(f"Sent items in history: {count}")
except Exception as e:
    print(f"Sent items check: {e}")

db.close()
print("Done!")
