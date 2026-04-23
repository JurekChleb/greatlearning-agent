"""
Discover the notebook item URL for the current week on the course page.

Strategy (in priority order):
1. Find the MLS section for the target week (heading contains "Week N" and "MLS")
2. Within that section, find items whose title contains "notebook" or "ipynb"
3. Rank by title_hints from schedule.yaml
4. Exclude quiz/assessment/session plan/video items
5. Return the item URL of the best match, or None if not found yet
"""

import logging
import re
import sys
from pathlib import Path

from playwright.sync_api import Page

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import LOGS_DIR

logger = logging.getLogger(__name__)

_NOTEBOOK_TERMS = ["notebook", "ipynb", "mls notebook"]
_EXCLUDE_TERMS  = ["quiz", "assessment", "session plan", "faq", "video", "live session", "graded"]
_MLS_TERMS      = ["mls", "machine learning"]

BASE_URL = "https://olympus.mygreatlearning.com"


def _score(title: str, hints: list[str]) -> int:
    t = title.lower()
    score = 0
    if any(nb in t for nb in _NOTEBOOK_TERMS):
        score += 10
    if any(ex in t for ex in _EXCLUDE_TERMS):
        score -= 20
    for hint in hints:
        if hint.lower() in t:
            score += 5
    return score


def find_notebook(page: Page, week_number: int, title_hints: list[str]) -> str | None:
    """
    Scan the course page for the notebook item belonging to the given week.

    Returns the full item URL (e.g. https://olympus.../courses/.../modules/items/...)
    or None if no suitable item is found (not yet released / wrong week).
    """
    logger.info(f"Discovering notebook for week {week_number}, hints={title_hints}")

    # Wait until the full module list is rendered. The spinner page has ~1 font_subtitleDesktop
    # span; a fully loaded course page has 20+. Threshold of 8 safely clears the spinner.
    try:
        page.wait_for_function(
            "() => document.querySelectorAll('span.font_subtitleDesktop').length >= 8",
            timeout=45_000,
        )
    except Exception:
        count = page.evaluate("() => document.querySelectorAll('span.font_subtitleDesktop').length")
        logger.warning(f"Timed out waiting for course content (only {count} section spans present)")
        _dump_candidates(page, week_number, [])
        return None

    count = page.evaluate("() => document.querySelectorAll('span.font_subtitleDesktop').length")
    logger.info(f"Course page loaded ({count} section spans)")

    # Collect all module section headings and their contained item links.
    # Structure on the page:
    #   <span class="font_subtitleDesktop ...">Week N : ... - MLS</span>   ← section header
    #   <a href="/courses/.../modules/items/...">                           ← item link
    #     <span class="font_bodyDesktop ...">Week N : MLS Notebook - ...</span>

    week_pattern = re.compile(rf"\bweek\s*{week_number}\b", re.IGNORECASE)

    # Get all section heading elements
    section_spans = page.locator("span.font_subtitleDesktop").all()

    # Find the MLS section index for this week
    mls_section_idx = None
    for i, span in enumerate(section_spans):
        try:
            text = span.inner_text(timeout=2000)
        except Exception:
            continue
        if week_pattern.search(text) and any(m in text.lower() for m in _MLS_TERMS):
            mls_section_idx = i
            logger.info(f"Found MLS section: {text!r}")
            break

    if mls_section_idx is None:
        logger.warning(f"No MLS section found for week {week_number} — not yet released?")
        _dump_candidates(page, week_number, [])
        return None

    # Scroll the MLS section into view to trigger lazy-loaded items, then wait briefly
    try:
        section_spans[mls_section_idx].scroll_into_view_if_needed(timeout=5000)
        page.wait_for_timeout(2000)
    except Exception:
        pass

    # Collect item links that belong to this MLS section using DOM order:
    # items must appear after the MLS heading and before the next section heading.
    # Week N items may not carry "Week N" in their title (e.g. "Notebook : Prompt Engineering"),
    # so title-based week filtering is unreliable — DOM position is the right scope.
    raw_items: list[dict] = page.evaluate(f"""() => {{
        const FOLLOWING = 4;  // Node.DOCUMENT_POSITION_FOLLOWING
        const PRECEDING  = 2;  // Node.DOCUMENT_POSITION_PRECEDING
        const spans = Array.from(document.querySelectorAll('span.font_subtitleDesktop'));
        const mlsIdx = {mls_section_idx};
        const mlsSpan = spans[mlsIdx];
        // Skip sub-section labels ("Slides", "Notebooks", "Dataset" etc.) and
        // use only the next top-level heading as the boundary.
        const topLevel = /week\\s*\\d|learning|mandatory|recordings|groups|notes/i;
        let nextTopSpan = null;
        for (let i = mlsIdx + 1; i < spans.length; i++) {{
            if (topLevel.test(spans[i].textContent)) {{
                nextTopSpan = spans[i];
                break;
            }}
        }}
        return Array.from(document.querySelectorAll('a[href*="/modules/items/"]'))
            .filter(a => {{
                const afterMls   = mlsSpan.compareDocumentPosition(a) & FOLLOWING;
                const beforeNext = !nextTopSpan || (nextTopSpan.compareDocumentPosition(a) & PRECEDING);
                return afterMls && beforeNext;
            }})
            .map(a => ({{
                href: a.getAttribute('href'),
                text: a.textContent.trim().replace(/\\s+/g, ' ')
            }}));
    }}""")

    candidates: list[tuple[int, str, str]] = []  # (score, title, href)
    for item in raw_items:
        href  = item.get("href", "")
        title = item.get("text", "").strip()
        if not href or not title:
            continue
        score = _score(title, title_hints)
        candidates.append((score, title, href))
        logger.debug(f"  Candidate score={score}: {title!r}")

    if not candidates:
        logger.warning(f"No item candidates found for week {week_number}")
        _dump_candidates(page, week_number, [])
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_title, best_href = candidates[0]

    if best_score < 0:
        logger.warning(f"Best candidate has negative score ({best_score}): {best_title!r} — skipping")
        _dump_candidates(page, week_number, candidates)
        return None

    full_url = BASE_URL + best_href if best_href.startswith("/") else best_href
    logger.info(f"Selected: {best_title!r} (score={best_score}) → {full_url}")
    return full_url


def _dump_candidates(page: Page, week_number: int, candidates: list) -> None:
    from datetime import datetime
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        page.screenshot(path=str(LOGS_DIR / f"{ts}_discovery_week{week_number}.png"), full_page=True)
    except Exception:
        pass
    if candidates:
        log_path = LOGS_DIR / f"{ts}_discovery_week{week_number}_candidates.txt"
        log_path.write_text(
            "\n".join(f"{s:+d}  {t!r}  {h}" for s, t, h in candidates),
            encoding="utf-8",
        )
