"""Direct ATS feed crawlers for Greenhouse and Lever company career boards.

Bypasses third-party aggregators by querying company career endpoints directly.
"""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Any

from autoapply.utils.logger import get_logger

logger = get_logger(__name__)

# Curated list of Indian tech product companies and GCCs using public ATS APIs
LEVER_COMPANIES = ["meesho", "cred"]
GREENHOUSE_COMPANIES = ["inmobi", "groww"]


def _strip_html(raw_html: str) -> str:
    """Strip basic HTML tags to produce clean plain text."""
    clean = re.sub(r"<[^>]+>", " ", raw_html)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def discover_lever_jobs(
    companies: list[str] | None = None,
    keywords: list[str] | None = None,
    target_locations: list[str] | None = None,
) -> list[dict]:
    """Fetch live engineering postings directly from Lever career boards."""
    if companies is None:
        companies = LEVER_COMPANIES
    if keywords is None:
        keywords = ["backend", "java", "sde", "software", "microservices", "distributed", "platform"]
    if target_locations is None:
        target_locations = ["bangalore", "bengaluru", "gurgaon", "hyderabad", "india", "remote"]

    discovered: list[dict] = []

    for comp in companies:
        url = f"https://api.lever.co/v0/postings/{comp}?mode=json"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                postings = json.loads(resp.read().decode("utf-8"))

            for p in postings:
                title = p.get("text", "")
                title_lower = title.lower()
                loc = p.get("categories", {}).get("location", "")
                loc_lower = loc.lower()

                # Filter by location and tech relevance
                matches_loc = any(tl in loc_lower for tl in target_locations) or not loc
                matches_kw = any(kw in title_lower for kw in keywords)

                # Skip non-backend roles
                if any(bad in title_lower for bad in ["qa", "test", "product manager", "sales", "design", "security analyst"]):
                    continue

                if matches_loc and matches_kw:
                    desc_plain = p.get("descriptionPlain", "") or p.get("description", "")
                    hosted_url = p.get("hostedUrl", "")

                    jd_text = (
                        f"Company: {comp.title()}\n"
                        f"Role: {title}\n"
                        f"Location: {loc}\n"
                        f"Description:\n{desc_plain[:2000]}"
                    )

                    discovered.append({
                        "title": title,
                        "company": comp.title(),
                        "location": loc or "Bengaluru / India",
                        "url": hosted_url,
                        "jd_text": jd_text,
                        "platform": "direct_ats",
                    })
                    logger.info(f"✓ Found Direct ATS (Lever) role: {title} @ {comp.title()}")
        except Exception as e:
            logger.debug(f"Lever search skipped for {comp}: {e}")
            continue

    return discovered


def discover_greenhouse_jobs(
    companies: list[str] | None = None,
    keywords: list[str] | None = None,
    target_locations: list[str] | None = None,
) -> list[dict]:
    """Fetch live engineering postings directly from Greenhouse Boards APIs."""
    if companies is None:
        companies = GREENHOUSE_COMPANIES
    if keywords is None:
        keywords = ["backend", "java", "sde", "software", "microservices", "distributed", "platform"]
    if target_locations is None:
        target_locations = ["bangalore", "bengaluru", "gurgaon", "hyderabad", "india", "remote"]

    discovered: list[dict] = []

    for comp in companies:
        url = f"https://boards-api.greenhouse.io/v1/boards/{comp}/jobs?content=true"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                jobs = data.get("jobs", [])

            for j in jobs:
                title = j.get("title", "")
                title_lower = title.lower()
                loc = j.get("location", {}).get("name", "")
                loc_lower = loc.lower()

                # Filter by location and tech relevance
                matches_loc = any(tl in loc_lower for tl in target_locations) or not loc
                matches_kw = any(kw in title_lower for kw in keywords)

                # Skip non-backend roles
                if any(bad in title_lower for bad in ["qa", "test", "product manager", "sales", "design", "security analyst"]):
                    continue

                if matches_loc and matches_kw:
                    content_raw = j.get("content", "")
                    content_plain = _strip_html(content_raw)
                    hosted_url = j.get("absolute_url", "")

                    jd_text = (
                        f"Company: {comp.title()}\n"
                        f"Role: {title}\n"
                        f"Location: {loc}\n"
                        f"Description:\n{content_plain[:2000]}"
                    )

                    discovered.append({
                        "title": title,
                        "company": comp.title(),
                        "location": loc or "Bengaluru / India",
                        "url": hosted_url,
                        "jd_text": jd_text,
                        "platform": "direct_ats",
                    })
                    logger.info(f"✓ Found Direct ATS (Greenhouse) role: {title} @ {comp.title()}")
        except Exception as e:
            logger.debug(f"Greenhouse search skipped for {comp}: {e}")
            continue

    return discovered


def discover_direct_ats_jobs(
    lever_companies: list[str] | None = None,
    greenhouse_companies: list[str] | None = None,
    keywords: list[str] | None = None,
    target_locations: list[str] | None = None,
    max_jobs: int = 6,
) -> list[dict]:
    """Unified crawler for all direct company ATS boards (Lever + Greenhouse)."""
    all_jobs: list[dict] = []

    # 1. Lever
    try:
        lever_results = discover_lever_jobs(
            companies=lever_companies,
            keywords=keywords,
            target_locations=target_locations,
        )
        all_jobs.extend(lever_results)
    except Exception as e:
        logger.warning(f"Direct Lever crawl failed: {e}")

    # 2. Greenhouse
    try:
        gh_results = discover_greenhouse_jobs(
            companies=greenhouse_companies,
            keywords=keywords,
            target_locations=target_locations,
        )
        all_jobs.extend(gh_results)
    except Exception as e:
        logger.warning(f"Direct Greenhouse crawl failed: {e}")

    return all_jobs[:max_jobs]
