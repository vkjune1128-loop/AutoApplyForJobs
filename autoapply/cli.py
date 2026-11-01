"""CLI entry point for AutoApply."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from autoapply.config.settings import Settings
from autoapply.utils.logger import get_logger

console = Console()
logger = get_logger(__name__)


def cmd_tailor(args: argparse.Namespace) -> None:
    """One-shot resume tailoring from a JD."""
    from autoapply.config.schemas import ResumeData
    from autoapply.core.tailor import ResumeTailor
    from autoapply.core.pdf_generator import generate_resume_pdf

    import yaml

    settings = Settings()

    # Load master resume
    resume_path = Path(args.resume or "config/master_resume.yaml")
    if not resume_path.exists():
        console.print(f"[red]Resume file not found: {resume_path}[/red]")
        sys.exit(1)

    with open(resume_path) as f:
        resume_raw = yaml.safe_load(f)
    resume = ResumeData.model_validate(resume_raw)

    # Read JD
    jd_text = args.jd
    if args.jd_file:
        jd_text = Path(args.jd_file).read_text()

    if not jd_text:
        console.print("[red]Provide --jd or --jd-file[/red]")
        sys.exit(1)

    tailor = ResumeTailor(api_key=settings.gemini_api_key)

    console.print("[cyan]Extracting keywords from JD...[/cyan]")
    keywords = tailor.extract_jd_keywords(jd_text)
    console.print(f"  Required: {', '.join(keywords.get('required_skills', []))}")
    console.print(f"  Preferred: {', '.join(keywords.get('preferred_skills', []))}")

    console.print("[cyan]Tailoring resume...[/cyan]")
    tailored = tailor.tailor_resume(resume, jd_text, keywords)

    console.print("[cyan]Estimating ATS score...[/cyan]")
    score = tailor.estimate_ats_score(resume, keywords)
    console.print(f"  ATS Score: [bold green]{score['score']}%[/bold green]")
    console.print(f"  Matched: {', '.join(score['matched'])}")
    console.print(f"  Missing: {', '.join(score['missing'])}")

    # Generate PDF with professional naming convention: Vikas_Kumar_{Company}_{Role}.pdf
    if args.output:
        output = args.output
    else:
        name_part = resume.name.strip().replace(" ", "_")
        company_part = (args.company or "Company").strip().replace(" ", "_")
        role_part = (args.role or "Java_Backend").strip().replace(" ", "_")
        filename = f"{name_part}_{company_part}_{role_part}.pdf"
        output = f"data/generated_resumes/{filename}"

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    generate_resume_pdf(tailored.model_dump(), output)
    console.print(f"[green]✓ Tailored resume saved to: [bold]{output}[/bold][/green]")

    # Generate custom cover note for recruiters
    cover_note = tailor.generate_cover_note(resume, jd_text)
    if cover_note:
        console.print("\n[bold cyan]📨 3-Sentence Recruiter Outreach Note:[/bold cyan]")
        console.print(f"[italic]{cover_note}[/italic]\n")

        note_file = Path(output).with_suffix(".txt")
        note_file.write_text(cover_note, encoding="utf-8")


def cmd_apply(args: argparse.Namespace) -> None:
    """Run a manual apply session on a platform."""
    from autoapply.config.schemas import JobFilter
    from autoapply.tracker.db import get_engine, get_session, init_db
    from autoapply.utils.browser import launch_browser

    import yaml

    settings = Settings()

    # Load filters
    filters_path = Path("config/job_filters.yaml")
    if not filters_path.exists():
        console.print("[red]config/job_filters.yaml not found[/red]")
        sys.exit(1)

    with open(filters_path) as f:
        all_filters = yaml.safe_load(f)

    platform = args.platform.lower()
    if platform not in all_filters:
        console.print(f"[red]No filters configured for platform: {platform}[/red]")
        sys.exit(1)

    filters = JobFilter.model_validate(all_filters[platform])
    max_apps = args.max or settings.max_applications_per_day

    # Init DB
    engine = get_engine(settings.db_path)
    init_db(engine)

    console.print(f"[cyan]Launching {platform} applier (max {max_apps} applications)...[/cyan]")
    if settings.dry_run:
        console.print("[yellow]DRY RUN mode — no applications will be submitted[/yellow]")

    # Import and run the platform applier
    applier_map = {
        "linkedin": "autoapply.platforms.linkedin",
        "naukri": "autoapply.platforms.naukri",
        "instahyre": "autoapply.platforms.instahyre",
    }

    if platform not in applier_map:
        console.print(f"[red]Unknown platform: {platform}[/red]")
        sys.exit(1)

    import importlib

    mod = importlib.import_module(applier_map[platform])
    applier_cls = {
        "linkedin": mod.LinkedInApplier,
        "naukri": mod.NaukriApplier,
        "instahyre": mod.InstahyreApplier,
    }[platform]

    browser, context = launch_browser(
        headless=settings.headless_browser,
        state_dir=str(Path(settings.data_dir) / "browser_state" / platform),
    )

    try:
        with get_session(engine) as session:
            applier = applier_cls(settings=settings, browser=context, tracker=session)
            applier.run(filters=filters, max_applications=max_apps)
    finally:
        context.close()
        browser.close()


def cmd_schedule(args: argparse.Namespace) -> None:
    """Start the scheduler daemon."""
    from autoapply.scheduler.jobs import create_scheduler

    settings = Settings()
    console.print("[cyan]Starting AutoApply scheduler...[/cyan]")
    console.print("  LinkedIn: 9 AM, 2 PM")
    console.print("  Naukri: 10 AM, 3 PM")
    console.print("  Instahyre: 11 AM")

    scheduler = create_scheduler(settings)
    try:
        scheduler.start()
        console.print("[green]Scheduler running. Press Ctrl+C to stop.[/green]")
        import time
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        console.print("[yellow]Scheduler stopped.[/yellow]")


def cmd_status(args: argparse.Namespace) -> None:
    """Show today's application stats from the DB."""
    from autoapply.tracker.db import get_engine, get_session, get_today_count, init_db

    settings = Settings()
    engine = get_engine(settings.db_path)
    init_db(engine)

    table = Table(title="Today's Application Stats")
    table.add_column("Platform", style="cyan")
    table.add_column("Applied", style="green")
    table.add_column("Skipped", style="yellow")
    table.add_column("Failed", style="red")
    table.add_column("Dry Run", style="dim")

    with get_session(engine) as session:
        for platform in ["linkedin", "naukri", "instahyre"]:
            applied = get_today_count(session, platform, status="applied")
            skipped = get_today_count(session, platform, status="skipped")
            failed = get_today_count(session, platform, status="failed")
            dry_run = get_today_count(session, platform, status="dry_run")
            table.add_row(platform.title(), str(applied), str(skipped), str(failed), str(dry_run))

    console.print(table)


