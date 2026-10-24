# Daily Jobs & Internship News Automation System

[![Daily Intelligence Digest](https://github.com/MuhammadShariqShakeel/Daily-Jobs-Internship-News-automation-System/actions/workflows/daily_digest.yml/badge.svg)](https://github.com/MuhammadShariqShakeel/Daily-Jobs-Internship-News-automation-System/actions/workflows/daily_digest.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

An enterprise-grade, automated **Executive Intelligence & Tech Career Briefing System**. Every morning at **05:00 AM Pakistan Standard Time (PKT)**, it aggregates verified news from reputable international and domestic sources, extracts entry-level computing & software engineering opportunities, performs multi-source deduplication with corroboration analysis, scores credibility, synthesizes summaries via the configured Groq AI model, renders high-contrast responsive email briefings dispatched via Gmail SMTP (SSL 465), and hosts an interactive web digest.

---

## 🏛️ Architecture Overview

```text
                     [ GitHub Actions (00:00 UTC = 05:00 AM PKT) ]
                                            │
                                            ▼
                             [ Python Pipeline Orchestrator ]
                                     (app/main.py)
                                            │
                      ┌─────────────────────┴─────────────────────┐
                      ▼                                           ▼
          [ News Collectors ]                            [ Job Collectors ]
        - RSS Feeds (Dawn, Guardian,                   - Adzuna Jobs API (PK)
          TechCrunch, NASA, Ars Technica)              - Remotive (Global Remote)
        - NewsAPI (Top Headlines)
                      │                                           │
                      └─────────────────────┬─────────────────────┘
                                            ▼
                                [ Normalization Layer ]
                                            │
                                            ▼
                         [ Content Hash & Deduplication ]
                         (Preserves corroboration counts)
                                            │
                                            ▼
                               [ Intelligence Categorizer ]
                         (Pakistan, Global, Wars, Tech/AI...)
                                            │
                                            ▼
                              [ Credibility Assessment ]
                         (Scores 0-100, Developing Story flags)
                                            │
                                            ▼
                            [ Deterministic Importance Rank ]
                         (Recency decay, category multipliers)
                                            │
                                            ▼
                                [ Groq AI Engine ]
                         (Synthesizes summaries & why-it-matters)
                                            │
                                            ▼
                              [ SQLite Persistence Engine ]
                         - Sent Items Ledger (prevents duplicates)
                         - Historical Digests Catalog (JSON storage)
                                            │
                      ┌─────────────────────┴─────────────────────┐
                      ▼                                           ▼
             [ Email Dispatcher ]                        [ Web Digest Portal ]
             - Table-based HTML Email                    - Dark-mode Dashboard
             - Cross-client compatible                   - Interactive Search & Filter
             - Multi-recipient Gmail SMTP
```

---

## 🚀 Key Features

1. **Multi-Source News Aggregation**: Collects from reputable global and domestic feeds (Dawn, Dawn Business, The Guardian, TechCrunch, Ars Technica, MIT Technology Review, NASA, NewsAPI).
2. **Targeted Tech Job Pipeline**: Filters internships, fresh graduate, junior, and entry-level computing roles for BS Computer Science / Software Engineering / IT students across Pakistan and remote global employers.
3. **Corroborating Deduplication**: Instead of discarding identical events reported by multiple outlets, it tracks corroboration counts (e.g., *"Confirmed by 3 sources"*) to elevate story credibility.
4. **Credibility & Developing Story Engine**: Identifies unconfirmed breaking news with `⚠️ Developing Story` warnings, distinguishes official `.gov`/`.edu` sources, and grades confidence (`High confidence`, `Medium confidence`, `Limited corroboration`).
5. **AI Summarization with Safe Fallback**: Leverages Groq (`openai/gpt-oss-120b`) with batching for executive summaries and *"Why it matters"* briefs. Automatically falls back to deterministic extraction if offline or unkeyed.
6. **Strict HCI Design Principles**:
   - Visual hierarchy, progressive disclosure, high information density without clutter.
   - High-contrast dark dashboard for reduced eye strain.
   - Keyboard accessibility, semantic HTML, and `prefers-reduced-motion` compliance.
7. **Ephemeral-Safe GitHub Actions Persistence**: Implements a two-phase GitHub Actions cache with rolling keys and artifact backups to ensure the SQLite database survives across daily runs.

---

## 📂 Project Structure

```text
daily-intelligence-digest-ready/
├── .github/workflows/daily_digest.yml  # Scheduled GitHub Actions workflow
├── app/
│   ├── ai/                             # AI providers, summarization and failover
│   ├── database/                       # SQLite persistence
│   ├── email/                          # Email rendering and SMTP delivery
│   ├── jobs/                           # Job-source collectors
│   ├── news/                           # News collectors and source metadata
│   ├── processing/                     # Categorization, credibility and ranking
│   ├── web/                            # Web digest application
│   ├── config.py
│   ├── main.py
│   ├── models.py
│   └── preview.py
├── data/                               # Runtime database; ignored by Git
├── static/                             # Dashboard CSS and JavaScript
├── templates/                          # Email and web HTML templates
├── tests/                              # Automated tests
├── .env.example                        # Safe environment-variable template
├── .gitignore
├── requirements.txt
├── validate_project.py
└── README.md
```

---

## 🛠️ Installation & Setup (Windows)

### 1. Prerequisites
- Python 3.11 or higher (Python 3.12 / 3.14 verified)
- Git

### 2. Clone and Setup Virtual Environment
Open **PowerShell** in your project folder:

```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\Activate.ps1

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy the template to `.env`:

```powershell
Copy-Item .env.example .env
```

Open `.env` and fill in your API credentials:

```ini
# Email Delivery (Gmail SMTP)
SMTP_USERNAME=your_gmail@gmail.com
SMTP_APP_PASSWORD=your_16_character_app_password
EMAIL_FROM=your_gmail@gmail.com
EMAIL_TO=recipient1@example.com,recipient2@example.com

# AI Summarization (Multi-Key Groq Failover)
GROQ_API_KEY=gsk_primary_key_here
GROQ_API_KEY_2=gsk_second_key_here
GROQ_API_KEY_3=gsk_third_key_here
GROQ_API_KEY_4=gsk_fourth_key_here
GROQ_MODEL=qwen/qwen3.8-27b
GROQ_MAX_RETRIES_PER_OP=2

# NewsAPI (Optional)
NEWS_API_KEY=

# Job APIs (Adzuna - Optional)
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
ADZUNA_COUNTRY=pk

# Persistence & Tuning
DATABASE_PATH=data/digest.db
REQUEST_TIMEOUT=20
MAX_NEWS_ITEMS=150
MAX_JOB_ITEMS=100
MIN_CREDIBILITY_SCORE=55
TOP_STORIES_COUNT=5

# Web Server Portal
WEB_HOST=127.0.0.1
WEB_PORT=8000
WEB_BASE_URL=http://127.0.0.1:8000
PUBLIC_BASE_URL=http://127.0.0.1:8000
```

> **Security Note:** Never commit your `.env` file or Gmail App Password to version control. `.env` is protected by `.gitignore`.

---

## 📧 Gmail SMTP Setup Instructions

To dispatch the daily digest via Gmail SMTP:

1. **Enable 2-Step Verification**: Turn on 2-Step Verification in your Google Account security settings.
2. **Generate a Gmail App Password**:
   - Go to Google Account → Security → 2-Step Verification → App passwords.
   - Create a dedicated App Password (e.g. named "Daily Digest") which generates a 16-character code.
3. **Configure Local `.env`**:
   - Set `SMTP_USERNAME=your_gmail@gmail.com`.
   - Set `SMTP_APP_PASSWORD=your_16_character_app_password` (without spaces).
   - Set `EMAIL_FROM=your_gmail@gmail.com` (normally matches your SMTP username).
   - Set `EMAIL_TO=recipient@example.com` (supports one or multiple comma-separated addresses).
4. **Never Commit Secrets**: Never commit `.env` or credentials to git.
5. **For Automated Execution**: Store credentials in GitHub Repository Secrets.

---

## 💻 Local Execution & Commands

### 1. Validate Codebase
Run AST syntax checks across all Python files:
```powershell
python validate_project.py
```

### 2. Run Test Suite
Execute the comprehensive test suite:
```powershell
pytest -v
```

### 3. Dry-Run Execution (Safe Local Test)
Runs the entire pipeline (aggregation, deduplication, scoring, AI, database persistence, and HTML rendering) **without sending real emails**:
```powershell
python -m app.main --dry-run
```
Output will be written to `data/latest_digest.html`.

### 4. Generate Email Preview & Start Web Dashboard
Generate a preview of the email and immediately launch the interactive web portal:
```powershell
python -m app.preview --serve
```
Open your browser to:
- **Interactive Web Digest**: `http://127.0.0.1:8000/`
- **Email Preview File**: Open `preview/digest.html` in any browser.

### 5. Production Execution (Send Real Email)
To run live and dispatch via Gmail SMTP:
```powershell
python -m app.main
```
To force delivery even if items were already recorded in the database:
```powershell
python -m app.main --force-send
```

---

## ⚙️ GitHub Actions Automation

The workflow `.github/workflows/daily_digest.yml` is configured to run automatically every morning at **00:00 UTC (05:00 AM PKT)**.

### Configuring GitHub Repository Secrets
Go to your GitHub repository: **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret Name | Description | Example |
| :--- | :--- | :--- |
| `SMTP_USERNAME` | Gmail address used for SMTP login | `your_account@gmail.com` |
| `SMTP_APP_PASSWORD` | 16-character Google App Password | `abcd efgh ijkl mnop` |
| `EMAIL_FROM` | Sender email address (normally your Gmail address) | `your_account@gmail.com` |
| `EMAIL_TO` | Recipient email(s) separated by commas | `user1@gmail.com, user2@gmail.com` |
| `GROQ_API_KEY` | Groq Cloud Primary API Key | `gsk_...` |
| `GROQ_API_KEY_2` | *(Optional)* Second Groq Key for failover | `gsk_...` |
| `GROQ_API_KEY_3` | *(Optional)* Third Groq Key for failover | `gsk_...` |
| `GROQ_API_KEY_4` | *(Optional)* Fourth Groq Key for failover | `gsk_...` |
| `GROQ_MODEL` | *(Optional)* LLM model identifier | `qwen/qwen3.8-27b` |
| `NEWS_API_KEY` | *(Optional)* NewsAPI Developer Key | `abc123...` |
| `ADZUNA_APP_ID` | *(Optional)* Adzuna Job App ID | `12345...` |
| `ADZUNA_APP_KEY` | *(Optional)* Adzuna Job App Key | `xyz987...` |
| `WEB_BASE_URL` | *(Optional)* Public URL of hosted web digest | `https://your-digest-domain.com` |

### SQLite Persistence Strategy on Ephemeral Runners
Because GitHub Actions runners are ephemeral, the workflow employs a **three-tier persistence strategy**:
1. **Cache Restore**: Restores `data/digest.db` before execution using the rolling prefix `digest-sqlite-${{ runner.os }}-`.
2. **Cache Save**: Saves the updated SQLite database with a run-specific key `digest-sqlite-${{ runner.os }}-${{ github.run_id }}`.
3. **Artifact Backup**: Uploads `data/digest.db` and `data/latest_digest.html` as downloadable workflow artifacts retained for 30 days.

---

## 🔒 Security Best Practices
- **No Hardcoded Credentials**: All tokens are resolved via environment variables.
- **SQL Injection Prevention**: All SQLite queries use strict parameter bindings (`?`).
- **XSS Mitigation**: Jinja2 autoescaping is enforced on all dynamic article data.
- **Protocol Sanitation**: Links are validated against safe schemes (`http://`, `https://`).

---

## 📄 License
Review the repository for the applicable license before redistributing or reusing the project.
# Daily-Jobs-Internship-News-automation-System
Automated daily entry-level jobs, internships, and Pakistan news fetcher with AI-powered summaries and scheduled email delivery using Python and GitHub Actions.
