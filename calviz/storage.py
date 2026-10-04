"""Autosave the current calendar so it survives restarting the program."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .model import Calendar
from .parser import parse_file
from .writer import to_markdown


def data_dir() -> Path:
    """The program's only folder on disk. It is created on the first save, never just by starting."""
    root = os.environ.get("APPDATA") or os.path.join(Path.home(), ".config")
    return Path(root) / "CalendarVisualizer"


def autosave_path() -> Path:
    return data_dir() / "calendar.md"


def load() -> Calendar:
    path = autosave_path()
    if not path.exists():
        return Calendar()
    result = parse_file(str(path))
    return Calendar(title=result.title, events=result.events)


def save(cal: Calendar) -> None:
    path = autosave_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(to_markdown(cal), encoding="utf-8")
    os.replace(tmp, path)


def remove_all_data() -> None:
    """Delete everything the program ever stored (the autosave folder)."""
    shutil.rmtree(data_dir(), ignore_errors=True)
