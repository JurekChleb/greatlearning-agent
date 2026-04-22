"""
Analyze a .ipynb notebook and generate a .md summary.

Usage:
    python src/analyzer.py <path/to/notebook.ipynb> [--week N] [--py-file path/to/output.py]
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import nbformat

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import SCRIPTS_DIR, SUMMARIES_DIR
from src.utils import slugify

_TODO_MARKERS = ("raise NotImplementedError", "# TODO", "# Your code here", "pass  #")
_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+([\w.]+)")
_PIP_MAGIC_RE = re.compile(r"^\s*!\s*pip\s+install\s+((?:[^\n]|\\\n)+)", re.MULTILINE)
_IMAGE_INLINE_RE = re.compile(r"!\[(.*?)\]\(data:image/[^)]+\)", re.DOTALL)
_IMAGE_ONLY_RE = re.compile(r"^\s*!\[.*?\]\(data:image/[^)]+\)\s*$", re.DOTALL)
_SLUG_MAX_LEN = 60

_STDLIB = {
    "os", "sys", "re", "json", "math", "time", "datetime", "pathlib",
    "collections", "itertools", "functools", "typing", "copy", "io",
    "string", "random", "hashlib", "logging", "unittest", "abc", "enum",
    "dataclasses", "contextlib", "warnings", "gc", "inspect", "textwrap",
    "pprint", "struct", "threading", "subprocess", "shutil", "tempfile",
    "urllib", "http", "email", "html", "xml", "csv", "sqlite3", "pickle",
    "base64", "binascii", "zlib", "gzip", "zipfile", "tarfile",
}


def _clean_markdown(src: str) -> str:
    """Replace inline base64 images with [image: alt_text] placeholders."""
    return _IMAGE_INLINE_RE.sub(
        lambda m: f"[image: {m.group(1) or 'figure'}]", src
    )


def _is_image_only(src: str) -> bool:
    return bool(_IMAGE_ONLY_RE.match(src))


def _extract_objectives(nb: nbformat.NotebookNode) -> tuple[str, str]:
    """Return (title, objectives_text).

    Strategy:
    - title: first non-image markdown cell's first non-empty heading
    - objectives: body of the 'Objective' section; if that cell has no body,
      the immediately following non-image markdown cell's text is used
    """
    # Collect clean text lines per markdown cell, skipping pure-image cells
    md_cells: list[list[str]] = []
    for cell in nb.cells:
        if cell.cell_type != "markdown":
            continue
        src = cell.source.strip()
        if not src or _is_image_only(src):
            continue
        clean = _clean_markdown(src)
        lines = [l for l in clean.splitlines() if l.strip()]
        if lines:
            md_cells.append(lines)

    if not md_cells:
        return "Notebook", ""

    title = md_cells[0][0].lstrip("#*").strip("* ").strip()

    # Search for objective section
    for i, lines in enumerate(md_cells):
        heading = lines[0].lstrip("#*").strip("* ").strip()
        body = "\n".join(lines[1:]).strip()
        if "objective" in heading.lower():
            if body:
                return title, body
            # body is in the next cell
            if i + 1 < len(md_cells):
                next_lines = md_cells[i + 1]
                next_heading = next_lines[0].lstrip("#*").strip("* ").strip()
                # use next cell only if it doesn't look like a new section heading
                if not re.match(r"^#+\s", md_cells[i + 1][0]) or len(next_lines) > 1:
                    return title, "\n".join(next_lines).strip()
            return title, heading  # fallback: at least return the word "Objective"

    # No 'Objective' cell found — fall back to second md cell content
    fallback = "\n".join(md_cells[1]).strip() if len(md_cells) > 1 else ""
    return title, fallback


def _cell_purpose(source: str) -> str:
    """Derive a one-line purpose from a code cell source."""
    lines = [l for l in source.splitlines() if l.strip() and not l.strip().startswith("#")]
    if not lines:
        return "Empty cell"
    first = lines[0].strip()
    if re.match(r"^(import|from)\s+", first):
        imports = []
        for line in lines[:6]:
            m = _IMPORT_RE.match(line)
            if m:
                imports.append(m.group(1).split(".")[0])
        return "Import " + ", ".join(dict.fromkeys(imports)) if imports else "Import libraries"
    if re.match(r"^def\s+", first):
        name = re.match(r"^def\s+(\w+)", first)
        return f"Define function `{name.group(1)}`" if name else "Define function"
    if re.match(r"^class\s+", first):
        name = re.match(r"^class\s+(\w+)", first)
        return f"Define class `{name.group(1)}`" if name else "Define class"
    if first.startswith(("!", "%")):
        return f"Shell/magic: {first[:70]}"
    return first[:80] + ("..." if len(first) > 80 else "")


def _is_todo(source: str) -> bool:
    return any(marker in source for marker in _TODO_MARKERS)


def _collect_requirements(nb: nbformat.NotebookNode) -> list[str]:
    """Collect third-party packages from imports and !pip install lines."""
    packages: dict[str, None] = {}
    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        src = cell.source
        for line in src.splitlines():
            m = _IMPORT_RE.match(line)
            if m:
                pkg = m.group(1).split(".")[0]
                if pkg not in _STDLIB:
                    packages[pkg] = None
        for match in _PIP_MAGIC_RE.finditer(src):
            for token in re.split(r"[\s\\,]+", match.group(1)):
                token = token.strip()
                if not token or token.startswith("-"):
                    continue
                # strip version specifiers and extras, e.g. langchain==0.3.9 -> langchain
                pkg = re.split(r"[=<>!\[]", token)[0].strip()
                if pkg and pkg not in _STDLIB:
                    packages[pkg] = None
    return list(packages.keys())


def _python_version(nb: nbformat.NotebookNode) -> str:
    ks = nb.metadata.get("kernelspec", {})
    lang = ks.get("language", "python")
    if lang != "python":
        return lang
    # try to get version from language_info
    li = nb.metadata.get("language_info", {})
    version = li.get("version", "")
    if version:
        parts = version.split(".")
        return ".".join(parts[:2])
    return "3.x"


def _md_cell_label(src: str) -> str:
    """One-line label for a markdown cell (images collapsed)."""
    clean = _clean_markdown(src)
    lines = [l.strip() for l in clean.splitlines() if l.strip()]
    return lines[0][:80] if lines else "(empty)"


def analyze(
    ipynb_path: Path,
    week: int | None = None,
    py_file: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    ipynb_path = Path(ipynb_path)
    output_dir = output_dir or SUMMARIES_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    nb = nbformat.read(ipynb_path, as_version=4)
    title, objectives = _extract_objectives(nb)
    py_version = _python_version(nb)
    requirements = _collect_requirements(nb)

    # Derive the expected .py output filename (mirrors converter.py naming)
    if py_file:
        py_filename = py_file.name
    else:
        slug = (slugify(title) or slugify(ipynb_path.stem))[:_SLUG_MAX_LEN]
        date_prefix = datetime.now().strftime("%Y-%m-%d")
        week_part = f"_week{week}" if week is not None else ""
        py_filename = f"{date_prefix}{week_part}_{slug}.py"

    rows: list[tuple[int, str, str, bool]] = []
    for cell_idx, cell in enumerate(nb.cells, start=1):
        src = cell.source.strip()
        if cell.cell_type == "markdown":
            label = _md_cell_label(src) if src else "(empty)"
            rows.append((cell_idx, "markdown", label, False))
        elif cell.cell_type == "code":
            purpose = _cell_purpose(src)
            todo = _is_todo(src)
            rows.append((cell_idx, "code", purpose, todo))

    todos = [(r[0], r[2]) for r in rows if r[3]]

    if requirements:
        install_line = "pip install " + " ".join(requirements)
    else:
        install_line = "# no third-party packages detected"

    out_lines = [
        f"# {title}",
        "",
        "## Overview",
        objectives if objectives else "_No objectives extracted from notebook._",
        "",
        "## Problem Description",
        f"This notebook covers **{title}**. "
        "Work through each cell in order; exercises marked TODO require your implementation.",
        "",
        "## Setup (VS Code)",
        "",
        f"- **Python:** {py_version}",
        f"- **Install:** `{install_line}`",
        f"- **Open:** `code data/scripts/py/{py_filename}`",
        "- **Run cells:** VS Code Python extension — click ▶ next to each `# %%` cell,",
        "  or use **Jupyter: Run Current Cell** (`Shift+Enter`).",
        "",
        "## Code Walkthrough",
        "",
        "| Cell | Type | Purpose |",
        "|------|------|---------|",
    ]

    for num, ctype, purpose, _ in rows:
        # Escape pipe characters so the markdown table stays valid
        out_lines.append(f"| {num} | {ctype} | {purpose.replace('|', '｜')} |")

    out_lines.append("")

    if todos:
        out_lines += ["## Exercises (TODOs)", ""]
        for cell_num, purpose in todos:
            out_lines.append(f"- **Cell {cell_num}:** {purpose}")
        out_lines.append("")

    out_lines += [
        "## Run Instructions",
        "",
        "1. Create and activate a virtual environment:",
        "   ```bash",
        f"   python{py_version} -m venv .venv && source .venv/bin/activate",
        "   ```",
        f"2. Install dependencies: `{install_line}`",
        f"3. Open the script: `code data/scripts/py/{py_filename}`",
        "4. VS Code detects `# %%` markers — run each cell with **Shift+Enter**.",
        "5. Fill in any TODO cells marked in the Exercises section above.",
    ]

    md_text = "\n".join(out_lines) + "\n"

    slug = (slugify(title) or slugify(ipynb_path.stem))[:_SLUG_MAX_LEN]
    date_prefix = datetime.now().strftime("%Y-%m-%d")
    week_part = f"_week{week}" if week is not None else ""
    out_name = f"{date_prefix}{week_part}_{slug}.md"
    out_path = output_dir / out_name

    out_path.write_text(md_text, encoding="utf-8")
    print(f"Summary:   {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate .md summary from .ipynb")
    parser.add_argument("notebook", type=Path)
    parser.add_argument("--week", type=int, default=None)
    parser.add_argument("--py-file", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    analyze(args.notebook, week=args.week, py_file=args.py_file, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
