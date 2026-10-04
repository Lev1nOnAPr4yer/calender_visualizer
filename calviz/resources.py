"""Locate bundled files both when running from source and inside the PyInstaller exe."""

from __future__ import annotations

import sys
from pathlib import Path


def base_dir() -> Path:
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        return Path(frozen)
    return Path(__file__).resolve().parent.parent


def resource(*parts: str) -> Path:
    return base_dir().joinpath(*parts)


FONT_REGULAR = resource("calviz", "assets", "DejaVuSans.ttf")
FONT_BOLD = resource("calviz", "assets", "DejaVuSans-Bold.ttf")
AI_GUIDE = resource("AI_SYNTAX_GUIDE.md")
SAMPLE = resource("examples", "sample.md")
SAMPLE_DATED = resource("examples", "sample-dated.md")
ICON_PNG = resource("calviz", "assets", "icon.png")
