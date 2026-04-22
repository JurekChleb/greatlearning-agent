"""
Playwright browser context management.

Loads a saved session from data/auth/storage_state.json so no password
is ever needed in code. If the session has expired (login page detected),
logs clearly and raises SessionExpiredError.
"""

import logging
import sys
from pathlib import Path
from typing import Generator
from contextlib import contextmanager

from playwright.sync_api import Browser, BrowserContext, Playwright, sync_playwright

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import STORAGE_STATE

logger = logging.getLogger(__name__)

LOGIN_URL_FRAGMENT = "login"


class SessionExpiredError(Exception):
    pass


UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@contextmanager
def browser_context(
    playwright: Playwright,
    headless: bool = True,
    user_agent: str = UA,
) -> Generator[BrowserContext, None, None]:
    """Yield an authenticated BrowserContext, raise SessionExpiredError if session is gone."""
    if not STORAGE_STATE.exists():
        raise FileNotFoundError(
            f"No saved session found at {STORAGE_STATE}. "
            "Run `python src/login_once.py` first."
        )

    browser: Browser = playwright.chromium.launch(headless=headless)
    context: BrowserContext = browser.new_context(
        storage_state=str(STORAGE_STATE),
        user_agent=user_agent,
        viewport={"width": 1280, "height": 900},
    )
    try:
        yield context
    finally:
        context.close()
        browser.close()


def check_session(playwright: Playwright) -> bool:
    """Return True if the saved session is still valid, False if expired."""
    from src.config import COURSE_URL
    try:
        with browser_context(playwright, headless=True) as ctx:
            page = ctx.new_page()
            page.goto(COURSE_URL, wait_until="domcontentloaded", timeout=30_000)
            if LOGIN_URL_FRAGMENT in page.url:
                logger.warning("Session expired — redirected to login page.")
                return False
            return True
    except FileNotFoundError:
        return False