def cmd_ats_check(args: argparse.Namespace) -> None:
    """Run an ATS compatibility check on a PDF resume."""
    from autoapply.core.ats_parser import parse_resume_pdf, check_ats_compatibility

    pdf_path = args.resume
    if not Path(pdf_path).exists():
        console.print(f"[red]File not found: {pdf_path}[/red]")
        sys.exit(1)

    console.print(f"[cyan]Checking ATS compatibility for {pdf_path}...[/cyan]")
    result = check_ats_compatibility(pdf_path)

    console.print(f"\n  Text Extractable: {'✓' if result['text_extractable'] else '✗'}")
    console.print(f"  Has Tables: {'⚠ Yes' if result['has_tables'] else '✓ No'}")
    console.print(f"  Has Images: {'⚠ Yes' if result['has_images'] else '✓ No'}")
    console.print(f"  Word Count: {result['word_count']}")

    if result["warnings"]:
        console.print("\n[yellow]Warnings:[/yellow]")
        for w in result["warnings"]:
            console.print(f"  ⚠ {w}")
    else:
        console.print("\n[green]✓ No ATS compatibility issues found[/green]")

    if args.verbose:
        console.print("\n[dim]--- Extracted Text (what ATS sees) ---[/dim]")
        text = parse_resume_pdf(pdf_path)
        console.print(text[:2000])


