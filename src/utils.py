import re
from pathlib import Path


def slugify(title: str) -> str:
    title = title.lower()
    title = re.sub(r"[^\w\s-]", "", title)
    title = re.sub(r"[\s_]+", "-", title)
    title = re.sub(r"-+", "-", title)
    return title.strip("-")


def find_notebooks(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.ipynb"))
