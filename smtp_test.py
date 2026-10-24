"""Gmail login test. Sends NO email and prints NO password. Run from the project folder."""
import os, smtplib, ssl
from dotenv import dotenv_values

env = dotenv_values(".env")
user = (env.get("SMTP_USERNAME") or "").strip()
pw = (env.get("SMTP_APP_PASSWORD") or "").replace(" ", "")
print(f"User: {user} | password length: {len(pw)} (Gmail App Password must be 16)")
if len(pw) != 16:
    print("PROBLEM: App Password is not 16 characters. Create a new one and paste it without spaces.")

def try_login(label, opener):
    try:
        s = opener()
        s.login(user, pw)
        s.quit()
        print(f"{label}: LOGIN OK")
    except smtplib.SMTPAuthenticationError as e:
        print(f"{label}: LOGIN REJECTED by Gmail (wrong/old App Password or 2-Step Verification off) code={e.smtp_code}")
    except Exception as e:
        print(f"{label}: FAILED -> {type(e).__name__}: {e}")

ctx = ssl.create_default_context()
try_login("smtp.gmail.com:465 (SSL)", lambda: smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=20))
def starttls():
    s = smtplib.SMTP("smtp.gmail.com", 587, timeout=20); s.starttls(context=ctx); return s
try_login("smtp.gmail.com:587 (STARTTLS)", starttls)
