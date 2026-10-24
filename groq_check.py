"""Groq key/model diagnostic. Run from the project folder:  python groq_check.py
Prints the REAL Groq response/error (the key itself is never printed)."""
import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv(override=True)
key = os.getenv("GROQ_API_KEY", "").strip()
model = os.getenv("GROQ_MODEL", "").strip()
print(f"Key loaded: {'yes' if key else 'NO'} (ends with ...{key[-4:] if key else ''})")
print(f"Model in .env: {model}")

client = Groq(api_key=key)

try:
    ids = sorted(m.id for m in client.models.list().data)
    print("\nModels available to your key:")
    for i in ids:
        print("  -", i)
    print("\nModel in .env exists on Groq:", model in ids)
except Exception as exc:
    print("\nCould not list models:", exc)

print("\nTest request with the model from .env ...")
try:
    r = client.chat.completions.with_raw_response.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        max_completion_tokens=20,
    )
    print("SUCCESS:", r.parse().choices[0].message.content)
    for h in ("x-ratelimit-limit-requests", "x-ratelimit-remaining-requests",
              "x-ratelimit-limit-tokens", "x-ratelimit-remaining-tokens"):
        if h in r.headers:
            print(f"  {h}: {r.headers[h]}")
except Exception as exc:
    print("ERROR (this is the real reason):")
    print(" ", exc)
