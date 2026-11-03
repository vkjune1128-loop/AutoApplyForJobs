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

            # Cover note & referral pitch
            cover_note = tailor.generate_cover_note(resume, jd)
            referral_note = tailor.generate_referral_note(resume, company, role)
            note_file = pdf_path.with_suffix(".txt")
            note_file.write_text(f"--- Recruiter Note ---\n{cover_note}\n\n--- Referral Pitch ---\n{referral_note}\n", encoding="utf-8")

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
            referral_note = ""

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
            "referral_note": referral_note,
            "recommended": score >= min_score,
        })

    console.print(table)

    # Fetch applied history for complete GitHub digest
    from autoapply.presentation.digest import render_copilot_html, render_daily_digest_markdown
    from sqlmodel import select

    applied_items = []
    with get_session(engine) as session:
        applied_stmt = select(Application, Job).join(Job).where(Application.status == "applied").order_by(Application.applied_at.desc())
        all_applied = session.exec(applied_stmt).all()
        seen_applied = set()
        for app_rec, job_rec in all_applied:
            if job_rec.url in seen_applied:
                continue
            seen_applied.add(job_rec.url)
            pdf_p = Path(app_rec.tailored_resume_path) if app_rec.tailored_resume_path else None
            applied_str = app_rec.applied_at.strftime("%Y-%m-%d %H:%M UTC") if app_rec.applied_at else "-"
            applied_items.append({
                "id": app_rec.id,
                "company": job_rec.company,
                "role": job_rec.title,
                "platform": job_rec.platform,
                "location": job_rec.location,
                "score": app_rec.ats_score,
                "pdf_path": str(pdf_p) if pdf_p else None,
                "pdf_name": pdf_p.name if pdf_p else None,
                "applied_at": applied_str,
            })

    # Generate HTML Action Digest Dashboard & Markdown Summary
    digest_html_path = Path("data/copilot_dashboard.html")
    render_copilot_html(digest_items, resume.name, digest_html_path)
    console.print(f"\n[bold green]✓ Action Dashboard generated at:[/bold green] [underline]{digest_html_path}[/underline]")

    digest_md_path = Path("DAILY_DIGEST.md")
    render_daily_digest_markdown(digest_items, resume.name, digest_md_path, applied_items=applied_items)
    console.print(f"[bold green]✓ GitHub Digest Markdown generated at:[/bold green] [underline]{digest_md_path}[/underline]")


