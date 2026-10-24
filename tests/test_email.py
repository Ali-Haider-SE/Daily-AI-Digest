"""Unit tests for HTML email and web digest rendering, accessibility, and recipient parsing."""
from datetime import datetime, timezone
from app.models import NewsItem, JobItem
from app.email.renderer import render_digest, format_digest_date
from app.email.sender import parse_recipients


def test_parse_recipients():
    raw_single = "ak5580k@gmail.com"
    assert parse_recipients(raw_single) == ["ak5580k@gmail.com"]

    raw_multi = " user1@example.com,  user2@example.com ,  "
    assert parse_recipients(raw_multi) == ["user1@example.com", "user2@example.com"]

    list_input = ["a@test.com", " b@test.com "]
    assert parse_recipients(list_input) == ["a@test.com", "b@test.com"]


def test_email_rendering():
    item = NewsItem(
        title="Major Pakistan Energy Development",
        url="https://dawn.com/energy-1",
        source="Dawn",
        category="Pakistan",
        credibility_score=90,
        credibility_label="Authentic News",
        summary="A new clean energy plant was inaugurated today in southern Pakistan.",
        why_it_matters="Reduces dependency on imported fuels and expands regional power grids.",
        source_count=2,
        corroboration_count=2,
        is_developing=True,
        content_hash="test_item_hash"
    )
    job = JobItem(
        title="Software Engineer Intern",
        company="Code Lab",
        url="https://codelab.io/apply",
        location="Islamabad",
        description="Fresh grad computer science internship.",
        source="Remotive",
        experience_level="Internship",
        match_label="Strong match",
        remote=True,
        work_mode="Remote",
        salary="Not disclosed",
        responsibilities="Build and test software features using Python.",
        key_skills="Python, Django, Git",
        content_hash="test_job_hash"
    )

    html = render_digest(
        news=[item],
        jobs=[job],
        top_stories=[item],
        web_base_url="http://127.0.0.1:8000"
    )

    assert "Daily Intelligence Digest" in html
    assert "Major Pakistan Energy Development" in html
    assert "Software Engineer Intern" in html
    # New labels must appear
    assert "Authentic News" in html or "Verification Pending" in html or "Conflicting Reports" in html
    # Old labels must NOT appear
    assert "High confidence" not in html
    assert "Medium confidence" not in html
    assert "Limited corroboration" not in html
    assert "DEVELOPING STORY" in html
    # Ensure Urdu translation and buttons are completely absent
    assert "اردو میں پڑھیں" not in html
    assert "btn-global-urdu" not in html
    assert "btn-toggle-urdu" not in html
    assert "lang=ur" not in html
    assert "PKT" in html

    # Table columns must be present
    assert "What You" in html or "What You&#39;ll Do" in html or "What You'll Do" in html
    assert "Salary" in html or "Pay" in html
    assert "Work Mode" in html or "Mode" in html
    assert "Apply" in html

    # Verify sections: Jobs is first, Pakistan is present, others removed
    assert html.find("Jobs") != -1
    assert "Pakistan News" in html
    jobs_pos = html.find("Jobs")
    pak_pos = html.find("Pakistan News")
    assert 0 < jobs_pos < pak_pos

    # Verify other categories and Top 5 Developments are removed
    assert "Today's 5 Most Important Developments" not in html
    assert "Wars &amp; Geopolitics" not in html
    assert "Finance &amp; Economy" not in html
    assert "Technology / AI" not in html
    assert "Science &amp; Inventions" not in html


def test_new_verification_labels_in_html():
    """Verify all three new label types render correctly in the HTML template."""
    authentic_item = NewsItem(
        title="Authentic Story",
        url="https://dawn.com/1",
        source="Dawn",
        category="Pakistan",
        credibility_score=90,
        credibility_label="Authentic News",
        summary="Summary of authentic story.",
        content_hash="h1"
    )
    pending_item = NewsItem(
        title="Pending Verification Story",
        url="https://example.com/2",
        source="Unknown Blog",
        category="Pakistan",
        credibility_score=55,
        credibility_label="Verification Pending",
        summary="Summary of pending story.",
        content_hash="h2"
    )
    conflicting_item = NewsItem(
        title="Conflicting Reports Story",
        url="https://dawn.com/3",
        source="Dawn",
        category="Pakistan",
        credibility_score=70,
        credibility_label="Conflicting Reports",
        is_developing=True,
        summary="Multiple sources disagree.",
        content_hash="h3"
    )

    html = render_digest(
        news=[authentic_item, pending_item, conflicting_item],
        jobs=[],
        top_stories=[],
        web_base_url="http://127.0.0.1:8000"
    )

    assert "Authentic News" in html
    assert "Verification Pending" in html
    assert "Conflicting Reports" in html
    # Old labels must never appear
    assert "High confidence" not in html
    assert "Low confidence" not in html


