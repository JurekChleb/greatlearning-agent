"""
Download the .ipynb file for a given course item URL.

Flow:
  1. Navigate to the item page
  2. Find the nbviewer iframe
  3. Extract the "Download Notebook" signed CloudFront link from the iframe
  4. Download via the authenticated Playwright context
  5. Save to data/downloads/raw_ipynb/<filename>.ipynb
"""

import logging
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import BrowserContext, Page

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import LOGS_DIR, RAW_IPYNB_DIR

logger = logging.getLogger(__name__)

NAV_TIMEOUT  = 30_000
LOAD_TIMEOUT = 20_000


def _dump_debug(page: Page, label: str) -> None:
    from datetime import datetime
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        page.screenshot(path=str(LOGS_DIR / f"{ts}_{label}.png"), full_page=True)
        (LOGS_DIR / f"{ts}_{label}.html").write_text(page.content(), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Debug dump failed: {e}")


def _find_download_url(page: Page) -> str:
    """Extract the signed 'Download Notebook' URL from the nbviewer iframe."""
    # Wait for the nbviewer iframe to appear
    page.wait_for_selector("iframe", timeout=NAV_TIMEOUT)

    nbviewer_frame = next(
        (f for f in page.frames if "nbviewer" in f.url),
        None,
    )
    if nbviewer_frame is None:
        _dump_debug(page, "no_nbviewer_iframe")
        raise RuntimeError("nbviewer iframe not found on item page")

    # Wait for the Download Notebook link to be present in the DOM (it's hidden, hence "attached")
    try:
        nbviewer_frame.wait_for_selector(
            "a[title='Download Notebook'], a[download]",
            state="attached",
            timeout=NAV_TIMEOUT,
        )
    except Exception:
        _dump_debug(page, "no_download_link")
        raise RuntimeError("'Download Notebook' link not found in nbviewer iframe")

    html = nbviewer_frame.content()
    soup = BeautifulSoup(html, "html.parser")
    dl_anchor = (
        soup.find("a", title="Download Notebook")
        or soup.find("a", string="Download Notebook")
        or next((a for a in soup.find_all("a") if a.get("download") is not None and a.get("href","").endswith(".ipynb")), None)
    )
    if dl_anchor is None:
        raise RuntimeError("'Download Notebook' anchor not found after waiting")

    return dl_anchor["href"]


def download(context: BrowserContext, item_url: str) -> Path:
    """
    Navigate to item_url, find the notebook download link, save the file.

    Returns the Path of the saved .ipynb file.
    """
    RAW_IPYNB_DIR.mkdir(parents=True, exist_ok=True)

    page = context.new_page()
    logger.info(f"Opening item page: {item_url}")
    try:
        page.goto(item_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        page.wait_for_load_state("networkidle", timeout=LOAD_TIMEOUT)
    except Exception as e:
        _dump_debug(page, "item_nav_failed")
        page.close()
        raise RuntimeError(f"Failed to load item page: {e}") from e

    try:
        download_url = _find_download_url(page)
    except Exception:
        page.close()
        raise

    filename = unquote(urlparse(download_url).path.split("/")[-1])
    if not filename.endswith(".ipynb"):
        filename += ".ipynb"

    logger.info(f"Downloading: {filename}")
    response = context.request.get(download_url)
    if not response.ok:
        page.close()
        raise RuntimeError(f"Download failed: HTTP {response.status} for {download_url[:80]}")

    out_path = RAW_IPYNB_DIR / filename
    out_path.write_bytes(response.body())
    logger.info(f"Saved: {out_path} ({len(response.body()):,} bytes)")

    page.close()
    return out_path
