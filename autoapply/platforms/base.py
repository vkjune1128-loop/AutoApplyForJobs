"""Abstract base class for platform job appliers."""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from autoapply.config.schemas import JobFilter
from autoapply.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Job:
    """Represents a scraped job listing."""

    platform: str
    title: str
    company: str
    location: str
    url: str
    jd_text: str = ""
    posted_date: str = ""
    easy_apply: bool = False


@dataclass
class ApplicationResult:
    """Result of attempting to apply to a job."""

    success: bool
    status: str  # "applied", "skipped", "failed", "dry_run"
    message: str = ""
    screenshot_path: str = ""


class BasePlatformApplier(ABC):
    """Base class that all platform appliers must inherit from.

    Provides a standard ``run()`` loop: login → search → filter → apply,
    with randomized human-like delays between actions.
    """

    platform_name: str = "base"

    def __init__(self, settings: Any, browser: Any, tracker: Any) -> None:
        """Initialize the applier.

        Args:
            settings: Application Settings instance.
            browser: Playwright BrowserContext with persistent state.
            tracker: SQLModel Session for tracking applications.
        """
        self.settings = settings
        self.browser = browser
        self.tracker = tracker

    @abstractmethod
    def login(self) -> bool:
        """Authenticate on the platform.

        Returns:
            True if login was successful.
        """
        ...

    @abstractmethod
    def search_jobs(self, filters: JobFilter) -> list[Job]:
        """Search for jobs matching the given filters.

        Args:
            filters: Search criteria.

        Returns:
            List of Job objects found.
        """
        ...

    @abstractmethod
    def apply_to_job(self, job: Job, resume_path: str | None = None) -> ApplicationResult:
        """Apply to a single job listing.

        Args:
            job: The job to apply to.
            resume_path: Optional path to a tailored resume PDF.

        Returns:
            ApplicationResult with status.
        """
        ...

    @abstractmethod
    def is_already_applied(self, job: Job) -> bool:
        """Check whether we've already applied to this job.

        Args:
            job: The job to check.

        Returns:
            True if already applied.
        """
        ...

    def run(self, filters: JobFilter, max_applications: int = 20) -> list[ApplicationResult]:
        """Orchestrate the full search → filter → apply pipeline.

        Args:
            filters: Search criteria for this platform.
            max_applications: Maximum number of applications this run.

        Returns:
            List of ApplicationResults.
        """
        results: list[ApplicationResult] = []

        logger.info(f"[{self.platform_name}] Starting apply run (max={max_applications})")

        # Step 1: Login
        if not self.login():
            logger.error(f"[{self.platform_name}] Login failed — aborting")
            return results

        logger.info(f"[{self.platform_name}] Login successful")
        time.sleep(random.uniform(2.0, 4.0))

        # Step 2: Search
        logger.info(f"[{self.platform_name}] Searching for jobs...")
        jobs = self.search_jobs(filters)
        logger.info(f"[{self.platform_name}] Found {len(jobs)} jobs")

        # Step 3: Filter and apply
        applied_count = 0
        for job in jobs:
            if applied_count >= max_applications:
                logger.info(f"[{self.platform_name}] Reached max applications ({max_applications})")
                break

            # Skip blacklisted companies
            if job.company.lower() in {c.lower() for c in filters.blacklisted_companies}:
                logger.info(f"[{self.platform_name}] Skipping blacklisted: {job.company}")
                results.append(ApplicationResult(
                    success=False, status="skipped", message=f"Blacklisted: {job.company}"
                ))
                continue

            # Skip already-applied jobs
            if self.is_already_applied(job):
                logger.info(f"[{self.platform_name}] Already applied: {job.title} @ {job.company}")
                results.append(ApplicationResult(
                    success=False, status="skipped", message="Already applied"
                ))
                continue

            # Dry run check
            if self.settings.dry_run:
                logger.info(
                    f"[{self.platform_name}] DRY RUN — would apply: {job.title} @ {job.company}"
                )
                results.append(ApplicationResult(
                    success=True, status="dry_run", message=f"{job.title} @ {job.company}"
                ))
                applied_count += 1
                continue

            # Apply
            logger.info(f"[{self.platform_name}] Applying: {job.title} @ {job.company}")
            result = self.apply_to_job(job)
            results.append(result)

            if result.success:
                applied_count += 1

            # Human-like delay between applications
            delay = random.uniform(30.0, 90.0)
            logger.info(f"[{self.platform_name}] Waiting {delay:.0f}s before next application...")
            time.sleep(delay)

        logger.info(
            f"[{self.platform_name}] Run complete — "
            f"{applied_count} applied, {len(results)} total processed"
        )

        return results
