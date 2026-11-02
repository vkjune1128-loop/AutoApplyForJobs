"""Direct ATS feed crawlers for Greenhouse and Lever company career boards.

Bypasses third-party aggregators by querying company career endpoints directly.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from autoapply.utils.logger import get_logger

logger = get_logger(__name__)

# Curated list of Indian tech product companies and GCCs using public ATS APIs
LEVER_COMPANIES = ["meesho", "cred"]
GREENHOUSE_COMPANIES = ["groww"]


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
