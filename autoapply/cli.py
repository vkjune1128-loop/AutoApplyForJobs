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

    # Generate PDF
    output = args.output or "data/generated_resumes/tailored_resume.pdf"
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    generate_resume_pdf(tailored.model_dump(), output)
    console.print(f"[green]✓ Tailored resume saved to {output}[/green]")


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
