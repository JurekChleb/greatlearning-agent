import os
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

COURSE_URL: str = os.environ.get("COURSE_URL", "https://olympus.mygreatlearning.com")

with open(PROJECT_ROOT / "config" / "schedule.yaml") as f:
    SCHEDULE = yaml.safe_load(f)

WARSAW = ZoneInfo(SCHEDULE["program_timezone"])

DATA_DIR = PROJECT_ROOT / "data"
AUTH_DIR = DATA_DIR / "auth"
RAW_IPYNB_DIR = DATA_DIR / "downloads" / "raw_ipynb"
SCRIPTS_DIR = DATA_DIR / "scripts" / "py"
SUMMARIES_DIR = DATA_DIR / "summaries"
LOGS_DIR = DATA_DIR / "logs"
STATE_DIR = DATA_DIR / "state"
PROCESSED_JSON = STATE_DIR / "processed.json"
STORAGE_STATE = AUTH_DIR / "storage_state.json"

WEEKS: list[dict] = SCHEDULE["weeks"]


def get_week(release_date: str) -> dict | None:
    for week in WEEKS:
        if str(week["release_date"]) == release_date:
            return week
    return None
