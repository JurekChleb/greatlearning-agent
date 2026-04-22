# Great Learning Agent

Automates downloading weekly Jupyter notebooks from a Great Learning course, converting them to clean `.py` scripts, and generating `.md` summaries. Run it manually any time — it detects and processes any Thursday release that has not been handled yet.

---

## What it does

1. Reads `config/schedule.yaml` to find the most recent unprocessed Thursday release.
2. Opens a real (non-headless) Chromium browser using your saved session.
3. Navigates to your course page, locates the notebook for that week, and downloads it.
4. Converts the `.ipynb` to a clean Python script (no cell markers, no magic commands).
5. Generates a Markdown summary with an overview, per-cell walkthrough, and TODO exercises.
6. Records the week as processed so it is never downloaded again.

---

## Directory layout

```
greatlearning-agent/
  config/
    schedule.yaml          # course release schedule — edit to match your program
  data/
    auth/                  # Playwright session (gitignored — created by login_once.py)
    downloads/raw_ipynb/   # raw .ipynb files downloaded from the course
    scripts/py/            # converted .py scripts  ← OUTPUT
    summaries/             # generated .md summaries ← OUTPUT
    logs/                  # debug screenshots and HTML dumps
    state/
      processed.json       # tracks which weeks have been processed
  src/
    run_release_check.py   # main entry point
    login_once.py          # one-time login to save a browser session
    config.py
    auth.py
    discovery.py
    downloader.py
    converter.py
    analyzer.py
    state_manager.py
    utils.py
```

**Output files** land in:

| Type | Path | Naming convention |
|------|------|-------------------|
| Raw notebook | `data/downloads/raw_ipynb/` | original filename from course |
| Python script | `data/scripts/py/` | `YYYY-MM-DD_week<N>_<topic-slug>.py` |
| MD summary | `data/summaries/` | `YYYY-MM-DD_week<N>_<topic-slug>.md` |

---

## Prerequisites

- Python 3.12
- A Great Learning account with access to the course
- macOS (tested) or Linux

---

## Setup

### 1 — Clone and create a virtual environment

```bash
git clone https://github.com/YOUR_USERNAME/greatlearning-agent.git
cd greatlearning-agent
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2 — Create `.env`

Create a file named `.env` in the project root:

```
COURSE_URL=https://olympus.mygreatlearning.com/courses/XXXXX?th=YYYY&pb_id=ZZZZ
```

**How to find your URL:**
1. Log into [olympus.mygreatlearning.com](https://olympus.mygreatlearning.com).
2. Open your course (e.g. "Certificate Program in Agentic AI").
3. Copy the full URL from the browser address bar. It looks like:
   ```
   https://olympus.mygreatlearning.com/courses/148723?th=dpep&pb_id=20415
   ```
   Paste that exact URL as the value of `COURSE_URL`.

### 3 — Update `config/schedule.yaml`

The file ships with the April 2026 Agentic AI cohort schedule. If your cohort has different dates, edit the `release_date` fields (format: `YYYY-MM-DD`) to match your Thursdays. Mark break weeks with `break: true` and project weeks that share a date with a content week with `skip: true`.

### 4 — Log in once

```bash
source .venv/bin/activate
python src/login_once.py
```

A browser window opens. Log in with your Great Learning credentials. Once redirected away from the login page the session is saved automatically to `data/auth/storage_state.json`. You will not need to do this again unless the session expires (typically after a few weeks).

---

## Running

```bash
source .venv/bin/activate
python src/run_release_check.py
```

Run this any day. The script finds the most recent Thursday release that has not been processed yet, downloads it, and writes the outputs. If everything is up to date it exits immediately with a log message.

### Session expired?

If you see `Session expired — redirected to login`, re-run the login step:

```bash
python src/login_once.py
```

---

## Output examples

**Python script** (`data/scripts/py/2026-04-22_week2_prompt-engineering-fundamentals.py`):
- Plain `.py` with no `# %%` cell markers, no `%`/`!` magic lines
- Header block with source title, week number, and download timestamp
- TODO exercises preserved verbatim

**Markdown summary** (`data/summaries/2026-04-22_week2_prompt-engineering-fundamentals.md`):
- Overview and learning objectives
- Per-cell walkthrough table
- List of TODO exercises with line references
- Required pip packages
- VS Code run instructions

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Browser opens and immediately closes | Session file is missing — run `python src/login_once.py` |
| `No release scheduled for today` | No unprocessed Thursday found — check `data/state/processed.json` and `config/schedule.yaml` |
| Notebook not found on course page | Content may not be released yet; re-run after the Thursday release time |
| `403` or page blocked | The script uses a real (non-headless) browser with a genuine user-agent — this should not happen normally |
