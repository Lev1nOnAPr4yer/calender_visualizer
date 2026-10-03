"""Write a calendar back out in the same human-readable syntax the parser reads."""

from __future__ import annotations

from itertools import groupby

from .model import Calendar, Event


def _escape(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ").strip()


def format_event(ev: Event, with_date: bool = False) -> str:
    parts = []
    if with_date:
        parts.append(ev.date.isoformat())
    parts.append("all day" if ev.all_day else f"{ev.start:%H:%M}-{ev.end:%H:%M}")
    parts.append(_escape(ev.title))
    line = "- " + " ".join(parts)
    if ev.location:
        line += f" | at: {_escape(ev.location)}"
    if ev.tag:
        line += f" | tag: {_escape(ev.tag)}"
    if ev.color:
        line += f" | color: {_escape(ev.color)}"
    if ev.repeat:
        line += f" | repeat: {ev.repeat.describe()}"
    for note in ev.notes.splitlines():
        if note.strip():
            line += f"\n  {note.strip()}"
    return line


def to_markdown(cal: Calendar) -> str:
    out = [f"# Calendar: {cal.title or 'My Calendar'}", ""]
    for day, events in groupby(cal.sorted_events(), key=lambda e: e.date):
        out.append(f"## {day:%A}, {day.isoformat()}")
        out.extend(format_event(e) for e in events)
        out.append("")
    return "\n".join(out).rstrip() + "\n"