def cmd_copilot(args: argparse.Namespace) -> None:
    """Run Smart Copilot batch matching and document generation."""
    import yaml
    from autoapply.config.schemas import ResumeData
    from autoapply.core.tailor import ResumeTailor
    from autoapply.core.pdf_generator import generate_resume_pdf
    from autoapply.tracker.db import get_engine, get_session, init_db
    from autoapply.tracker.models import Job, Application

    settings = Settings()
    min_score = args.min_score or 65

    # Load master resume
    resume_path = Path("config/master_resume.yaml")
    if not resume_path.exists():
        console.print("[red]config/master_resume.yaml not found[/red]")
        sys.exit(1)

    with open(resume_path) as f:
        resume_raw = yaml.safe_load(f)
    resume = ResumeData.model_validate(resume_raw)

    # Load jobs
    jobs_file = Path(args.jobs_file or "config/jobs.yaml")
    if not jobs_file.exists():
        console.print(f"[red]Jobs queue file not found: {jobs_file}[/red]")
        sys.exit(1)

    with open(jobs_file) as f:
        jobs_data = yaml.safe_load(f)

    job_list = jobs_data.get("jobs", [])
    if not job_list:
        console.print("[yellow]No jobs found in queue.[/yellow]")
        return

    console.print(f"[bold cyan]🚀 Smart Copilot analyzing {len(job_list)} job(s)...[/bold cyan]\n")

    tailor = ResumeTailor(api_key=settings.gemini_api_key)
    engine = get_engine(settings.db_path)
    init_db(engine)

    table = Table(title="Smart Copilot — Job Match & Action Digest")
    table.add_column("Company", style="bold white")
    table.add_column("Role", style="cyan")
    table.add_column("Platform", style="magenta")
    table.add_column("ATS Match", justify="center")
    table.add_column("Action / PDF", style="green")

    digest_items = []

    for item in job_list:
        company = item.get("company", "Company")
        role = item.get("role", "Software Engineer")
        platform = item.get("platform", "web")
        url = item.get("url", "#")
        jd = item.get("jd", "")

        # Extract keywords and score
        kw = tailor.extract_jd_keywords(jd)
        score_res = tailor.estimate_ats_score(resume, kw)
        score = score_res["score"]

        # Filename
        name_clean = resume.name.strip().replace(" ", "_")
        comp_clean = company.strip().replace(" ", "_")
        role_clean = role.strip().replace(" ", "_").replace("/", "_").replace("-", "_")
        pdf_filename = f"{name_clean}_{comp_clean}_{role_clean}.pdf"
        pdf_path = Path(f"data/generated_resumes/{pdf_filename}")

        if score >= min_score:
            score_badge = f"[bold green]{score}% ✓[/bold green]"
            # Tailor and generate PDF
            tailored = tailor.tailor_resume(resume, jd, kw)
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            generate_resume_pdf(tailored.model_dump(), str(pdf_path))

            # Cover note
            cover_note = tailor.generate_cover_note(resume, jd)
            note_file = pdf_path.with_suffix(".txt")
            note_file.write_text(cover_note, encoding="utf-8")

            # Log to DB
            with get_session(engine) as session:
                from sqlmodel import select
                existing_job = session.exec(select(Job).where(Job.url == url)).first() if url != "#" else None
                if existing_job:
                    job_rec = existing_job
                else:
                    job_rec = Job(
                        platform=platform,
                        title=role,
                        company=company,
                        location=item.get("location", ""),
                        url=url if url != "#" else f"urn:{comp_clean}:{role_clean}",
                        jd_text=jd,
                    )
                    session.add(job_rec)
                    session.commit()
                    session.refresh(job_rec)

                app_rec = Application(
                    job_id=job_rec.id,
                    platform=platform,
                    status="ready_to_apply",
                    tailored_resume_path=str(pdf_path),
                    ats_score=score,
                    notes=cover_note,
                )
                session.add(app_rec)
                session.commit()

            action_text = f"[green]Ready[/green] ({pdf_filename})"
        else:
            score_badge = f"[yellow]{score}% (Low)[/yellow]"
            action_text = "[dim]Skipped (< threshold)[/dim]"
            cover_note = ""

        table.add_row(company, role, platform.upper(), score_badge, action_text)

        digest_items.append({
            "company": company,
            "role": role,
            "platform": platform,
            "url": url,
            "location": item.get("location", ""),
            "score": score,
            "pdf_path": str(pdf_path) if score >= min_score else None,
            "pdf_name": pdf_filename if score >= min_score else None,
            "cover_note": cover_note,
            "recommended": score >= min_score,
        })

    console.print(table)

    # Generate HTML Action Digest Dashboard
    digest_html_path = Path("data/copilot_dashboard.html")
    _render_copilot_html(digest_items, resume.name, digest_html_path)
    console.print(f"\n[bold green]✓ Action Dashboard generated at:[/bold green] [underline]{digest_html_path}[/underline]")


