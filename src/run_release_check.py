"""
Idempotent entry point — called by launchd every hour on Thursdays.

Exit conditions (do nothing, exit 0):
  1. Today is not a release Thursday in schedule.yaml
  2. This week is a break week
  3. This week is already in processed.json
  4. Notebook not yet available on the course page (retry next hour)

Exit 1 conditions (need human action):
  5. Session expired → "re-run login_once.py"
  6. Unexpected error
"""

import logging
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import COURSE_URL, STORAGE_STATE, WARSAW, WEEKS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schedule helpers
# ---------------------------------------------------------------------------

def _today_warsaw() -> date:
    return datetime.now(tz=WARSAW).date()


def _find_week_for_date(today: date) -> dict | None:
    for week in WEEKS:
        if week.get("skip") or week.get("break"):
            continue
        release = week.get("release_date")
        if not release:
            continue
        release_date = release if isinstance(release, date) else date.fromisoformat(str(release))
        if release_date == today:
            return week
    return None


def _find_stale_week(today: date) -> dict | None:
    """Return the most recent unprocessed past week, if any."""
    from src.state_manager import is_processed
    past = []
    for week in WEEKS:
        if week.get("break") or week.get("skip"):
            continue
        release = week.get("release_date")
        if not release:
            continue
        release_date = release if isinstance(release, date) else date.fromisoformat(str(release))
        if release_date < today and not is_processed(week["week"]):
            past.append((release_date, week))
    if past:
        past.sort(key=lambda x: x[0], reverse=True)
        return past[0][1]
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> int:
    today = _today_warsaw()
    logger.info(f"Warsaw date: {today}  ({today.strftime('%A')})")

    # Gate 1: is today a release Thursday?
    week = _find_week_for_date(today)
    if week is None:
        stale = _find_stale_week(today)
        if stale:
            logger.warning(
                f"Week {stale['week']} ({stale['release_date']}) was never processed — attempting recovery."
            )
            week = stale
        else:
            logger.info("No release scheduled for today. Exiting.")
            return 0

    week_number: int = week["week"]
    logger.info(f"Week {week_number}: {week.get('topic', '')}")

    # Gate 2: break week?
    if week.get("break"):
        logger.info(f"Week {week_number} is a break ({week.get('break_name', 'break')}). Exiting.")
        return 0

    # Gate 3: already processed?
    from src.state_manager import is_processed, mark_processed
    if is_processed(week_number):
        logger.info(f"Week {week_number} already processed. Exiting.")
        return 0

    # Gate 4: session file present?
    if not STORAGE_STATE.exists():
        logger.error("No saved session found. Run `python src/login_once.py` first.")
        return 1

    # Gather title hints from schedule
    title_hints: list[str] = []
    for resource in week.get("expected_resources", []):
        title_hints.extend(resource.get("title_hints", []))

    # Pipeline
    from playwright.sync_api import sync_playwright
    from src.auth import LOGIN_URL_FRAGMENT, browser_context
    from src.discovery import find_notebook
    from src.downloader import download
    from src.converter import convert
    from src.analyzer import analyze

    logger.info("Starting pipeline...")
    try:
        with sync_playwright() as pw:
            with browser_context(pw, headless=False) as ctx:

                # Open course page
                page = ctx.new_page()
                logger.info(f"Opening {COURSE_URL}")
                page.goto(COURSE_URL, wait_until="domcontentloaded", timeout=30_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=20_000)
                except Exception:
                    pass  # SPA may never fully idle; find_notebook waits for real content

                # Check session still valid
                if LOGIN_URL_FRAGMENT in page.url:
                    logger.error(
                        "Session expired — redirected to login. "
                        "Re-run `python src/login_once.py` to refresh."
                    )
                    return 1

                # Discover notebook item
                item_url = find_notebook(page, week_number, title_hints)
                if item_url is None:
                    logger.info("Notebook not yet available. Will retry next hour.")
                    return 0

                # Download .ipynb
                ipynb_path = download(ctx, item_url)

    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        return 1

    # Convert + summarize (no browser needed)
    try:
        py_path = convert(ipynb_path, week=week_number)
        md_path = analyze(ipynb_path, week=week_number, py_file=py_path)
    except Exception as e:
        logger.error(f"Convert/summarize error: {e}", exc_info=True)
        return 1

    # Mark complete
    mark_processed(week_number, ipynb_path, py_path, md_path)

    logger.info("=" * 50)
    logger.info(f"Week {week_number} done.")
    logger.info(f"  Notebook : {ipynb_path.name}")
    logger.info(f"  Script   : {py_path.name}")
    logger.info(f"  Summary  : {md_path.name}")
    logger.info("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(run())