def cmd_morning_run(args: argparse.Namespace) -> None:
    """Automated daily morning job discovery, filtering, tailoring, and git update."""
    import subprocess
    import yaml
    from datetime import datetime, timezone
    from autoapply.core.discovery import discover_multi_source_jobs
    from autoapply.core.tailor import ResumeTailor
    from autoapply.core.pdf_generator import generate_resume_pdf
    from autoapply.tracker.db import get_engine, get_session, init_db
    from autoapply.tracker.models import Job, Application
    from autoapply.config.schemas import ResumeData
    from autoapply.presentation.digest import render_copilot_html, render_daily_digest_markdown
    from sqlmodel import select

    settings = Settings()
    min_score = args.min_score or 70
    max_search_jobs = args.max_jobs or 12

    # Dynamic search configuration from config/job_filters.yaml
    filters_path = Path("config/job_filters.yaml")
    search_kw = "Java Spring Boot Kafka"
    search_loc = "Bengaluru, Karnataka, India"
    if filters_path.exists():
        try:
            with open(filters_path) as f:
                f_data = yaml.safe_load(f) or {}
            li_f = f_data.get("linkedin", {})
            if li_f.get("keywords"):
                search_kw = " ".join(li_f["keywords"])
            if li_f.get("locations"):
                search_loc = li_f["locations"][0]
        except Exception as e:
            logger.warning(f"Could not load filters from {filters_path}: {e}")

    console.print(f"[bold cyan]🌅 Starting Multi-Source Morning Discovery for '{search_kw}' in '{search_loc}'...[/bold cyan]")

    # 1. Scrape latest jobs across Instahyre, Direct ATS, and LinkedIn
    discovered_jobs = discover_multi_source_jobs(
        keywords=search_kw,
        location=search_loc,
        posted_within_hours=24,
        max_total_jobs=max_search_jobs,
    )

    if not discovered_jobs:
        console.print("[yellow]No new jobs found in the past 24 hours.[/yellow]")
        return

    # 2. Load master resume & DB
    engine = get_engine(settings.db_path)
    init_db(engine)

    # 0. Sync previously closed GitHub Issues back to DB before discovery (Two-Way Sync)
    from autoapply.platforms.github_issues import sync_closed_issues_to_db, create_or_update_digest_issue

    try:
        synced_count = sync_closed_issues_to_db(engine, settings)
        if synced_count > 0:
            console.print(f"[bold green]✓ Synced {synced_count} application(s) from closed GitHub issues into DB![/bold green]")
    except Exception as e:
        logger.warning(f"GitHub issues pre-sync skipped: {e}")

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
                ref_pitch = tailor.generate_referral_note(resume, item["company"], item["title"])
                pdf_path.with_suffix(".txt").write_text(
                    f"--- Recruiter Note ---\n{cover_note}\n\n--- Referral Pitch ---\n{ref_pitch}\n",
                    encoding="utf-8",
                )

                # Insert Job & Application
                job_platform = item.get("platform", "linkedin")
                job_rec = Job(
                    platform=job_platform,
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
                    platform=job_platform,
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
                    "platform": job_platform,
                    "location": item["location"],
                    "url": url,
                    "score": score,
                    "pdf_path": str(pdf_path),
                    "pdf_name": pdf_filename,
                    "cover_note": cover_note,
                    "referral_note": ref_pitch,
                    "recommended": True,
                })

    console.print(f"[bold green]✓ Discovered & tailored {new_matches} high-match jobs (≥{min_score}% ATS)![/bold green]")

    # 3. Update HTML Dashboard and DAILY_DIGEST.md with all active ready-to-apply roles
    with get_session(engine) as session:
        statement = select(Application, Job).join(Job).where(Application.status == "ready_to_apply").order_by(Application.id.desc())
        all_active = session.exec(statement).all()
        seen_urls = set()
        active_digest_items = []
        for app_rec, job_rec in all_active:
            if job_rec.url in seen_urls:
                continue
            seen_urls.add(job_rec.url)
            pdf_p = Path(app_rec.tailored_resume_path) if app_rec.tailored_resume_path else None
            ref_pitch = tailor.generate_referral_note(resume, job_rec.company, job_rec.title)
            active_digest_items.append({
                "id": app_rec.id,
                "company": job_rec.company,
                "role": job_rec.title,
                "platform": job_rec.platform,
                "location": job_rec.location,
                "url": job_rec.url,
                "score": app_rec.ats_score,
                "pdf_path": str(pdf_p) if pdf_p else None,
                "pdf_name": pdf_p.name if pdf_p else None,
                "cover_note": app_rec.notes or "",
                "referral_note": ref_pitch,
                "recommended": True,
            })

        # Applied applications history
        applied_stmt = select(Application, Job).join(Job).where(Application.status == "applied").order_by(Application.applied_at.desc())
        all_applied = session.exec(applied_stmt).all()
        applied_digest_items = []
        seen_applied = set()
        for app_rec, job_rec in all_applied:
            if job_rec.url in seen_applied:
                continue
            seen_applied.add(job_rec.url)
            pdf_p = Path(app_rec.tailored_resume_path) if app_rec.tailored_resume_path else None
            applied_str = app_rec.applied_at.strftime("%Y-%m-%d %H:%M UTC") if app_rec.applied_at else "-"
            applied_digest_items.append({
                "id": app_rec.id,
                "company": job_rec.company,
                "role": job_rec.title,
                "platform": job_rec.platform,
                "location": job_rec.location,
                "score": app_rec.ats_score,
                "pdf_path": str(pdf_p) if pdf_p else None,
                "pdf_name": pdf_p.name if pdf_p else None,
                "applied_at": applied_str,
            })

    dashboard_path = Path("data/copilot_dashboard.html")
    render_copilot_html(active_digest_items, resume.name, dashboard_path)

    digest_md_path = Path("DAILY_DIGEST.md")
    render_daily_digest_markdown(active_digest_items, resume.name, digest_md_path, applied_items=applied_digest_items)
    console.print(f"[bold green]✓ GitHub Digest Markdown generated at:[/bold green] [underline]{digest_md_path}[/underline]")

    # 4. Auto Git Commit and Push
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    commit_msg = f"chore(morning-digest): {today_str} automated jobs digest ({new_matches} new matched roles)"
    try:
        subprocess.run(["git", "add", "data/", "DAILY_DIGEST.md"], check=False)
        res = subprocess.run(["git", "commit", "-m", commit_msg], capture_output=True, text=True)
        if res.returncode == 0:
            console.print(f"[green]✓ Git commit created: [dim]{commit_msg}[/dim][/green]")
            remotes = subprocess.run(["git", "remote"], capture_output=True, text=True).stdout.strip()
            if remotes:
                subprocess.run(["git", "pull", "--rebase", "origin", "main"], capture_output=True, text=True)
                push_res = subprocess.run(["git", "push", "origin", "HEAD"], capture_output=True, text=True)
                if push_res.returncode == 0:
                    console.print("[bold green]✓ Successfully pushed HTML digest and tailored resumes to Git origin/main![/bold green]")
                else:
                    console.print(f"[yellow]Git push warning (check remote auth/permissions): {push_res.stderr.strip()}[/yellow]")
            else:
                console.print("[dim]No remote origin set up yet; changes committed locally to git.[/dim]")
        else:
            console.print("[dim]Git working tree clean (no new files to commit).[/dim]")
    except Exception as e:
        logger.warning(f"Git commit/push failed: {e}")

    # 5. Create / Update GitHub Issue with @mention for instant mobile push notification
    try:
        issue_num = create_or_update_digest_issue(active_digest_items, resume.name, settings)
        if issue_num:
            console.print(f"[bold green]✓ GitHub Issue #{issue_num} notified! Check your phone's GitHub app.[/bold green]")
    except Exception as e:
        logger.warning(f"GitHub issue notification skipped: {e}")


def cmd_sync_issues(args: argparse.Namespace) -> None:
    """Manually sync closed GitHub issues back to SQLite database."""
    from autoapply.platforms.github_issues import sync_closed_issues_to_db
    from autoapply.tracker.db import get_engine, init_db

    settings = Settings()
    engine = get_engine(settings.db_path)
    init_db(engine)

    console.print("[cyan]Syncing closed GitHub issues back to database...[/cyan]")
    synced = sync_closed_issues_to_db(engine, settings)
    if synced > 0:
        console.print(f"[bold green]✓ Successfully synced {synced} application(s) as APPLIED in database![/bold green]")
    else:
        console.print("[yellow]No newly closed digest issues to sync.[/yellow]")


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

    # sync-issues
    p_sync = subparsers.add_parser("sync-issues", help="Sync closed GitHub issues back to tracker database")
    p_sync.set_defaults(func=cmd_sync_issues)

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
