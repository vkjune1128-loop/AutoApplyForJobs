"""GitHub Issues manager for mobile push notifications and two-way sync."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from autoapply.config.settings import Settings
from autoapply.tracker.models import Application, Job
from autoapply.utils.logger import get_logger

logger = get_logger(__name__)


def _github_api_request(
    endpoint: str,
    method: str = "GET",
    data: dict[str, Any] | None = None,
    token: str = "",
) -> Any:
    """Execute an authenticated GitHub REST API request."""
    url = f"https://api.github.com{endpoint}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AutoApply-Bot",
    }
    body = json.dumps(data).encode("utf-8") if data else None

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=12) as resp:
        res_data = resp.read()
        return json.loads(res_data.decode("utf-8")) if res_data else None


def create_or_update_digest_issue(
    items: list[dict],
    candidate_name: str,
    settings: Settings,
) -> int | None:
    """Create a new GitHub Issue for today's action queue or update existing open issue.

    This triggers an instant mobile push notification on the user's phone via the GitHub app.
    """
    token = settings.github_token
    repo = settings.github_repo
    username = settings.github_username

    if not token or not repo:
        logger.info("GitHub token not configured — skipping Issue creation.")
        return None

    if not items:
        logger.info("No active jobs in queue — skipping Issue notification.")
        return None

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    date_title = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. Build Issue Body in clean Markdown for mobile reading
    lines = [
        f"Hey @{username}! 🌅 **{len(items)} High-Match Roles** are tailored and ready for you.",
        "",
        f"**Candidate:** {candidate_name} | **Sync Time:** `{today_str}`",
        "",
        "### 🎯 Action Queue",
        "",
        "| Company | Role | ATS Match | Apply | Tailored Resume |",
        "|:---|:---|:---:|:---:|:---:|",
    ]

    for it in items:
        comp = it.get("company", "Company")
        role = it.get("role", "Software Engineer")
        score = it.get("score", 0)
        url = it.get("url", "#")
        pdf_name = it.get("pdf_name")
        if pdf_name:
            quoted_name = urllib.parse.quote(pdf_name)
            raw_url = f"https://raw.githubusercontent.com/{repo}/main/data/generated_resumes/{quoted_name}"
            pdf_link = f"[📄 Download PDF]({raw_url})"
        else:
            pdf_link = "N/A"
        apply_link = f"[🚀 Apply Now]({url})" if url != "#" else "Direct Search"
        lines.append(f"| **{comp}** | {role} | **{score}%** | {apply_link} | {pdf_link} |")

    lines.extend([
        "",
        "### 📨 Outreach Notes & Referral Pitches",
        "",
    ])

    for it in items:
        comp = it.get("company", "Company")
        role = it.get("role", "Software Engineer")
        cover_note = it.get("cover_note", "").strip()
        ref_note = it.get("referral_note", "").strip()

        lines.append(f"#### 🏢 {comp} — {role}")
        if cover_note:
            lines.append(f"<details><summary><b>📨 Recruiter Outreach Note (Tap to Expand)</b></summary>\n\n> {cover_note}\n</details>")
        if ref_note:
            lines.append(f"<details><summary><b>🤝 Employee Referral Pitch (Tap to Expand)</b></summary>\n\n> {ref_note}\n</details>")
        lines.append("")

    lines.extend([
        "---",
        "### 📌 How to Complete this Queue from your Phone:",
        "1. Tap the **Apply Now** links and attach the tailored PDFs.",
        "2. When done, simply tap **Close Issue** at the bottom.",
        "   - **Applied to all?** Just close the issue. AutoApply will automatically mark all roles as *Applied* in SQLite on the next run!",
        "   - **Applied to some only?** Leave a quick comment before closing (e.g. `Applied: Capgemini, Meesho` or `Skipped: PayPal`).",
        "",
        f"🔗 *Full dashboard: [DAILY_DIGEST.md](DAILY_DIGEST.md) | [Dashboard](data/copilot_dashboard.html)*",
    ])

    issue_body = "\n".join(lines)
    issue_title = f"🌅 Action Queue: {len(items)} Roles Ready — {date_title}"

    try:
        # Check if an open issue with label 'daily-digest' already exists
        open_issues = _github_api_request(
            f"/repos/{repo}/issues?state=open&labels=daily-digest",
            token=token,
        )

        if open_issues and len(open_issues) > 0:
            existing = open_issues[0]
            issue_num = existing["number"]
            logger.info(f"Updating existing open GitHub Issue #{issue_num}")
            _github_api_request(
                f"/repos/{repo}/issues/{issue_num}",
                method="PATCH",
                data={"title": issue_title, "body": issue_body},
                token=token,
            )
            return issue_num

        # Otherwise create a new issue
        logger.info(f"Creating new GitHub Issue for {len(items)} jobs...")
        new_issue = _github_api_request(
            f"/repos/{repo}/issues",
            method="POST",
            data={
                "title": issue_title,
                "body": issue_body,
                "labels": ["daily-digest", "ready-to-apply"],
            },
            token=token,
        )
        issue_num = new_issue.get("number")
        logger.info(f"✓ Created GitHub Issue #{issue_num}: '{issue_title}'")
        return issue_num

    except Exception as e:
        logger.warning(f"Could not create/update GitHub Issue: {e}")
        return None


def sync_closed_issues_to_db(engine: object, settings: Settings) -> int:
    """Inspect closed digest issues and synchronize applied applications back to SQLite.

    Default Behavior:
    - If the user closed the issue without special comments: assume ALL jobs in that issue were applied!
    - If the user wrote a comment (e.g. 'Applied: Meesho' or 'Skipped: Cred'): parse and record accordingly.
    """
    token = settings.github_token
    repo = settings.github_repo

    if not token or not repo:
        return 0

    try:
        # Fetch closed issues with label 'daily-digest'
        closed_issues = _github_api_request(
            f"/repos/{repo}/issues?state=closed&labels=daily-digest",
            token=token,
        )
        if not closed_issues:
            return 0

        synced_count = 0

        for issue in closed_issues:
            labels = [lbl.get("name") for lbl in issue.get("labels", [])]
            if "synced" in labels:
                continue

            issue_num = issue["number"]
            issue_body = issue.get("body", "")
            closed_at_str = issue.get("closed_at")
            if closed_at_str:
                closed_at = datetime.fromisoformat(closed_at_str.replace("Z", "+00:00"))
            else:
                closed_at = datetime.now(timezone.utc)

            # Extract companies mentioned in the issue table (e.g. | **Capgemini** | ...)
            companies_in_issue = re.findall(r"\|\s*\*\*([^*]+)\*\*\s*\|", issue_body)
            if not companies_in_issue:
                # Fallback: look for 🏢 Company — Role
                companies_in_issue = re.findall(r"#### 🏢 ([^\s—]+)", issue_body)

            if not companies_in_issue:
                continue

            # Fetch any user comments on this issue
            comments = _github_api_request(
                f"/repos/{repo}/issues/{issue_num}/comments",
                token=token,
            ) or []

            applied_companies: set[str] = set()
            skipped_companies: set[str] = set()

            if comments:
                # User left a comment (e.g. "Applied: Capgemini, Meesho. Skipped: PayPal")
                all_comment_text = " ".join([c.get("body", "") for c in comments]).lower()

                for comp in companies_in_issue:
                    comp_lower = comp.lower().strip()
                    if f"skip" in all_comment_text and comp_lower in all_comment_text:
                        skipped_companies.add(comp)
                    elif comp_lower in all_comment_text:
                        applied_companies.add(comp)

                # If comment didn't mention some companies, check if user indicated anything
                if not applied_companies and not skipped_companies:
                    # Generic comment, treat all as applied
                    applied_companies = set(companies_in_issue)
            else:
                # Zero comments — default rule: user closed issue = applied to all!
                applied_companies = set(companies_in_issue)

            # Update SQLite database
            with Session(engine) as session:
                for comp in applied_companies:
                    statement = select(Application).join(Job).where(Job.company.ilike(f"%{comp}%")).where(Application.status == "ready_to_apply")
                    app_records = session.exec(statement).all()
                    for app in app_records:
                        app.status = "applied"
                        app.applied_at = closed_at
                        session.add(app)
                        synced_count += 1
                        logger.info(f"✓ Marked {comp} as APPLIED (synced from GitHub Issue #{issue_num})")

                for comp in skipped_companies:
                    statement = select(Application).join(Job).where(Job.company.ilike(f"%{comp}%")).where(Application.status == "ready_to_apply")
                    app_records = session.exec(statement).all()
                    for app in app_records:
                        app.status = "skipped"
                        session.add(app)
                        logger.info(f"✓ Marked {comp} as SKIPPED (synced from GitHub Issue #{issue_num})")

                session.commit()

            # Mark issue with label 'synced' so we don't process it repeatedly
            try:
                _github_api_request(
                    f"/repos/{repo}/issues/{issue_num}/labels",
                    method="POST",
                    data={"labels": ["synced"]},
                    token=token,
                )
            except Exception as e:
                logger.debug(f"Could not add synced label to issue #{issue_num}: {e}")

        return synced_count

    except Exception as e:
        logger.warning(f"Error during GitHub issue two-way sync: {e}")
        return 0
