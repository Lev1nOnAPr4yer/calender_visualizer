"""Write a calendar back out in the same human-readable syntax the parser reads."""

from __future__ import annotations

import re
from itertools import groupby

from .model import WEEKDAYS, Calendar, Event, fmt_date
from .parser import _KEY_ALIASES

# A comma followed by something that reads like "tag:" would start a field; escape it.
_FIELD_LIKE_COMMA = re.compile(rf",(?=\s*(?:{'|'.join(_KEY_ALIASES)})\s*:)", re.I)


def _escape(s: str) -> str:
    s = s.replace("|", "\\|").replace("\n", " ").strip()
    return _FIELD_LIKE_COMMA.sub("\\\\,", s)


def format_event(ev: Event, with_date: bool = False) -> str:
    parts = []
    if with_date:
        parts.append(fmt_date(ev.date) if ev.dated else WEEKDAYS[ev.weekday])
    parts.append("all day" if ev.all_day else f"{ev.start:%H:%M}-{ev.end:%H:%M}")
    parts.append(_escape(ev.title))
    line = "- " + " ".join(parts)
    if ev.location:
        line += f", at: {_escape(ev.location)}"
    if ev.tag:
        line += f", tag: {_escape(ev.tag)}"
    if ev.color:
        line += f", color: {_escape(ev.color)}"
    if ev.repeat:
        line += f", repeat: {ev.repeat.describe()}"
    for note in ev.notes.splitlines():
        if note.strip():
            line += f"\n  {note.strip()}"
    return line


def to_markdown(cal: Calendar) -> str:
    out = [f"# Calendar: {cal.title or 'My Calendar'}", ""]
    # Weekly-planner entries (no date) first: they appear in every week.
    for wd, events in groupby(cal.undated_events(), key=lambda e: e.weekday):
        out.append(f"## {WEEKDAYS[wd]}")
        out.extend(format_event(e) for e in events)
        out.append("")
    for day, events in groupby(cal.dated_events(), key=lambda e: e.date):
        out.append(f"## {WEEKDAYS[day.weekday()]}, {fmt_date(day)}")
        out.extend(format_event(e) for e in events)
        out.append("")
    return "\n".join(out).rstrip() + "\n"
