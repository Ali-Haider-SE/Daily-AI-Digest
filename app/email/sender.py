import smtplib
from email.message import EmailMessage
from typing import List, Union, Optional

def parse_recipients(recipients: Union[str, List[str]]) -> List[str]:
    """Clean and parse comma-separated recipient strings or lists."""
    if isinstance(recipients, str):
        raw = recipients.split(",")
    else:
        raw = recipients
    cleaned = [r.strip() for r in raw if r and r.strip() and "@" in r]
    if not cleaned:
        raise RuntimeError("EMAIL_TO is missing")
    return cleaned

def send_email(
    smtp_username: str,
    smtp_app_password: str,
    email_from: str,
    email_to: Union[str, List[str]],
    html: str,
    date_string: str,
    attachment_html: Optional[str] = None,
    attachment_filename: Optional[str] = None,
) -> str:
    """Send formatted digest email via Gmail SMTP using SSL (port 465) with HTML file attachment."""
    if not smtp_username:
        raise RuntimeError("SMTP_USERNAME is missing")

    if not smtp_app_password:
        raise RuntimeError("SMTP_APP_PASSWORD is missing")

    if not email_from:
        raise RuntimeError("EMAIL_FROM is missing")

    recipients = parse_recipients(email_to)

    # Use HTML content provided for attachment or default to main html
    standalone_content = attachment_html if attachment_html is not None else html
    if not attachment_filename:
        # Default filename format: daily_digest_YYYY-MM-DD.html
        import re
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", date_string)
        if date_match:
            attachment_filename = f"daily_digest_{date_match.group(1)}.html"
        else:
            attachment_filename = "daily_digest.html"

    message = EmailMessage()
    message["From"] = email_from
    message["To"] = ", ".join(recipients)
    message["Subject"] = f"Daily Intelligence Digest — {date_string}"

    # 1. Plain text fallback
    message.set_content(
        f"Your Daily Intelligence Digest for {date_string} is ready.\n\n"
        f"Please open the attached file '{attachment_filename}' in Google Chrome or any browser "
        "to view the complete interactive briefing and Jobs & Internships section."
    )

    # 2. HTML email body fallback
    body_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0b1120; margin: 0; padding: 24px; color: #1e293b; }}
    .card {{ max-width: 580px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; padding: 32px 28px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); border-top: 4px solid #0284c7; }}
    h1 {{ color: #0f172a; font-size: 22px; margin-top: 0; }}
    p {{ font-size: 14px; line-height: 1.6; color: #334155; }}
    .badge {{ display: inline-block; background-color: #dcfce7; color: #15803d; font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 4px; }}
    .notice {{ background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 16px; margin: 20px 0; }}
    .filename {{ font-family: monospace; font-weight: bold; color: #0284c7; font-size: 14px; }}
    .footer {{ font-size: 11px; color: #94a3b8; margin-top: 24px; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 16px; }}
  </style>
</head>
<body>
  <div class="card">
    <span class="badge">Briefing Ready</span>
    <h1>📰 Daily Intelligence Digest</h1>
    <p><strong>{date_string}</strong></p>
    
    <div class="notice">
      <p style="margin: 0 0 8px 0; font-weight: bold; color: #166534;">📎 Complete Digest Attached</p>
      <p style="margin: 0; color: #1e293b;">
        Your complete interactive intelligence digest is attached as:
        <br/><span class="filename">{attachment_filename}</span>
      </p>
    </div>

    <p>
      <strong>How to view:</strong>
      <ol style="padding-left: 20px; font-size: 14px; color: #334155;">
        <li>Download or open the attached <span class="filename">{attachment_filename}</span> file.</li>
        <li>Open it in Google Chrome or any web browser.</li>
        <li>Browse <strong>Jobs &amp; Internships</strong> at the top, followed by Top 5 developments and categorized global intelligence.</li>
      </ol>
    </p>

    <div class="footer">
      Daily Intelligence Digest &bull; Automated Decision Support &bull; Sent via Secure SMTP
    </div>
  </div>
</body>
</html>"""

        # Use the full digest as the email body; fall back to the notice card if empty
    email_body = html if html and html.strip() else body_html
    message.add_alternative(email_body, subtype="html")

    # 3. Add standalone HTML file attachment
    message.add_attachment(
        standalone_content.encode("utf-8"),
        maintype="text",
        subtype="html",
        filename=attachment_filename
    )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(smtp_username, smtp_app_password)
        smtp.send_message(message)

    return f"Email sent successfully with attachment {attachment_filename}"
