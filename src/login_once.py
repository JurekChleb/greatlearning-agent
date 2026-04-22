"""
One-time manual login to Great Learning.

Opens a visible browser window pointed at the login page. Log in
manually (handles MFA / captcha), then navigate to your course page.
When you're there, come back to this terminal and press Enter.
The session is saved to data/auth/storage_state.json.

Usage:
    python src/login_once.py
"""

import logging
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import AUTH_DIR, STORAGE_STATE

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
logger = logging.getLogger(__name__)

LOGIN_URL = "https://olympus.mygreatlearning.com/login"


def login_once() -> None:
    AUTH_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        logger.info(f"Opening login page: {LOGIN_URL}")
        page.goto(LOGIN_URL, wait_until="domcontentloaded")

        print()
        print("=" * 60)
        print("  Browser is open at the Great Learning login page.")
        print()
        print("  1. Log in with your credentials.")
        print("  2. Navigate to your course page.")
        print("  3. This script will save the session automatically")
        print("     once you leave the login page.")
        print("  (Waiting up to 5 minutes...)")
        print("=" * 60)
        print()

        # Wait until the URL is no longer the login page — no stdin needed
        page.wait_for_url(
            lambda url: "login" not in url and "sign" not in url,
            timeout=5 * 60 * 1000,
        )
        page.wait_for_load_state("networkidle", timeout=15_000)
        current_url = page.url
        logger.info(f"Saving session from: {current_url}")

        context.storage_state(path=str(STORAGE_STATE))
        logger.info(f"Session saved → {STORAGE_STATE}")
        print()
        print("  Done! You can close the browser window.")

        browser.close()


if __name__ == "__main__":
    login_once()
