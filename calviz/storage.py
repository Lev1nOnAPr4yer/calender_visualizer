"""Autosave the current calendar so it survives restarting the program."""

from __future__ import annotations

import os
from pathlib import Path

from .model import Calendar
from .parser import parse_file
from .writer import to_markdown


def data_dir() -> Path:
    root = os.environ.get("APPDATA") or os.path.join(Path.home(), ".config")
    path = Path(root) / "CalendarVisualizer"
    path.mkdir(parents=True, exist_ok=True)
    return path


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
    tmp = path.with_suffix(".tmp")
    tmp.write_text(to_markdown(cal), encoding="utf-8")
    os.replace(tmp, path)
