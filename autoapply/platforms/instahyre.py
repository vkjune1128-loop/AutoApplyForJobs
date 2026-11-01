"""Instahyre auto-apply automation."""

from __future__ import annotations

import random
import time
from typing import Any
from urllib.parse import quote_plus

from autoapply.config.schemas import JobFilter
from autoapply.platforms.base import ApplicationResult, BasePlatformApplier, Job
from autoapply.utils.logger import get_logger

logger = get_logger(__name__)


class InstahyreApplier(BasePlatformApplier):
    """Instahyre job application automation.

    Instahyre has a unique model: recruiters reach out to candidates, but candidates
    can also express interest in listed jobs. The "Apply" is more of an "Interested" action.
    """

    platform_name = "instahyre"

    def login(self) -> bool:
        """Log in to Instahyre.

        Returns:
            True if login succeeded.
        """
        page = self.browser.new_page()

        try:
            page.goto("https://www.instahyre.com/", wait_until="domcontentloaded", timeout=15000)
            time.sleep(random.uniform(2.0, 4.0))

            # Check if already logged in
            # TODO: Verify logged-in indicator — Instahyre may show user avatar or dashboard link
            if "candidate" in page.url or page.query_selector('a[href*="candidate"]'):
                logger.info("Already logged in via persistent session")
                page.close()
                return True

            # Navigate to login
            page.goto(
                "https://www.instahyre.com/login/",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            time.sleep(random.uniform(1.5, 2.5))

            # Fill credentials
            # TODO: Verify Instahyre login form selectors:
            #   - Email: 'input[name="email"]' or 'input#email'
            #   - Password: 'input[name="password"]' or 'input#password'
            #   - Submit: 'button[type="submit"]' or 'input[type="submit"]'
            page.fill('input[name="email"], input#email', self.settings.instahyre_email)
            time.sleep(random.uniform(0.3, 0.7))
            page.fill('input[name="password"], input#password', self.settings.instahyre_password)
            time.sleep(random.uniform(0.3, 0.7))

            page.click('button[type="submit"], input[type="submit"]')
            time.sleep(random.uniform(3.0, 5.0))

            # Verify login
            if "candidate" in page.url:
                logger.info("Instahyre login successful")
                page.close()
                return True

            logger.warning("Instahyre login may have failed")
            page.close()
            return False

        except Exception as e:
            logger.error(f"Instahyre login error: {e}")
            page.close()
            return False

    def search_jobs(self, filters: JobFilter) -> list[Job]:
        """Search Instahyre for job opportunities.

        Instahyre shows job recommendations to candidates. We navigate to the
        jobs/opportunities page and scrape listed positions.

        Args:
            filters: Search criteria.

        Returns:
            List of Job objects.
        """
        jobs: list[Job] = []
        page = self.browser.new_page()

        try:
            # Instahyre candidate dashboard / opportunities page
            # TODO: Verify the correct URL for job listings
            search_url = "https://www.instahyre.com/candidate/opportunities/"
            logger.info(f"Navigating to: {search_url}")

            page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(random.uniform(3.0, 5.0))

            # TODO: Apply filters if Instahyre supports URL-based filtering
            # Instahyre may have filter controls on the page:
            #   - Location filter
            #   - Role/keyword filter
            #   - Experience filter

            # TODO: Parse job/opportunity cards
            # Instahyre opportunity card selectors to investigate:
            #   - Card container: 'div.opportunity-card' or 'div.opp-card'
            #   - Job title: 'h3.opp-title' or similar
            #   - Company: 'span.company-name'
            #   - Location: 'span.location'
            #   - "Interested" button: 'button.interested-btn'

            job_cards = page.query_selector_all(
                'div.opportunity-card, div.opp-card, div[class*="opportunity"]'
            )

            for card in job_cards[:30]:
                try:
                    title_el = card.query_selector('h3, h4, a[class*="title"]')
                    company_el = card.query_selector('span[class*="company"], div[class*="company"]')
                    location_el = card.query_selector('span[class*="location"]')
                    link_el = card.query_selector('a[href]')

                    title = title_el.inner_text().strip() if title_el else "Unknown"
                    company = company_el.inner_text().strip() if company_el else "Unknown"
                    location = location_el.inner_text().strip() if location_el else ""
                    href = link_el.get_attribute("href") if link_el else ""

                    # Filter by keywords
                    title_lower = title.lower()
                    keyword_match = any(
                        kw.lower() in title_lower for kw in filters.keywords
                    )
                    if filters.keywords and not keyword_match:
                        continue

                    jobs.append(Job(
                        platform="instahyre",
                        title=title,
                        company=company,
                        location=location,
                        url=href if href.startswith("http") else f"https://www.instahyre.com{href}",
                    ))

                except Exception as e:
                    logger.warning(f"Failed to parse Instahyre card: {e}")
                    continue

            logger.info(f"Parsed {len(jobs)} Instahyre opportunities")

        except Exception as e:
            logger.error(f"Instahyre search failed: {e}")
        finally:
            page.close()

        return jobs

    def apply_to_job(self, job: Job, resume_path: str | None = None) -> ApplicationResult:
        """Express interest in / apply to an Instahyre opportunity.

        Instahyre's flow is simpler than LinkedIn:
        1. Open the opportunity
        2. Click "I'm Interested" or "Apply"
        3. Optionally answer screening questions

        Args:
            job: The job/opportunity to apply to.
            resume_path: Not typically used — Instahyre uses profile resume.

        Returns:
            ApplicationResult with outcome.
        """
        page = self.browser.new_page()

        try:
            page.goto(job.url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(random.uniform(2.0, 4.0))

            # Extract JD
            # TODO: Verify JD container selector
            jd_el = page.query_selector('div[class*="description"], div[class*="jd"]')
            if jd_el:
                job.jd_text = jd_el.inner_text()

            # Find and click the interest/apply button
            # TODO: Verify button selectors — Instahyre uses "I'm Interested" or "Apply"
            apply_btn = page.query_selector(
                'button[class*="interested"], button[class*="apply"], '
                'a[class*="interested"], a[class*="apply"]'
            )

            if not apply_btn:
                logger.warning(f"No apply button found on Instahyre: {job.title}")
                page.close()
                return ApplicationResult(
                    success=False, status="skipped", message="No apply/interested button found"
                )

            btn_text = apply_btn.inner_text().lower()
            if "applied" in btn_text or "interested" in btn_text:
                # May already be applied
                if "already" in btn_text:
                    page.close()
                    return ApplicationResult(
                        success=False, status="skipped", message="Already applied on Instahyre"
                    )

            apply_btn.click()
            time.sleep(random.uniform(2.0, 4.0))

            # TODO: Handle any post-click confirmation or questionnaire

            logger.info(f"Expressed interest on Instahyre: {job.title} @ {job.company}")
            page.close()
            return ApplicationResult(
                success=True, status="applied",
                message=f"Applied to {job.title} @ {job.company}"
            )

        except Exception as e:
            logger.error(f"Instahyre apply error for {job.title}: {e}")
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
