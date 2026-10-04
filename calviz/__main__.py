"""Entry point: `python -m calviz` (or the built CalendarVisualizer.exe).

`--selftest` parses the bundled example, renders it and round-trips it
through the Markdown writer without opening a window (used by CI).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path


def selftest() -> int:
    from .model import PLANNER_WEEK, Calendar
    from .parser import parse_file, parse_text
    from .render import export_week
    from .resources import AI_GUIDE, SAMPLE, SAMPLE_DATED
    from .writer import to_markdown

    assert AI_GUIDE.exists(), "AI guide not bundled"
    planner = parse_file(str(SAMPLE))
    dated = parse_file(str(SAMPLE_DATED))
    for result in (planner, dated):
        assert result.events and not result.warnings, result.warnings
    cal = Calendar(planner.title, planner.events)
    assert not cal.is_dated()
    out = Path(tempfile.gettempdir()) / "calviz_selftest.png"
    export_week(cal, PLANNER_WEEK, str(out), scale=2, show_dates=False)
    assert out.stat().st_size > 10_000
    cal.add(dated.events)
    assert cal.is_dated()
    again = parse_text(to_markdown(cal))
    assert set(again.events) == set(cal.events), "markdown round-trip mismatch"
    export_week(cal, cal.first_date(), str(out), scale=2)
    assert out.stat().st_size > 10_000
    out.unlink()
    from .ics import to_ics

    ics = to_ics(cal.events, cal.title)
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.count("BEGIN:VEVENT") == len(cal.events)
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        try:
            return selftest()
        except Exception as exc:  # report via exit code; a windowed exe has no console
            if sys.stderr:
                print(f"selftest failed: {exc!r}", file=sys.stderr)
            return 1
    from .gui import main as gui_main

    gui_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
