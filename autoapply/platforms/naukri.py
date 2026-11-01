"""Naukri.com auto-apply automation."""

from __future__ import annotations

import random
import time
from typing import Any
from urllib.parse import quote_plus

from autoapply.config.schemas import JobFilter
from autoapply.platforms.base import ApplicationResult, BasePlatformApplier, Job
from autoapply.utils.logger import get_logger

logger = get_logger(__name__)


class NaukriApplier(BasePlatformApplier):
    """Naukri.com job application automation.

    Automates: login → search → click Apply → fill details → submit.
    Naukri is simpler than LinkedIn — most jobs have a direct "Apply" button
    that submits your profile directly.
    """

    platform_name = "naukri"

    def login(self) -> bool:
        """Log in to Naukri.com.

        Returns:
            True if login succeeded or session is still active.
        """
        page = self.browser.new_page()

        try:
            page.goto("https://www.naukri.com/", wait_until="domcontentloaded", timeout=15000)
            time.sleep(random.uniform(2.0, 4.0))

            # Check if already logged in (persistent context)
            # TODO: Verify logged-in indicator selector
            profile_icon = page.query_selector('div.nI-gNb-drawer__icon')
            if profile_icon:
                logger.info("Already logged in via persistent session")
                page.close()
                return True

            # Click login link
            # TODO: Verify selector for Naukri's login trigger
            login_link = page.query_selector('a[title="Jobseeker Login"]')
            if login_link:
                login_link.click()
                time.sleep(random.uniform(1.5, 2.5))

            # Fill credentials
            # TODO: Naukri login modal selectors — verify these:
            #   - Email input: 'input[placeholder="Enter your active Email ID / Username"]'
            #   - Password input: 'input[placeholder="Enter your password"]'
            #   - Submit: 'button[type="submit"]' or 'button.loginButton'
            page.fill('input[placeholder*="Email"]', self.settings.naukri_email)
            time.sleep(random.uniform(0.3, 0.7))
            page.fill('input[placeholder*="password"]', self.settings.naukri_password)
            time.sleep(random.uniform(0.3, 0.7))

            page.click('button[type="submit"]')
            time.sleep(random.uniform(3.0, 5.0))

            # TODO: Handle CAPTCHA if present
            # Naukri may show Google reCAPTCHA on login

            # Verify login
            if page.query_selector('div.nI-gNb-drawer__icon'):
                logger.info("Naukri login successful")
                page.close()
                return True

            logger.warning("Naukri login may have failed")
            page.close()
            return False

        except Exception as e:
            logger.error(f"Naukri login error: {e}")
            page.close()
            return False

    def search_jobs(self, filters: JobFilter) -> list[Job]:
        """Search Naukri for jobs matching filters.

        Args:
            filters: Search criteria.

        Returns:
            List of Job objects.
        """
        jobs: list[Job] = []
        page = self.browser.new_page()

        try:
            # Build Naukri search URL
            keywords_slug = "-".join(filters.keywords).lower().replace(" ", "-")
            location_slug = "-".join(filters.locations).lower().replace(" ", "-") if filters.locations else ""

            # Naukri URL pattern: /keyword-jobs-in-location
            # TODO: Add experience range filter via URL param qexp=4-8
            search_url = (
                f"https://www.naukri.com/{quote_plus(keywords_slug)}-jobs"
                f"{'-in-' + quote_plus(location_slug) if location_slug else ''}"
                f"?k={quote_plus(' '.join(filters.keywords))}"
            )

            if filters.experience_range:
                search_url += f"&experience={filters.experience_range}"

            logger.info(f"Searching: {search_url}")
            page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(random.uniform(3.0, 5.0))

            # TODO: Parse job cards from search results
            # Naukri job card selectors to investigate:
            #   - Job cards: 'article.jobTuple'
            #   - Job title: 'a.title'
            #   - Company: 'a.subTitle'
            #   - Location: 'li.location span'
            #   - Experience: 'li.experience span'
            #   - Salary: 'li.salary span'

            job_cards = page.query_selector_all('article.jobTuple, div.srp-jobtuple-wrapper')

            for card in job_cards[:50]:
                try:
                    title_el = card.query_selector('a.title, a.title')
                    company_el = card.query_selector('a.subTitle, a.comp-name')
                    location_el = card.query_selector('li.location span, span.locWdth')

                    title = title_el.inner_text().strip() if title_el else "Unknown"
                    company = company_el.inner_text().strip() if company_el else "Unknown"
                    location = location_el.inner_text().strip() if location_el else ""
                    url = title_el.get_attribute("href") if title_el else ""

                    jobs.append(Job(
                        platform="naukri",
                        title=title,
                        company=company,
                        location=location,
                        url=url or "",
                    ))

                except Exception as e:
                    logger.warning(f"Failed to parse Naukri job card: {e}")
                    continue

            logger.info(f"Parsed {len(jobs)} Naukri job listings")

        except Exception as e:
            logger.error(f"Naukri search failed: {e}")
        finally:
            page.close()

        return jobs

    def apply_to_job(self, job: Job, resume_path: str | None = None) -> ApplicationResult:
        """Apply to a job on Naukri.

        Naukri's apply flow is typically:
        1. Click "Apply" on the job page
        2. Optionally update profile / answer questions
        3. Confirm submission

        Args:
            job: The job to apply to.
            resume_path: Optional tailored resume path (Naukri primarily uses profile resume).

        Returns:
            ApplicationResult with outcome.
        """
        page = self.browser.new_page()

        try:
            page.goto(job.url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(random.uniform(2.0, 4.0))

            # Extract JD text
            # TODO: Verify selector for Naukri's JD section
            jd_el = page.query_selector('section.job-desc, div.job-desc')
            if jd_el:
                job.jd_text = jd_el.inner_text()

            # Find and click Apply button
            # TODO: Naukri has different apply button variants:
            #   - Direct apply: 'button#apply-button' or 'button.apply-button'
            #   - Apply on company site: redirects externally (skip these)
            #   - Already applied: button is disabled
            apply_btn = page.query_selector(
                'button#apply-button, button.apply-button, button[id*="apply"]'
            )

            if not apply_btn:
                logger.warning(f"No apply button found: {job.title}")
                page.close()
                return ApplicationResult(
                    success=False, status="skipped", message="No apply button found"
                )

            # Check if already applied
            btn_text = apply_btn.inner_text().lower()
            if "applied" in btn_text:
                page.close()
                return ApplicationResult(
                    success=False, status="skipped", message="Already applied on Naukri"
                )

            apply_btn.click()
            time.sleep(random.uniform(2.0, 4.0))

            # TODO: Handle post-click flow
            # After clicking Apply, Naukri may:
            #   1. Show a success toast → application complete
            #   2. Open a chatbot/questionnaire modal → fill answers
            #   3. Redirect to company's external ATS → skip or handle
            #   4. Ask to update resume → upload resume_path

            # Check for success indicators
            # TODO: Verify success selectors
            success_indicator = page.query_selector(
                'div.apply-message, span.apply-message, div[class*="success"]'
            )

            if success_indicator:
                logger.info(f"Successfully applied on Naukri: {job.title} @ {job.company}")
                page.close()
                return ApplicationResult(
                    success=True, status="applied",
                    message=f"Applied to {job.title} @ {job.company}"
                )

            # If a questionnaire appeared, try to fill it
            # TODO: Implement Naukri questionnaire handler

            logger.warning(f"Uncertain apply status for: {job.title}")
            page.close()
            return ApplicationResult(
                success=False, status="failed",
                message="Could not confirm application submission"
            )

        except Exception as e:
            logger.error(f"Naukri apply error for {job.title}: {e}")
            page.close()
            return ApplicationResult(success=False, status="failed", message=str(e))

    def is_already_applied(self, job: Job) -> bool:
        """Check tracker DB for prior application.

        Args:
            job: Job to check.

        Returns:
            True if already applied.
        """
        from autoapply.tracker.db import is_job_applied
        return is_job_applied(self.tracker, job.url)
