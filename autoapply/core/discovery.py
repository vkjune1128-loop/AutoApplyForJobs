"""Automated job discovery engine for LinkedIn, Naukri, and tech portals."""

from __future__ import annotations

import re
import time
from typing import Generator
from playwright.sync_api import sync_playwright

from autoapply.utils.logger import get_logger

logger = get_logger(__name__)


def discover_linkedin_jobs(
    keywords: str = "Java Spring Boot Kafka",
    location: str = "Bengaluru, Karnataka, India",
    posted_within_hours: int = 24,
    max_jobs: int = 15,
) -> list[dict]:
    """Search LinkedIn's public job board for recently posted roles.

    No login or authentication is required (uses guest search to avoid account risk).

    Args:
        keywords: Search query (e.g. "Java Spring Boot Kafka").
        location: City / Country (e.g. "Bengaluru, Karnataka, India").
        posted_within_hours: Lookback window (default: 24h).
        max_jobs: Maximum number of jobs to scrape details for.

    Returns:
        List of dicts: {"company", "title", "location", "url", "jd_text", "platform"}
    """
    logger.info(f"Starting automated LinkedIn discovery: '{keywords}' in '{location}'")

    # Time filter: r86400 = past 24 hours, r604800 = past week
    tpr_param = "r86400" if posted_within_hours <= 24 else "r604800"
    encoded_keywords = keywords.replace(" ", "%20")
    encoded_location = location.replace(" ", "%20").replace(",", "%2C")
    search_url = (
        f"https://www.linkedin.com/jobs/search?keywords={encoded_keywords}"
        f"&location={encoded_location}&f_TPR={tpr_param}&position=1&pageNum=0"
    )

    discovered: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        try:
            logger.info(f"Navigating to LinkedIn search: {search_url}")
            page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            # Scroll a few times to load job cards
            for _ in range(2):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1500)

            cards = page.query_selector_all(".job-search-card, .base-search-card")
            logger.info(f"Found {len(cards)} raw job cards")

            job_stubs = []
            for c in cards:
                if len(job_stubs) >= max_jobs * 2:
                    break
                t_elem = c.query_selector(".base-search-card__title")
                c_elem = c.query_selector(".base-search-card__subtitle")
                l_elem = c.query_selector(".job-search-card__location")
                link_elem = c.query_selector("a.base-card__full-link")

                if t_elem and c_elem and link_elem:
                    url = link_elem.get_attribute("href") or ""
                    clean_url = url.split("?")[0]
                    job_stubs.append({
                        "title": t_elem.inner_text().strip(),
                        "company": c_elem.inner_text().strip(),
                        "location": l_elem.inner_text().strip() if l_elem else location,
                        "url": clean_url,
                        "platform": "linkedin",
                    })

            # Fetch JD text for each job stub
            for stub in job_stubs:
                if len(discovered) >= max_jobs:
                    break
                try:
                    logger.info(f"Fetching JD: {stub['title']} @ {stub['company']}")
                    page.goto(stub["url"], timeout=20000, wait_until="domcontentloaded")
                    page.wait_for_timeout(1500)

                    desc_elem = (
                        page.query_selector(".show-more-less-html__markup")
                        or page.query_selector(".description__text")
                        or page.query_selector("section.show-more-less-html")
                    )

                    if desc_elem:
                        jd_text = desc_elem.inner_text().strip()
                        if len(jd_text) > 100:
                            stub["jd_text"] = jd_text
                            discovered.append(stub)
                            logger.info(f"✓ Scraped {stub['company']} ({len(jd_text)} chars)")
                except Exception as e:
                    logger.warning(f"Could not fetch JD for {stub['url']}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error during job discovery: {e}")
        finally:
            browser.close()

    logger.info(f"Discovered total of {len(discovered)} detailed job postings from LinkedIn")
    return discovered


