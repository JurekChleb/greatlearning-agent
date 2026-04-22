"""
Read/write processed.json to track which weeks have been completed.

Schema:
{
  "2": {
    "processed_at": "2026-04-16T14:23:00+02:00",
    "notebook": "JHU_AgenticAI_MLS2_Prompt_Engineering_Fundamentals_HF.ipynb",
    "py_file": "2026-04-16_week2_prompt-engineering-fundamentals.py",
    "summary": "2026-04-16_week2_prompt-engineering-fundamentals.md"
  }
}

Week numbers are stored as strings (JSON keys must be strings).
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import PROCESSED_JSON, WARSAW

logger = logging.getLogger(__name__)


def _load() -> dict:
    if PROCESSED_JSON.exists():
        return json.loads(PROCESSED_JSON.read_text(encoding="utf-8"))
    return {}


def _save(data: dict) -> None:
    PROCESSED_JSON.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def is_processed(week_number: int) -> bool:
    return str(week_number) in _load()


def mark_processed(week_number: int, notebook: Path, py_file: Path, summary: Path) -> None:
    data = _load()
    data[str(week_number)] = {
        "processed_at": datetime.now(tz=WARSAW).isoformat(),
        "notebook": notebook.name,
        "py_file": py_file.name,
        "summary": summary.name,
    }
    _save(data)
    logger.info(f"Week {week_number} marked as processed.")


def get_all() -> dict:
    return _load()
