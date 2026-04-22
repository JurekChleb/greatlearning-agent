"""
Convert a .ipynb notebook to a .py script (Jupytext percent format).

Usage:
    python src/converter.py <path/to/notebook.ipynb> [--week N] [--url URL]
"""

import argparse
import copy
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import jupytext
import nbformat

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import SCRIPTS_DIR
from src.utils import slugify

_MAGIC_PREFIXES = ("%", "!")
_IMAGE_INLINE_RE = re.compile(r"!\[(.*?)\]\(data:image/[^)]+\)", re.DOTALL)
_IMAGE_ONLY_RE = re.compile(r"^\s*!\[.*?\]\(data:image/[^)]+\)\s*$", re.DOTALL)


def _extract_title(nb: nbformat.NotebookNode) -> str:
    for cell in nb.cells:
        if cell.cell_type != "markdown":
            continue
        src = cell.source.strip()
        if not src or _IMAGE_ONLY_RE.match(src):
            continue
        for line in src.splitlines():
            line = line.strip()
            if line and not _IMAGE_ONLY_RE.match(line):
                return line.lstrip("#*").strip("* ").strip()
    return ""


def _strip_images(nb: nbformat.NotebookNode) -> nbformat.NotebookNode:
    """Return a copy of nb with embedded base64 images replaced by alt-text placeholders."""
    nb = copy.deepcopy(nb)
    for cell in nb.cells:
        if cell.cell_type == "markdown":
            cell.source = _IMAGE_INLINE_RE.sub(
                lambda m: f"[image: {m.group(1) or 'figure'}]", cell.source
            )
    return nb


def _build_header(title: str, week: int | None, url: str | None, timestamp: str) -> str:
    lines = [
        "# " + "=" * 70,
        f"# Source:    {title}",
    ]
    if week is not None:
        lines.append(f"# Week:      {week}")
    if url:
        lines.append(f"# URL:       {url}")
    lines.append(f"# Downloaded:{timestamp}")
    lines.append("# " + "=" * 70)
    return "\n".join(lines)


_JUPYTEXT_FRONT_MATTER_RE = re.compile(
    r"^(#\s*---\s*\n(?:#[^\n]*\n)*#\s*---\s*\n)", re.MULTILINE
)
# Any Jupytext cell marker line (# %% or # %% [markdown] with optional metadata)
_CELL_MARKER_RE = re.compile(r"^# %%.*$")
# Magic lines as bare code OR jupytext-commented (# ! ..., # % ...)
_MAGIC_LINE_RE = re.compile(r"^\s*(?:#\s*)?[!%]\s")


def _post_process(py_text: str) -> str:
    # Strip Jupytext YAML front-matter block
    py_text = _JUPYTEXT_FRONT_MATTER_RE.sub("", py_text, count=1)
    out = []
    in_magic_continuation = False
    for line in py_text.splitlines():
        # Drop all cell markers (# %% ...)
        if _CELL_MARKER_RE.match(line):
            in_magic_continuation = False
            continue
        # Drop magic lines and their backslash continuations
        if _MAGIC_LINE_RE.match(line):
            in_magic_continuation = line.rstrip().endswith("\\")
            continue
        if in_magic_continuation:
            in_magic_continuation = line.rstrip().endswith("\\")
            continue
        out.append(line)
    # Collapse runs of 3+ blank lines down to 2
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    return result


def _convert_jupytext(nb: nbformat.NotebookNode) -> str:
    return jupytext.writes(nb, fmt="py:percent")


def _convert_nbconvert(ipynb_path: Path) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            ["jupyter", "nbconvert", "--to", "script", str(ipynb_path), "--output-dir", tmpdir],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"nbconvert failed: {result.stderr}")
        out_file = Path(tmpdir) / (ipynb_path.stem + ".py")
        return out_file.read_text(encoding="utf-8")


def convert(
    ipynb_path: Path,
    week: int | None = None,
    url: str | None = None,
    output_dir: Path | None = None,
) -> Path:
    ipynb_path = Path(ipynb_path)
    output_dir = output_dir or SCRIPTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    nb = nbformat.read(ipynb_path, as_version=4)
    title = _extract_title(nb) or nb.metadata.get("title") or ipynb_path.stem
    nb_clean = _strip_images(nb)

    try:
        py_text = _convert_jupytext(nb_clean)
    except Exception:
        py_text = _convert_nbconvert(ipynb_path)

    py_body = _post_process(py_text)

    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    header = _build_header(title, week, url, timestamp)
    full_text = header + "\n\n" + py_body

    slug = (slugify(title) or slugify(ipynb_path.stem))[:60]
    date_prefix = datetime.now().strftime("%Y-%m-%d")
    week_part = f"_week{week}" if week is not None else ""
    out_name = f"{date_prefix}{week_part}_{slug}.py"
    out_path = output_dir / out_name

    out_path.write_text(full_text, encoding="utf-8")
    print(f"Converted: {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert .ipynb to .py (Jupytext percent format)")
    parser.add_argument("notebook", type=Path, help="Path to .ipynb file")
    parser.add_argument("--week", type=int, default=None)
    parser.add_argument("--url", type=str, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    convert(args.notebook, week=args.week, url=args.url, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
