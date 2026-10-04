"""Export entries as an iCalendar (.ics) file for Thunderbird, Outlook, Google Calendar, ...

Weekly (undated) entries become events that repeat every week from a chosen
start date. Times are written as "floating" local times (no time zone), so
calendar apps show them at exactly the clock time that was typed.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable

from .model import Event

_ICAL_DAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
_FREQ = {"daily": "DAILY", "weekly": "WEEKLY", "monthly": "MONTHLY", "yearly": "YEARLY"}


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
        .replace("\r\n", "\\n").replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Split a content line into chunks of at most 75 octets (RFC 5545 §3.1)."""
    out: list[str] = []
    current = ""
    limit = 75
    for ch in line:
        if len((current + ch).encode("utf-8")) > limit:
            out.append(current)
            current = " " + ch  # continuation lines start with a space
            limit = 75
        else:
            current += ch
    out.append(current)
    return "\r\n".join(out)


def _dt(d: date, t: time) -> str:
    return f"{d:%Y%m%d}T{t:%H%M%S}"


def _uid(ev: Event) -> str:
    key = "|".join(
        str(x) for x in (ev.title, ev.date, ev.weekday, ev.start, ev.end, ev.location, ev.tag, ev.repeat)
    )
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:20] + "@calendar-visualizer"


def first_weekly_date(weekday: int, start: date) -> date:
    """First date on or after `start` that falls on `weekday` (0 = Monday)."""
    return start + timedelta(days=(weekday - start.weekday()) % 7)


def _until(d: date, all_day: bool) -> str:
    return f"{d:%Y%m%d}" if all_day else f"{d:%Y%m%d}T235959"


def _event_lines(ev: Event, weekly_start: date, weekly_until: date | None, stamp: str) -> list[str]:
    day = ev.date if ev.dated else first_weekly_date(ev.weekday, weekly_start)
    lines = ["BEGIN:VEVENT", f"UID:{_uid(ev)}", f"DTSTAMP:{stamp}"]
    if ev.all_day:
        lines.append(f"DTSTART;VALUE=DATE:{day:%Y%m%d}")
        lines.append(f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}")
    else:
        end_day = day + timedelta(days=1) if ev.crosses_midnight else day
        lines.append(f"DTSTART:{_dt(day, ev.start)}")
        lines.append(f"DTEND:{_dt(end_day, ev.end)}")

    if not ev.dated:
        rule = f"RRULE:FREQ=WEEKLY;BYDAY={_ICAL_DAYS[ev.weekday]}"
        if weekly_until:
            rule += f";UNTIL={_until(weekly_until, ev.all_day)}"
        lines.append(rule)
    elif ev.repeat:
        r = ev.repeat
        rule = f"RRULE:FREQ={_FREQ[r.freq]}"
        if r.interval != 1:
            rule += f";INTERVAL={r.interval}"
        if r.until:
            rule += f";UNTIL={_until(r.until, ev.all_day)}"
        elif r.count:
            rule += f";COUNT={r.count}"
        lines.append(rule)

    lines.append(f"SUMMARY:{_escape(ev.title)}")
    if ev.location:
        lines.append(f"LOCATION:{_escape(ev.location)}")
    if ev.notes:
        lines.append(f"DESCRIPTION:{_escape(ev.notes)}")
    if ev.tag:
        lines.append(f"CATEGORIES:{_escape(ev.tag)}")
    lines.append("END:VEVENT")
    return lines


def to_ics(
    events: Iterable[Event],
    title: str = "",
    weekly_start: date | None = None,
    weekly_until: date | None = None,
) -> str:
    """Build the .ics text. Weekly entries repeat from `weekly_start` (default: this week's Monday)."""
    if weekly_start is None:
        today = date.today()
        weekly_start = today - timedelta(days=today.weekday())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Calendar Visualizer//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    if title:
        lines.append(f"X-WR-CALNAME:{_escape(title)}")
    for ev in events:
        lines.extend(_event_lines(ev, weekly_start, weekly_until, stamp))
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
