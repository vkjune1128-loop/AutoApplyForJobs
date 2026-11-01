"""Playwright browser helpers: launch, anti-detect, and interaction utilities."""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from autoapply.utils.logger import get_logger

logger = get_logger(__name__)

# Realistic user agents for anti-detection
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


def launch_browser(
    headless: bool = False,
    state_dir: str | None = None,
) -> tuple[Browser, BrowserContext]:
    """Launch a Playwright Chromium browser with persistent context.

    Uses realistic viewport, user agent, and locale settings to reduce
    detection by anti-bot systems.

    Args:
        headless: Whether to run the browser in headless mode.
        state_dir: Directory to store persistent browser state (cookies, localStorage).
            If None, uses a temporary non-persistent context.

    Returns:
        Tuple of (Browser, BrowserContext).
    """
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--no-sandbox",
        ],
    )

    user_agent = random.choice(_USER_AGENTS)

    context_kwargs: dict[str, Any] = {
        "viewport": {"width": 1366, "height": 768},
        "user_agent": user_agent,
        "locale": "en-IN",
        "timezone_id": "Asia/Kolkata",
        "permissions": [],
        "java_script_enabled": True,
    }

    if state_dir:
        # Ensure state directory exists
        Path(state_dir).mkdir(parents=True, exist_ok=True)
        context = browser.new_context(storage_state=_load_state(state_dir), **context_kwargs)
        # Save state on context close
        context.on("close", lambda: _save_state(context, state_dir))
    else:
        context = browser.new_context(**context_kwargs)

    # Inject anti-detection scripts
    context.add_init_script("""
        // Override navigator.webdriver
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        // Override chrome automation indicators
        window.chrome = { runtime: {} };
    """)

    logger.info(f"Browser launched (headless={headless}, state_dir={state_dir})")
    return browser, context


def _load_state(state_dir: str) -> str | None:
    """Load browser state from a JSON file if it exists.

    Args:
        state_dir: Directory containing the state file.

    Returns:
        Path to the state file, or None if it doesn't exist.
    """
    state_file = Path(state_dir) / "state.json"
    if state_file.exists():
        logger.info(f"Loading browser state from {state_file}")
        return str(state_file)
    return None


def _save_state(context: BrowserContext, state_dir: str) -> None:
    """Save browser state to a JSON file.

    Args:
        context: Playwright BrowserContext to save.
        state_dir: Directory to write the state file.
    """
    state_file = Path(state_dir) / "state.json"
    try:
        context.storage_state(path=str(state_file))
        logger.info(f"Browser state saved to {state_file}")
    except Exception as e:
        logger.warning(f"Failed to save browser state: {e}")


def random_delay(min_s: float = 1.0, max_s: float = 3.0) -> None:
    """Sleep for a random duration to simulate human behavior.

    Args:
        min_s: Minimum sleep duration in seconds.
        max_s: Maximum sleep duration in seconds.
    """
    delay = random.uniform(min_s, max_s)
    time.sleep(delay)


def safe_click(
    page: Page,
    selector: str,
    timeout: int = 5000,
    retries: int = 3,
) -> bool:
    """Click an element with retry and error handling.

    Args:
        page: Playwright Page object.
        selector: CSS selector for the element to click.
        timeout: Milliseconds to wait for the element.
        retries: Number of click attempts.

    Returns:
        True if the click succeeded, False otherwise.
    """
    for attempt in range(retries):
        try:
            page.wait_for_selector(selector, timeout=timeout)
            page.click(selector)
            logger.debug(f"Clicked: {selector}")
            return True
        except Exception as e:
            logger.warning(f"Click attempt {attempt + 1}/{retries} failed for '{selector}': {e}")
            time.sleep(random.uniform(0.5, 1.5))

    logger.error(f"Failed to click '{selector}' after {retries} attempts")
    return False
