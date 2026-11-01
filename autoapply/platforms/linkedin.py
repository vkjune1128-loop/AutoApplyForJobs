"""LinkedIn Easy Apply automation."""

from __future__ import annotations

import random
import time
from typing import Any
from urllib.parse import quote_plus

from autoapply.config.schemas import JobFilter
from autoapply.platforms.base import ApplicationResult, BasePlatformApplier, Job
from autoapply.utils.browser import random_delay, safe_click
from autoapply.utils.logger import get_logger

logger = get_logger(__name__)


class LinkedInApplier(BasePlatformApplier):
    """LinkedIn Easy Apply automation.

    Automates the flow: login → search → open listing → click Easy Apply → fill modal → submit.
    """

    platform_name = "linkedin"

    def login(self) -> bool:
        """Log in to LinkedIn.

        Returns:
            True if login was successful (or already logged in via persistent context).
        """
        page = self.browser.new_page()

        try:
            page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=15000)
            await_delay = random.uniform(2.0, 3.0)
            time.sleep(await_delay)

            # Check if already logged in (persistent browser context)
            if page.url.startswith("https://www.linkedin.com/feed"):
                logger.info("Already logged in via persistent session")
                page.close()
                return True

            # Navigate to login page
            page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
            time.sleep(random.uniform(1.0, 2.0))

            # Fill credentials
            # TODO: Handle LinkedIn's anti-bot detection — may need CAPTCHA solving or manual intervention
            page.fill('input#username', self.settings.linkedin_email)
            time.sleep(random.uniform(0.3, 0.8))
            page.fill('input#password', self.settings.linkedin_password)
            time.sleep(random.uniform(0.3, 0.8))

            page.click('button[type="submit"]')
            time.sleep(random.uniform(3.0, 5.0))

            # TODO: Handle 2FA / verification challenge
            # LinkedIn may prompt for phone verification or email verification code.
            # Options:
            #   1. Pause and wait for manual input
            #   2. Read verification code from email/SMS API
            #   3. Use persistent browser context to avoid re-login

            # Verify login success
            if "feed" in page.url or "mynetwork" in page.url:
                logger.info("LinkedIn login successful")
                page.close()
                return True

            logger.warning(f"Login may have failed — current URL: {page.url}")
            page.close()
            return False

        except Exception as e:
            logger.error(f"LinkedIn login error: {e}")
            page.close()
            return False

    def search_jobs(self, filters: JobFilter) -> list[Job]:
        """Search LinkedIn for jobs matching filters.

        Args:
            filters: Search criteria including keywords, locations, etc.

        Returns:
            List of Job objects scraped from search results.
        """
        jobs: list[Job] = []
        page = self.browser.new_page()

        try:
            # Build search URL
            keywords_query = quote_plus(" ".join(filters.keywords))
            location_query = quote_plus(filters.locations[0] if filters.locations else "India")

            # LinkedIn Jobs search URL construction
            # TODO: Map experience_level to LinkedIn's f_E parameter:
            #   1=Internship, 2=Entry, 3=Associate, 4=Mid-Senior, 5=Director, 6=Executive
            search_url = (
                f"https://www.linkedin.com/jobs/search/"
                f"?keywords={keywords_query}"
                f"&location={location_query}"
                f"&f_AL={'true' if filters.easy_apply_only else 'false'}"  # Easy Apply filter
                f"&f_TPR=r604800"  # Past week
                f"&sortBy=DD"  # Sort by date
            )

            logger.info(f"Searching: {search_url}")
            page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(random.uniform(3.0, 5.0))

            # TODO: Scroll through job listings to load more results
            # LinkedIn lazy-loads job cards as you scroll

            # TODO: Parse job cards from the search results page
            # Selectors to investigate (LinkedIn frequently changes these):
            #   - Job cards container: 'div.jobs-search-results-list'
            #   - Individual cards: 'li.jobs-search-results__list-item'
            #   - Job title: 'a.job-card-list__title'
            #   - Company name: 'span.job-card-container__primary-description'
            #   - Location: 'li.job-card-container__metadata-item'
            #   - Easy Apply badge: 'li.job-card-container__apply-method'

            # Placeholder: parse job listings
            job_cards = page.query_selector_all('div.job-card-container')

            for card in job_cards[:50]:  # Limit to 50 per search
                try:
                    title_el = card.query_selector('.job-card-list__title')
                    company_el = card.query_selector('.job-card-container__primary-description')
                    location_el = card.query_selector('.job-card-container__metadata-item')
                    link_el = card.query_selector('a.job-card-list__title')

                    title = title_el.inner_text().strip() if title_el else "Unknown"
                    company = company_el.inner_text().strip() if company_el else "Unknown"
                    location = location_el.inner_text().strip() if location_el else ""
                    href = link_el.get_attribute("href") if link_el else ""
                    url = f"https://www.linkedin.com{href}" if href and not href.startswith("http") else href

                    jobs.append(Job(
                        platform="linkedin",
                        title=title,
                        company=company,
                        location=location,
                        url=url or "",
                        easy_apply=True,  # We filtered for Easy Apply
                    ))

                except Exception as e:
                    logger.warning(f"Failed to parse job card: {e}")
                    continue

            logger.info(f"Parsed {len(jobs)} job listings")

        except Exception as e:
            logger.error(f"Job search failed: {e}")
        finally:
            page.close()

        return jobs

    def apply_to_job(self, job: Job, resume_path: str | None = None) -> ApplicationResult:
        """Apply to a LinkedIn Easy Apply job.

        Args:
            job: The job to apply to.
            resume_path: Optional path to a tailored resume PDF to upload.

        Returns:
            ApplicationResult with the outcome.
        """
        page = self.browser.new_page()

        try:
            page.goto(job.url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(random.uniform(2.0, 4.0))

            # TODO: Extract full JD text for tailoring
            # Selector: 'div.jobs-description__content'
            jd_el = page.query_selector('div.jobs-description__content')
            if jd_el:
                job.jd_text = jd_el.inner_text()

            # Click "Easy Apply" button
            # TODO: Verify selector — LinkedIn changes button selectors frequently
            easy_apply_btn = page.query_selector('button.jobs-apply-button')
            if not easy_apply_btn:
                logger.warning(f"No Easy Apply button found for: {job.title}")
                page.close()
                return ApplicationResult(
                    success=False, status="skipped", message="No Easy Apply button found"
                )

            easy_apply_btn.click()
            time.sleep(random.uniform(1.5, 3.0))

            # TODO: Handle multi-step Easy Apply modal
            # The modal may have multiple pages with different form fields:
            #   Page 1: Contact info (usually pre-filled)
            #   Page 2: Resume upload
            #   Page 3: Screening questions (years of experience, visa, etc.)
            #   Page 4: Review & submit
            #
            # Modal selectors to investigate:
            #   - Modal container: 'div.jobs-easy-apply-modal'
            #   - Next button: 'button[aria-label="Continue to next step"]'
            #   - Submit button: 'button[aria-label="Submit application"]'
            #   - Resume upload: 'input[type="file"]'
            #   - Form fields: 'div.jobs-easy-apply-form-section__grouping'

            # Step through modal pages
            max_steps = 5
            for step in range(max_steps):
                time.sleep(random.uniform(1.0, 2.0))

                # Check for screening questions and fill them
                self._handle_screening_questions(page)

                # Upload resume if file input is present
                if resume_path:
                    file_input = page.query_selector('input[type="file"]')
                    if file_input:
                        file_input.set_input_files(resume_path)
                        time.sleep(random.uniform(1.0, 2.0))

                # Look for submit button
                submit_btn = page.query_selector('button[aria-label="Submit application"]')
                if submit_btn:
                    submit_btn.click()
                    time.sleep(random.uniform(2.0, 3.0))
                    logger.info(f"Successfully applied: {job.title} @ {job.company}")
                    page.close()
                    return ApplicationResult(
                        success=True, status="applied",
                        message=f"Applied to {job.title} @ {job.company}"
                    )

                # Click next
                next_btn = page.query_selector('button[aria-label="Continue to next step"]')
                if next_btn:
                    next_btn.click()
                else:
                    # Try review button
                    review_btn = page.query_selector('button[aria-label="Review your application"]')
                    if review_btn:
                        review_btn.click()
                    else:
                        break

            logger.warning(f"Could not complete application for: {job.title}")
            page.close()
            return ApplicationResult(
                success=False, status="failed",
                message="Could not complete multi-step application"
            )

        except Exception as e:
            logger.error(f"Application error for {job.title}: {e}")
            page.close()
            return ApplicationResult(success=False, status="failed", message=str(e))

    def is_already_applied(self, job: Job) -> bool:
        """Check if already applied to this job via the tracker DB.

        Args:
            job: Job to check.

        Returns:
            True if a record exists in the tracker.
        """
        from autoapply.tracker.db import is_job_applied
        return is_job_applied(self.tracker, job.url)

    def _handle_screening_questions(self, page: Any) -> None:
        """Attempt to fill screening questions in the Easy Apply modal.

        Args:
            page: Playwright Page object.
        """
        # TODO: Load form_answers.yaml and match questions to answers
        # Common question patterns:
        #   - "How many years of experience do you have with X?"
        #   - "What is your expected salary?"
        #   - "Are you authorized to work in X?"
        #   - "Will you now or in the future require sponsorship?"
        #
        # Strategy:
        #   1. Find all visible form groups in the modal
        #   2. Extract the question label text
        #   3. Fuzzy-match against form_answers.yaml keys
        #   4. Fill in the matching answer
        #
        # Selectors to investigate:
        #   - Question label: 'label.t-14'
        #   - Text input: 'input.artdeco-text-input--input'
        #   - Dropdown: 'select'
        #   - Radio buttons: 'input[type="radio"]'
        #   - Checkbox: 'input[type="checkbox"]'

        # Placeholder: find and fill text inputs
        form_groups = page.query_selector_all('div.jobs-easy-apply-form-section__grouping')
        for group in form_groups:
            try:
                label_el = group.query_selector('label')
                input_el = group.query_selector('input[type="text"], input[type="number"]')

                if label_el and input_el:
                    label_text = label_el.inner_text().lower()
                    self._fill_form_field(input_el, label_text)
            except Exception:
                continue

    def _fill_form_field(self, input_el: Any, label_text: str) -> None:
        """Fill a single form field based on the question label.

        Args:
            input_el: Playwright input element.
            label_text: Lowercase text of the field's label.
        """
        # TODO: Load from config/form_answers.yaml dynamically
        # For now, use hardcoded fallback answers

        answer_map: dict[str, str] = {
            "years": "5",
            "experience": "5",
            "salary": "18",
            "ctc": "18",
            "notice": "30",
            "phone": "+91-XXXXXXXXXX",
        }

        for keyword, answer in answer_map.items():
            if keyword in label_text:
                current_value = input_el.input_value()
                if not current_value:
                    input_el.fill(answer)
                    logger.info(f"Filled '{keyword}' field with: {answer}")
                break
