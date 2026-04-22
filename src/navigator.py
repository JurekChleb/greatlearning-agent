"""
Navigate to the Great Learning course page and locate the week panel.

navigator.py is intentionally kept thin — it opens the course URL and
returns the Page object so that discovery.py can do the actual content
matching. Screenshot + HTML dump are saved on any navigation failure.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import BrowserContext, Page

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import COURSE_URL, LOGS_DIR

logger = logging.getLogger(__name__)

LOGIN_URL_FRAGMENT = "login"
NAV_TIMEOUT_MS = 30_000


def _dump_debug(page: Page, label: str) -> None:
    """Save screenshot + HTML on failure for debugging selectors."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        page.screenshot(path=str(LOGS_DIR / f"{ts}_{label}.png"), full_page=True)
        (LOGS_DIR / f"{ts}_{label}.html").write_text(page.content(), encoding="utf-8")
        logger.info(f"Debug dump saved: {ts}_{label}.*")
    except Exception as e:
        logger.warning(f"Could not save debug dump: {e}")


def open_course(context: BrowserContext) -> Page:
    """
    Open the course dashboard using the saved session.

    Returns the Page at COURSE_URL.
    Raises SessionExpiredError if redirected to the login page.
    Raises RuntimeError on other navigation failures.
    """
    from src.auth import SessionExpiredError

    page = context.new_page()
    logger.info(f"Navigating to {COURSE_URL}")
    try:
        page.goto(COURSE_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    except Exception as e:
        _dump_debug(page, "nav_failed")
        raise RuntimeError(f"Navigation to course URL failed: {e}") from e

    if LOGIN_URL_FRAGMENT in page.url:
        _dump_debug(page, "session_expired")
        raise SessionExpiredError(
            "Session expired — redirected to login. "
            "Re-run `python src/login_once.py` to refresh the session."
        )

    logger.info(f"Course page loaded: {page.url}")
    return page


def find_week_panel(page: Page, week_number: int, topic: str) -> Page:
    """
    Navigate within the course page to the panel for the given week.

    Great Learning's course structure is dynamic — this function tries a
    set of heuristic strategies in order. After a successful navigation
    the page is returned so discovery.py can search for notebook links.

    NOTE: Once you run login_once.py and can see the real page structure,
    update the selectors below to match. The strategies are:

    1. Look for a sidebar/nav item whose text contains the week number or topic.
    2. Click it and wait for the content panel to update.
    3. If nothing matches, return the page as-is (discovery will handle it).
    """
    logger.info(f"Looking for week {week_number} panel (topic: {topic!r})")

    # Strategy 1: find a clickable element containing the week number
    week_patterns = [
        f"Week {week_number}",
        f"week {week_number}",
        f"Week{week_number}",
        topic,
    ]

    for pattern in week_patterns:
        try:
            locator = page.get_by_text(pattern, exact=False).first
            if locator.is_visible(timeout=3_000):
                logger.info(f"Found week panel via text {pattern!r} — clicking")
                locator.click()
                page.wait_for_load_state("networkidle", timeout=10_000)
                return page
        except Exception:
            continue

    # Strategy 2: look for an <a> or <li> whose href/data attribute references the week
    try:
        locator = page.locator(
            f"[data-week='{week_number}'], [data-module='{week_number}'], "
            f"li:has-text('Week {week_number}'), a:has-text('Week {week_number}')"
        ).first
        if locator.is_visible(timeout=3_000):
            logger.info(f"Found week panel via attribute selector — clicking")
            locator.click()
            page.wait_for_load_state("networkidle", timeout=10_000)
            return page
    except Exception:
        pass

    logger.warning(
        f"Could not find a clickable element for week {week_number}. "
        "Returning page as-is — discovery will search the full panel."
    )
    _dump_debug(page, f"week{week_number}_panel_not_found")
    return page