def test_send_email_validation_missing_fields():
    import pytest
    from app.email.sender import send_email

    # Missing SMTP_USERNAME
    with pytest.raises(RuntimeError, match="SMTP_USERNAME is missing"):
        send_email("", "app_pwd", "from@gmail.com", "to@gmail.com", "<p>hi</p>", "08 Oct 2026")

    # Missing SMTP_APP_PASSWORD
    with pytest.raises(RuntimeError, match="SMTP_APP_PASSWORD is missing"):
        send_email("user@gmail.com", "", "from@gmail.com", "to@gmail.com", "<p>hi</p>", "08 Oct 2026")

    # Missing EMAIL_FROM
    with pytest.raises(RuntimeError, match="EMAIL_FROM is missing"):
        send_email("user@gmail.com", "app_pwd", "", "to@gmail.com", "<p>hi</p>", "08 Oct 2026")

    # Missing EMAIL_TO
    with pytest.raises(RuntimeError, match="EMAIL_TO is missing"):
        send_email("user@gmail.com", "app_pwd", "from@gmail.com", "", "<p>hi</p>", "08 Oct 2026")


def test_send_email_mocked_smtp(monkeypatch):
    from unittest.mock import MagicMock
    import smtplib
    from app.email.sender import send_email

    mock_smtp_instance = MagicMock()
    mock_smtp_class = MagicMock(return_value=mock_smtp_instance)
    mock_smtp_instance.__enter__.return_value = mock_smtp_instance

    monkeypatch.setattr(smtplib, "SMTP_SSL", mock_smtp_class)

    result = send_email(
        smtp_username="test_user@gmail.com",
        smtp_app_password="test_secret_password",
        email_from="test_user@gmail.com",
        email_to="recipient1@example.com, recipient2@example.com",
        html="<h1>Briefing</h1><p>Content</p>",
        date_string="Thursday, 08 October 2026",
    )

    assert "Email sent successfully" in result

    # Verify SMTP_SSL initialized with smtp.gmail.com and port 465
    mock_smtp_class.assert_called_once_with("smtp.gmail.com", 465)

    # Verify login called with credentials
    mock_smtp_instance.login.assert_called_once_with("test_user@gmail.com", "test_secret_password")

    # Verify send_message called
    mock_smtp_instance.send_message.assert_called_once()
    sent_msg = mock_smtp_instance.send_message.call_args[0][0]

    assert sent_msg["From"] == "test_user@gmail.com"
    assert sent_msg["To"] == "recipient1@example.com, recipient2@example.com"
    assert "Thursday, 08 October 2026" in sent_msg["Subject"]

    # Verify multipart payload contains alternative body and attachment
    assert sent_msg.is_multipart()
    parts = list(sent_msg.walk())
    content_types = [p.get_content_type() for p in parts]
    assert "text/plain" in content_types
    assert "text/html" in content_types

    # Verify HTML attachment
    attachments = [p for p in parts if p.get_content_disposition() == "attachment"]
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "daily_digest.html" or "daily_digest" in attachments[0].get_filename()
    assert attachments[0].get_content_type() == "text/html"
    assert b"Briefing" in attachments[0].get_payload(decode=True)


def test_job_table_columns_in_html():
    """Verify new table columns appear in the rendered HTML."""
    job = JobItem(
        title="Junior Python Developer",
        company="TechCo Pakistan",
        url="https://techco.pk/apply",
        location="Lahore, Pakistan",
        description="Build REST APIs using Python and FastAPI.",
        source="Rozee.pk",
        experience_level="Entry Level",
        match_label="Strong match",
        remote=False,
        work_mode="On-site",
        salary="PKR 60,000/month",
        responsibilities="Develop and maintain REST APIs. Write unit tests.",
        key_skills="Python, FastAPI, PostgreSQL",
        deadline="31 Oct 2026",
        content_hash="test_job2"
    )

    html = render_digest(
        news=[],
        jobs=[job],
        top_stories=[],
        web_base_url="http://127.0.0.1:8000"
    )

    assert "Junior Python Developer" in html
    assert "TechCo Pakistan" in html
    assert "PKR 60,000/month" in html
    assert "Lahore, Pakistan" in html
    assert "On-site" in html
    assert "Python, FastAPI, PostgreSQL" in html
    assert "31 Oct 2026" in html
    assert "Rozee.pk" in html
    assert "Apply" in html


def test_filter_jobs_caps_at_30():
    """Verify filter_jobs never returns more than 30 jobs."""
    from app.processing.ranking import filter_jobs
    from app.models import JobItem

    jobs = [
        JobItem(
            title=f"Software Engineer Intern {i}",
            company=f"Company {i}",
            url=f"https://example.com/{i}",
            location="Worldwide",
            description="Intern 0-2 years Python developer entry level graduate.",
            remote=True,
            skills=["python"],
        )
        for i in range(50)
    ]
    result = filter_jobs(jobs)
    assert len(result) <= 30
