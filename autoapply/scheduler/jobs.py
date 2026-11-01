"""APScheduler job definitions for automated apply runs."""

from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from autoapply.utils.logger import get_logger

logger = get_logger(__name__)


def linkedin_job(settings: object) -> None:
    """Scheduled job: run LinkedIn Easy Apply session.

    Args:
        settings: Application Settings instance.
    """
    logger.info("[Scheduler] Running LinkedIn apply job")

    from autoapply.config.schemas import JobFilter
    from autoapply.tracker.db import get_engine, get_session, init_db
    from autoapply.utils.browser import launch_browser

    import yaml
    from pathlib import Path

    try:
        filters_path = Path("config/job_filters.yaml")
        with open(filters_path) as f:
            all_filters = yaml.safe_load(f)

        filters = JobFilter.model_validate(all_filters.get("linkedin", {}))

        engine = get_engine(settings.db_path)  # type: ignore[attr-defined]
        init_db(engine)

        browser, context = launch_browser(
            headless=settings.headless_browser,  # type: ignore[attr-defined]
            state_dir=str(Path(settings.data_dir) / "browser_state" / "linkedin"),  # type: ignore[attr-defined]
        )

        try:
            from autoapply.platforms.linkedin import LinkedInApplier

            with get_session(engine) as session:
                applier = LinkedInApplier(settings=settings, browser=context, tracker=session)
                applier.run(
                    filters=filters,
                    max_applications=settings.max_applications_per_day,  # type: ignore[attr-defined]
                )
        finally:
            context.close()
            browser.close()

    except Exception as e:
        logger.error(f"[Scheduler] LinkedIn job failed: {e}", exc_info=True)


def naukri_job(settings: object) -> None:
    """Scheduled job: run Naukri auto-apply session.

    Args:
        settings: Application Settings instance.
    """
    logger.info("[Scheduler] Running Naukri apply job")

    from autoapply.config.schemas import JobFilter
    from autoapply.tracker.db import get_engine, get_session, init_db
    from autoapply.utils.browser import launch_browser

    import yaml
    from pathlib import Path

    try:
        filters_path = Path("config/job_filters.yaml")
        with open(filters_path) as f:
            all_filters = yaml.safe_load(f)

        filters = JobFilter.model_validate(all_filters.get("naukri", {}))

        engine = get_engine(settings.db_path)  # type: ignore[attr-defined]
        init_db(engine)

        browser, context = launch_browser(
            headless=settings.headless_browser,  # type: ignore[attr-defined]
            state_dir=str(Path(settings.data_dir) / "browser_state" / "naukri"),  # type: ignore[attr-defined]
        )

        try:
            from autoapply.platforms.naukri import NaukriApplier

            with get_session(engine) as session:
                applier = NaukriApplier(settings=settings, browser=context, tracker=session)
                applier.run(
                    filters=filters,
                    max_applications=settings.max_applications_per_day,  # type: ignore[attr-defined]
                )
        finally:
            context.close()
            browser.close()

    except Exception as e:
        logger.error(f"[Scheduler] Naukri job failed: {e}", exc_info=True)


def instahyre_job(settings: object) -> None:
    """Scheduled job: run Instahyre auto-apply session.

    Args:
        settings: Application Settings instance.
    """
    logger.info("[Scheduler] Running Instahyre apply job")

    from autoapply.config.schemas import JobFilter
    from autoapply.tracker.db import get_engine, get_session, init_db
    from autoapply.utils.browser import launch_browser

    import yaml
    from pathlib import Path

    try:
        filters_path = Path("config/job_filters.yaml")
        with open(filters_path) as f:
            all_filters = yaml.safe_load(f)

        filters = JobFilter.model_validate(all_filters.get("instahyre", {}))

        engine = get_engine(settings.db_path)  # type: ignore[attr-defined]
        init_db(engine)

        browser, context = launch_browser(
            headless=settings.headless_browser,  # type: ignore[attr-defined]
            state_dir=str(Path(settings.data_dir) / "browser_state" / "instahyre"),  # type: ignore[attr-defined]
        )

        try:
            from autoapply.platforms.instahyre import InstahyreApplier

            with get_session(engine) as session:
                applier = InstahyreApplier(settings=settings, browser=context, tracker=session)
                applier.run(
                    filters=filters,
                    max_applications=settings.max_applications_per_day,  # type: ignore[attr-defined]
                )
        finally:
            context.close()
            browser.close()

    except Exception as e:
        logger.error(f"[Scheduler] Instahyre job failed: {e}", exc_info=True)


def create_scheduler(settings: object) -> BlockingScheduler:
    """Create and configure the APScheduler with platform jobs.

    Default schedule:
        - LinkedIn: 9:00 AM, 2:00 PM (Mon–Fri)
        - Naukri:   10:00 AM, 3:00 PM (Mon–Fri)
        - Instahyre: 11:00 AM (Mon–Fri)

    Args:
        settings: Application Settings instance.

    Returns:
        Configured BlockingScheduler (call .start() to run).
    """
    scheduler = BlockingScheduler()

    # LinkedIn — 9 AM and 2 PM, weekdays
    scheduler.add_job(
        linkedin_job,
        trigger=CronTrigger(hour=9, minute=0, day_of_week="mon-fri"),
        args=[settings],
        id="linkedin_morning",
        name="LinkedIn Morning Run",
    )
    scheduler.add_job(
        linkedin_job,
        trigger=CronTrigger(hour=14, minute=0, day_of_week="mon-fri"),
        args=[settings],
        id="linkedin_afternoon",
        name="LinkedIn Afternoon Run",
    )

    # Naukri — 10 AM and 3 PM, weekdays
    scheduler.add_job(
        naukri_job,
        trigger=CronTrigger(hour=10, minute=0, day_of_week="mon-fri"),
        args=[settings],
        id="naukri_morning",
        name="Naukri Morning Run",
    )
    scheduler.add_job(
        naukri_job,
        trigger=CronTrigger(hour=15, minute=0, day_of_week="mon-fri"),
        args=[settings],
        id="naukri_afternoon",
        name="Naukri Afternoon Run",
    )

    # Instahyre — 11 AM, weekdays
    scheduler.add_job(
        instahyre_job,
        trigger=CronTrigger(hour=11, minute=0, day_of_week="mon-fri"),
        args=[settings],
        id="instahyre_morning",
        name="Instahyre Morning Run",
    )

    logger.info("Scheduler configured with 5 jobs across 3 platforms")
    return scheduler