def discover_instahyre_jobs(
    locations: list[str] | None = None,
    keywords: list[str] | None = None,
    max_jobs: int = 8,
) -> list[dict]:
    """Discover curated product company and startup tech jobs from Instahyre's public API.

    No browser overhead or login required. Returns clean, structured job metadata.
    """
    import json
    import urllib.request

    if locations is None:
        locations = ["Bangalore", "Gurgaon"]
    if keywords is None:
        keywords = ["java", "spring", "kafka", "microservices", "distributed", "backend"]

    discovered: list[dict] = []
    seen_urls: set[str] = set()

    for loc in locations:
        if len(discovered) >= max_jobs:
            break
        url = f"https://www.instahyre.com/api/v1/job_search?job_functions=10&location={loc}"
        try:
            logger.info(f"Querying Instahyre API for backend roles in '{loc}'")
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                objects = data.get("objects", [])
                for obj in objects:
                    if len(discovered) >= max_jobs:
                        break
                    pub_url = obj.get("public_url") or ""
                    if not pub_url or pub_url in seen_urls:
                        continue

                    obj_keywords = [k.lower() for k in obj.get("keywords", [])]
                    title = obj.get("title", "")
                    title_lower = title.lower()

                    # Exclude explicitly non-Java / non-backend roles
                    excluded_titles = ["python", "react", "frontend", "flutter", "ios", "android", "qa", "tester", "data scientist", "devops"]
                    if any(bad in title_lower for bad in excluded_titles) and not any(j in obj_keywords for j in ["java", "spring boot", "kafka"]):
                        continue

                    # Require Java / Spring / Kafka / Microservices stack relevance
                    has_core_skill = any(kw in obj_keywords for kw in ["java", "spring", "spring boot", "kafka", "microservices", "distributed systems"])
                    if not (has_core_skill or ("java" in title_lower)):
                        continue

                    company = obj.get("employer", {}).get("company_name", "Tech Company")
                    note = obj.get("employer", {}).get("instahyre_note", "")
                    skills_list = obj.get("keywords", [])
                    job_locations = obj.get("locations", loc)

                    jd_text = (
                        f"Company: {company}\n"
                        f"About Company: {note}\n"
                        f"Role: {title}\n"
                        f"Location: {job_locations}\n"
                        f"Required Tech Stack & Skills: {', '.join(skills_list)}\n"
                        f"Core Responsibilities: Design, develop, and maintain high-throughput distributed systems, "
                        f"REST APIs, and backend microservices using {', '.join(skills_list[:6])}."
                    )

                    seen_urls.add(pub_url)
                    discovered.append({
                        "title": title,
                        "company": company,
                        "location": job_locations,
                        "url": pub_url,
                        "jd_text": jd_text,
                        "platform": "instahyre",
                    })
                    logger.info(f"✓ Found Instahyre role: {title} @ {company} ({job_locations})")
        except Exception as e:
            logger.warning(f"Instahyre search failed for '{loc}': {e}")
            continue

    logger.info(f"Instahyre discovery found {len(discovered)} relevant backend roles")
    return discovered


def discover_multi_source_jobs(
    keywords: str = "Java Spring Boot Kafka",
    location: str = "Bengaluru, Karnataka, India",
    posted_within_hours: int = 24,
    max_total_jobs: int = 12,
) -> list[dict]:
    """Unified multi-source discovery engine across LinkedIn and Instahyre."""
    all_discovered: list[dict] = []
    seen_urls: set[str] = set()

    max_per_platform = max(3, max_total_jobs // 2)

    # 1. Discover via Instahyre (Fast API, high-growth product companies & unicorns)
    try:
        insta_jobs = discover_instahyre_jobs(
            locations=["Bangalore", "Gurgaon"],
            max_jobs=max_per_platform,
        )
        for j in insta_jobs:
            if j["url"] not in seen_urls:
                seen_urls.add(j["url"])
                all_discovered.append(j)
    except Exception as e:
        logger.warning(f"Instahyre multi-source discovery failed: {e}")

    # 2. Discover via LinkedIn (Past 24h public search for GCCs & enterprise tech)
    try:
        li_jobs = discover_linkedin_jobs(
            keywords=keywords,
            location=location,
            posted_within_hours=posted_within_hours,
            max_jobs=max_per_platform,
        )
        for j in li_jobs:
            if j["url"] not in seen_urls:
                seen_urls.add(j["url"])
                all_discovered.append(j)
    except Exception as e:
        logger.warning(f"LinkedIn multi-source discovery failed: {e}")

    logger.info(f"Unified discovery produced {len(all_discovered)} roles across platforms")
    return all_discovered
