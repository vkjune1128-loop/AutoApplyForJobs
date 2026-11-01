# AutoApply: Automated Job Application & Resume Tailoring System

An open-source automation engine for multi-platform job hunting (LinkedIn, Naukri, Instahyre) with AI-powered resume tailoring (Gemini API) and intelligent scheduling.

---

## 🚀 Features

- **Multi-Platform Support**:
  - **LinkedIn**: Easy Apply automation via Playwright with session reuse and human-paced interaction.
  - **Naukri**: Search, batch/single apply with questionnaire handling (CTC, notice period).
  - **Instahyre**: One-click apply matching workflow.
- **ATS Resume Tailoring**:
  - Ground-truth AI tailoring via Google Gemini (`google-genai` SDK).
  - Strict anti-fabrication guardrails (reframes, reorders, and highlights real experience only).
  - ATS compatibility scoring & deterministic PDF parsing (`pdfminer.six`).
  - Clean HTML-to-PDF compilation via `weasyprint` and Jinja2 templates.
- **Cron / Scheduler**:
  - Daily scheduling with `APScheduler` configured for 15–20 applications/day spread across business hours.
- **Application Tracking**:
  - SQLite tracking with `sqlmodel` to record applications, prevent duplicates, and log ATS scores.

---

## 🛠️ Architecture

```
autoapply/
├── cli.py                     # CLI commands (tailor, apply, schedule, status, ats-check)
├── config/
│   ├── settings.py            # Environment-backed configuration (.env)
│   └── schemas.py             # Pydantic schemas (ResumeData, JobFilter, FormAnswers)
├── core/
│   ├── tailor.py              # Gemini API resume tailoring engine
│   ├── pdf_generator.py       # Jinja2 + WeasyPrint PDF compiler
│   ├── ats_parser.py          # pdfminer ATS text & layout checker
│   └── keyword_extractor.py   # TF keyword extraction & Jaccard matching
├── platforms/
│   ├── base.py                # Abstract Base Platform Applier
│   ├── linkedin.py            # LinkedIn Easy Apply automation
│   ├── naukri.py              # Naukri application automation
│   └── instahyre.py           # Instahyre application automation
├── scheduler/
│   └── jobs.py                # APScheduler job definitions (9 AM - 4 PM staggered)
├── tracker/
│   ├── models.py              # SQLModel schema (Job, Application, TailoredResume)
│   └── db.py                  # SQLite operations & application logging
└── utils/
    ├── browser.py             # Playwright browser manager with anti-detect settings
    └── logger.py              # Rich logging utility
```

---

## 📦 Setup & Installation

### 1. Requirements
- Python 3.11+
- Chrome / Chromium (installed via Playwright)

### 2. Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

### 3. Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Fill in your credentials:
```ini
# LinkedIn
LINKEDIN_EMAIL=your_email@example.com
LINKEDIN_PASSWORD=your_password

# Naukri
NAUKRI_EMAIL=your_email@example.com
NAUKRI_PASSWORD=your_password

# Instahyre
INSTAHYRE_EMAIL=your_email@example.com
INSTAHYRE_PASSWORD=your_password

# AI Tailoring
GEMINI_API_KEY=your_gemini_api_key

# Global Settings
MAX_APPLICATIONS_PER_DAY=20
HEADLESS_BROWSER=false
DRY_RUN=true
```

Customize:
- `config/master_resume.yaml`: Your master work history, skills, projects, and education.
- `config/job_filters.yaml`: Keywords, experience ranges, locations for each platform.
- `config/form_answers.yaml`: Answers for recurring screening questions (CTC, notice period, years of experience).

---

## 💻 CLI Usage

### 1. Tailor Resume for a Job Description
```bash
# Provide JD text or pass a file
autoapply tailor --jd-file sample_jd.txt --output data/generated_resumes/tailored.pdf
```

### 2. Check ATS Compatibility of Any Resume
```bash
autoapply ats-check --resume data/generated_resumes/tailored.pdf
```

### 3. Run Manual Application Session
```bash
# LinkedIn (runs in dry-run mode by default)
autoapply apply --platform linkedin --max 5

# Naukri
autoapply apply --platform naukri --max 5

# Instahyre
autoapply apply --platform instahyre --max 5
```

### 4. Check Status & Daily Application Counts
```bash
autoapply status
```

### 5. Run the Automated Daily Scheduler
```bash
autoapply schedule --start
```
The scheduler executes jobs at staggered intervals (e.g., LinkedIn at 9:00 AM & 2:00 PM, Naukri at 10:00 AM & 3:00 PM, Instahyre at 11:00 AM) to maintain 15–20 total daily applications safely.

---

## 🛡️ Anti-Detection & Safety

- **Delays**: Built-in randomized sleep intervals (3–8 seconds) mimic human interaction.
- **Headless Mode Disabled by Default**: Visible browser sessions minimize bot-detection triggers.
- **Daily Quotas**: Strict limits prevent over-applying and flagging accounts.
- **Dry-Run Mode**: Inspect filled forms and actions before enabling real submissions.