def _render_copilot_html(items: list[dict], candidate_name: str, output_path: Path) -> None:
    """Render an interactive HTML action dashboard for Smart Copilot."""
    cards_html = []
    for it in items:
        badge_class = "badge-high" if it["score"] >= 80 else ("badge-med" if it["score"] >= 65 else "badge-low")
        pdf_button = (
            f'<a href="generated_resumes/{it["pdf_name"]}" target="_blank" class="btn btn-pdf">📄 Open Tailored PDF</a>'
            if it["pdf_path"]
            else '<span class="skipped-label">Below Threshold</span>'
        )
        note_section = (
            f'<div class="note-box"><p class="note-text" id="note-{it["company"]}">{it["cover_note"]}</p>'
            f'<button onclick="navigator.clipboard.writeText(document.getElementById(\'note-{it["company"]}\').innerText); alert(\'Copied outreach note!\');" class="btn btn-copy">📋 Copy Outreach Note</button></div>'
            if it["cover_note"]
            else ""
        )

        cards_html.append(f"""
        <div class="job-card">
            <div class="card-header">
                <div>
                    <h3>{it['role']}</h3>
                    <div class="company-sub">{it['company']} • <span class="loc">{it['location']}</span> • <span class="plat">{it['platform'].upper()}</span></div>
                </div>
                <div class="score-badge {badge_class}">{it['score']}% ATS</div>
            </div>
            <div class="card-actions">
                {pdf_button}
                <a href="{it['url']}" target="_blank" class="btn btn-apply">🚀 Apply on {it['platform'].title()}</a>
            </div>
            {note_section}
        </div>
        """)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Smart Copilot — Daily Action Digest</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 2rem; }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        header {{ text-align: center; margin-bottom: 2rem; border-bottom: 1px solid #334155; padding-bottom: 1.5rem; }}
        h1 {{ font-size: 1.8rem; margin: 0 0 0.5rem 0; color: #38bdf8; }}
        p.subtitle {{ color: #94a3b8; margin: 0; }}
        .job-card {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.25rem; transition: all 0.2s; }}
        .job-card.applied {{ border-color: #22c55e; background: #0f291e; opacity: 0.85; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1rem; }}
        h3 {{ margin: 0 0 0.25rem 0; font-size: 1.2rem; }}
        .company-sub {{ font-size: 0.9rem; color: #94a3b8; }}
        .plat {{ background: #475569; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; color: #fff; }}
        .score-badge {{ font-weight: bold; padding: 6px 12px; border-radius: 8px; font-size: 0.95rem; }}
        .badge-high {{ background: #166534; color: #86efac; border: 1px solid #22c55e; }}
        .badge-med {{ background: #854d0e; color: #fef08a; border: 1px solid #eab308; }}
        .badge-low {{ background: #7f1d1d; color: #fca5a5; }}
        .card-actions {{ display: flex; gap: 0.75rem; align-items: center; margin-top: 1rem; flex-wrap: wrap; }}
        .btn {{ display: inline-block; padding: 8px 16px; border-radius: 6px; font-size: 0.9rem; text-decoration: none; font-weight: 500; cursor: pointer; border: none; }}
        .btn-apply {{ background: #2563eb; color: #fff; }}
        .btn-apply:hover {{ background: #1d4ed8; }}
        .btn-pdf {{ background: #059669; color: #fff; }}
        .btn-pdf:hover {{ background: #047857; }}
        .btn-copy {{ background: #475569; color: #fff; font-size: 0.8rem; margin-top: 0.5rem; }}
        .btn-copy:hover {{ background: #64748b; }}
        .btn-mark {{ background: #334155; color: #94a3b8; }}
        .btn-mark:hover {{ background: #475569; color: #fff; }}
        .note-box {{ background: #0f172a; border: 1px dashed #475569; border-radius: 8px; padding: 0.75rem 1rem; margin-top: 1rem; }}
        .note-text {{ margin: 0; font-size: 0.88rem; color: #cbd5e1; font-style: italic; }}
        .skipped-label {{ color: #94a3b8; font-size: 0.85rem; font-style: italic; }}
    </style>
    <script>
        function markApplied(cardId, compName) {{
            const card = document.getElementById(cardId);
            if (card) {{
                card.classList.toggle('applied');
                const isApp = card.classList.contains('applied');
                localStorage.setItem('applied_' + compName, isApp ? '1' : '0');
                const btn = card.querySelector('.btn-mark');
                if (btn) btn.innerText = isApp ? '✓ Applied' : 'Mark as Applied';
            }}
        }}
        window.addEventListener('DOMContentLoaded', () => {{
            document.querySelectorAll('.job-card').forEach(card => {{
                const comp = card.getAttribute('data-comp');
                if (comp && localStorage.getItem('applied_' + comp) === '1') {{
                    card.classList.add('applied');
                    const btn = card.querySelector('.btn-mark');
                    if (btn) btn.innerText = '✓ Applied';
                }}
            }});
        }});
    </script>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎯 Smart Copilot Action Digest</h1>
            <p class="subtitle">Candidate: <strong>{candidate_name}</strong> • High-Impact Target Roles</p>
        </header>
        {"".join(cards_html)}
    </div>
</body>
</html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def cmd_morning_run(args: argparse.Namespace) -> None:
    """Automated daily morning job discovery, filtering, tailoring, and git update."""
    import subprocess
    import yaml
    from datetime import datetime, timezone
    from autoapply.core.discovery import discover_linkedin_jobs
    from autoapply.core.tailor import ResumeTailor
    from autoapply.core.pdf_generator import generate_resume_pdf
    from autoapply.tracker.db import get_engine, get_session, init_db
    from autoapply.tracker.models import Job, Application
    from autoapply.config.schemas import ResumeData
    from sqlmodel import select

    settings = Settings()
    min_score = args.min_score or 70
    max_search_jobs = args.max_jobs or 12

    console.print("[bold cyan]🌅 Starting Morning Automated Job Discovery...[/bold cyan]")

    # 1. Scrape latest jobs posted in past 24 hours
    discovered_jobs = discover_linkedin_jobs(
        keywords="Java Spring Boot Kafka",
        location="Bengaluru, Karnataka, India",
        posted_within_hours=24,
        max_jobs=max_search_jobs,
    )

    if not discovered_jobs:
        console.print("[yellow]No new jobs found in the past 24 hours.[/yellow]")
        return

    # 2. Load master resume & DB
    engine = get_engine(settings.db_path)
    init_db(engine)

    with open("config/master_resume.yaml") as f:
        resume = ResumeData.model_validate(yaml.safe_load(f))

    tailor = ResumeTailor(api_key=settings.gemini_api_key)

    new_matches = 0
    all_digest_items = []

    with get_session(engine) as session:
        for item in discovered_jobs:
            url = item["url"]
            # Deduplicate against existing DB entries
            existing_job = session.exec(select(Job).where(Job.url == url)).first()
            if existing_job:
                logger.info(f"Skipping already tracked job: {item['company']}")
                continue

            # ATS Score
            kw = tailor.extract_jd_keywords(item["jd_text"])
            score_res = tailor.estimate_ats_score(resume, kw)
            score = score_res["score"]

            name_clean = resume.name.strip().replace(" ", "_")
            comp_clean = item["company"].strip().replace(" ", "_")
            role_clean = item["title"].strip().replace(" ", "_").replace("/", "_").replace("-", "_")
            pdf_filename = f"{name_clean}_{comp_clean}_{role_clean}.pdf"
            pdf_path = Path(f"data/generated_resumes/{pdf_filename}")

            if score >= min_score:
                # Tailor & generate PDF
                tailored = tailor.tailor_resume(resume, item["jd_text"], kw)
                generate_resume_pdf(tailored.model_dump(), str(pdf_path))

                cover_note = tailor.generate_cover_note(resume, item["jd_text"])
                pdf_path.with_suffix(".txt").write_text(cover_note, encoding="utf-8")

                # Insert Job & Application
                job_rec = Job(
                    platform="linkedin",
                    title=item["title"],
                    company=item["company"],
                    location=item["location"],
                    url=url,
                    jd_text=item["jd_text"],
                )
                session.add(job_rec)
                session.commit()
                session.refresh(job_rec)

                app_rec = Application(
                    job_id=job_rec.id,
                    platform="linkedin",
                    status="ready_to_apply",
                    tailored_resume_path=str(pdf_path),
                    ats_score=score,
                    notes=cover_note,
                )
                session.add(app_rec)
                session.commit()
                new_matches += 1

                all_digest_items.append({
                    "id": app_rec.id,
                    "company": item["company"],
                    "role": item["title"],
                    "platform": "linkedin",
                    "location": item["location"],
                    "url": url,
                    "score": score,
                    "pdf_path": str(pdf_path),
                    "pdf_name": pdf_filename,
                    "cover_note": cover_note,
                    "recommended": True,
                })

    console.print(f"[bold green]✓ Discovered & tailored {new_matches} high-match jobs (≥{min_score}% ATS)![/bold green]")

    # 3. Update HTML Dashboard
    dashboard_path = Path("data/copilot_dashboard.html")
    _render_copilot_html(all_digest_items, resume.name, dashboard_path)

    # 4. Auto Git Commit
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    commit_msg = f"chore(morning-digest): {today_str} automated jobs digest ({new_matches} new matched roles)"
    try:
        subprocess.run(["git", "add", "data/"], check=False)
        res = subprocess.run(["git", "commit", "-m", commit_msg], capture_output=True, text=True)
        if res.returncode == 0:
            console.print(f"[green]✓ Git commit created: [dim]{commit_msg}[/dim][/green]")
        else:
            console.print("[dim]Git working tree clean (no new files to commit).[/dim]")
    except Exception as e:
        logger.warning(f"Git commit failed: {e}")


def cmd_mark_applied(args: argparse.Namespace) -> None:
    """Mark a job application as applied in SQLite DB."""
    from autoapply.tracker.db import get_engine, get_session
    from autoapply.tracker.models import Application, Job
    from sqlmodel import select
    from datetime import datetime, timezone

    settings = Settings()
    engine = get_engine(settings.db_path)

    with get_session(engine) as session:
        if args.id:
            app = session.get(Application, args.id)
        elif args.company:
            statement = select(Application).join(Job).where(Job.company.ilike(f"%{args.company}%"))
            app = session.exec(statement).first()
        else:
            console.print("[red]Provide --id or --company[/red]")
            return

        if not app:
            console.print("[red]Application not found in database.[/red]")
            return

        app.status = "applied"
        app.applied_at = datetime.now(timezone.utc)
        session.add(app)
        session.commit()
        console.print(f"[bold green]✓ Marked application #{app.id} as APPLIED at {app.applied_at}[/bold green]")


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="autoapply",
        description="AutoApply — Automated job application system with AI-powered resume tailoring",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # tailor
    p_tailor = subparsers.add_parser("tailor", help="Tailor resume for a specific JD")
    p_tailor.add_argument("--jd", type=str, help="Job description text")
    p_tailor.add_argument("--jd-file", type=str, help="Path to JD text file")
    p_tailor.add_argument("--company", "-c", type=str, help="Company name (e.g. Capgemini)")
    p_tailor.add_argument("--role", type=str, help="Role name (e.g. Java_Kafka)")
    p_tailor.add_argument("--resume", type=str, help="Path to master resume YAML")
    p_tailor.add_argument("--output", "-o", type=str, help="Output PDF path")
    p_tailor.set_defaults(func=cmd_tailor)

    # apply
    p_apply = subparsers.add_parser("apply", help="Run manual apply session")
    p_apply.add_argument("--platform", "-p", required=True, choices=["linkedin", "naukri", "instahyre"])
    p_apply.add_argument("--max", type=int, help="Max applications this run")
    p_apply.set_defaults(func=cmd_apply)

    # schedule
    p_schedule = subparsers.add_parser("schedule", help="Start scheduler daemon")
    p_schedule.add_argument("--start", action="store_true", default=True)
    p_schedule.set_defaults(func=cmd_schedule)

    # status
    p_status = subparsers.add_parser("status", help="Show today's application stats")
    p_status.set_defaults(func=cmd_status)

    # ats-check
    p_ats = subparsers.add_parser("ats-check", help="ATS compatibility check")
    p_ats.add_argument("--resume", "-r", required=True, help="Path to PDF resume")
    p_ats.add_argument("--verbose", "-v", action="store_true", help="Show extracted text")
    p_ats.set_defaults(func=cmd_ats_check)

    # copilot
    p_copilot = subparsers.add_parser("copilot", help="Run Smart Copilot batch matching and action digest")
    p_copilot.add_argument("--jobs-file", "-f", type=str, help="Path to jobs YAML (default: config/jobs.yaml)")
    p_copilot.add_argument("--min-score", "-m", type=int, default=65, help="Minimum ATS score threshold to generate resume")
    p_copilot.set_defaults(func=cmd_copilot)

    # morning-run
    p_morning = subparsers.add_parser("morning-run", help="Run automated morning job discovery, filtering, and git digest")
    p_morning.add_argument("--min-score", "-m", type=int, default=70, help="Minimum ATS score threshold (default: 70)")
    p_morning.add_argument("--max-jobs", type=int, default=10, help="Max jobs to discover and detail (default: 10)")
    p_morning.set_defaults(func=cmd_morning_run)

    # mark-applied
    p_applied = subparsers.add_parser("mark-applied", help="Mark a job as applied in tracker database")
    p_applied.add_argument("--id", type=int, help="Application ID to mark applied")
    p_applied.add_argument("--company", "-c", type=str, help="Company name to mark applied")
    p_applied.set_defaults(func=cmd_mark_applied)

    return parser


def main() -> None:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        args.func(args)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
