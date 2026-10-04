"""Parse the human-readable event syntax (see AI_SYNTAX_GUIDE.md) into events.

The parser is forgiving: anything it cannot understand is skipped and
reported as a warning instead of raising an error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, time

from .model import FREQUENCIES, WEEKDAYS, Event, Repeat


@dataclass
class ParseResult:
    events: list[Event] = field(default_factory=list)
    title: str = ""
    warnings: list[str] = field(default_factory=list)


# --- low level token patterns ------------------------------------------------

_DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)|(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)")
_TIME_PAT = r"\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)|\d{1,2}:\d{2}"
_TIME_RE = re.compile(rf"^(?:{_TIME_PAT})$", re.I)
_RANGE_RE = re.compile(
    rf"^(?P<start>{_TIME_PAT})(?:\s*(?:-|–|—|to|bis)\s*(?P<end>{_TIME_PAT}))?(?=\s|$)",
    re.I,
)
_DURATION_RE = re.compile(r"^\(\s*(?P<dur>[^)]*)\)\s*")
_ALL_DAY_RE = re.compile(r"^(?:all[\s-]?day|ganztägig|ganztags)\b[:\s]*", re.I)
_BULLET_RE = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+(?:\[[ xX]\]\s+)?")
_HEADING_RE = re.compile(r"^\s*(#{1,6})\s*(.*?)\s*#*\s*$")
_FIELD_SPLIT_RE = re.compile(r"(?<!\\)\|")
_DATE_LINE_RE = re.compile(rf"(?:[A-Za-zÄÖÜäöü]+[,:]?\s+)*(?:{_DATE_RE.pattern})\s*:?")

_WEEKDAY_NAMES = {
    0: ("monday", "mon", "montag"),
    1: ("tuesday", "tue", "tues", "dienstag"),
    2: ("wednesday", "wed", "mittwoch"),
    3: ("thursday", "thu", "thur", "thurs", "donnerstag"),
    4: ("friday", "fri", "freitag"),
    5: ("saturday", "sat", "samstag", "sonnabend"),
    6: ("sunday", "sun", "sonntag"),
}
_WEEKDAY_LOOKUP = {name: wd for wd, names in _WEEKDAY_NAMES.items() for name in names}
_WEEKDAY_PAT = "|".join(sorted(_WEEKDAY_LOOKUP, key=len, reverse=True))
# "Monday", "Mondays", "every Monday", "jeden Montag", "Mon." (whole text)
_WEEKDAY_ONLY_RE = re.compile(rf"(?:(?:every|each|jeden|jeder)\s+)?(?P<wd>{_WEEKDAY_PAT})s?\.?\s*:?", re.I)
# Leading weekday on an event line; only counts when a time or "all day" follows.
_WEEKDAY_LEAD_RE = re.compile(rf"^(?:(?:every|each|jeden|jeder)\s+)?(?P<wd>{_WEEKDAY_PAT})s?\.?\s*[,:]?\s+(?=\d|all[\s-]?day|ganzt)", re.I)
_WEEKDAY_WORD_RE = re.compile(rf"\b(?P<wd>{_WEEKDAY_PAT})\b", re.I)

_KEY_ALIASES = {
    "at": "location", "location": "location", "where": "location", "place": "location", "ort": "location",
    "tag": "tag", "tags": "tag", "category": "tag", "type": "tag",
    "color": "color", "colour": "color", "farbe": "color",
    "repeat": "repeat", "repeats": "repeat", "every": "repeat", "recurring": "repeat",
    "note": "notes", "notes": "notes", "description": "notes",
}


def parse_date(text: str) -> date | None:
    m = _DATE_RE.search(text)
    if not m:
        return None
    try:
        if m.group(1):
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return date(int(m.group(6)), int(m.group(5)), int(m.group(4)))
    except ValueError:
        return None


def parse_weekday(text: str) -> int | None:
    """'Monday', 'every Monday', 'Mo...' style text -> 0..6, else None."""
    m = _WEEKDAY_ONLY_RE.fullmatch(text.strip())
    return _WEEKDAY_LOOKUP[m.group("wd").lower()] if m else None


def parse_time(text: str) -> time | None:
    text = text.strip().lower().replace(".", "").replace(" ", "")
    if not _TIME_RE.match(text) and not re.match(r"^\d{1,2}(:\d{2})?(am|pm)$", text):
        return None
    suffix = ""
    if text.endswith(("am", "pm")):
        text, suffix = text[:-2], text[-2:]
    hh, _, mm = text.partition(":")
    h, m = int(hh), int(mm or 0)
    if suffix:
        if not 1 <= h <= 12:
            return None
        h = h % 12 + (12 if suffix == "pm" else 0)
    if h == 24 and m == 0:
        h = 0
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return time(h, m)


def parse_duration(text: str) -> int | None:
    """'45m', '1h', '1h30m', '1.5h', '90 min', '2 hours' -> minutes."""
    t = text.strip().lower().replace(",", ".")
    m = re.fullmatch(r"(?:(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours|std|stunden?))?\s*(?:(\d+)\s*(?:m|min|mins|minutes?|minuten?))?", t)
    if not m or not (m.group(1) or m.group(2)):
        return None
    minutes = round(float(m.group(1) or 0) * 60) + int(m.group(2) or 0)
    return minutes if minutes > 0 else None


def parse_repeat(text: str) -> Repeat | None:
    t = text.strip().lower()
    m = re.fullmatch(
        r"(?:(?P<freq>daily|weekly|monthly|yearly|annually)"
        r"|every\s+(?:(?P<n>\d+)\s+)?(?P<unit>days?|weeks?|months?|years?))"
        r"(?:\s*,?\s*(?:until|till|bis)\s+(?P<until>\S+)|\s*,?\s*(?:for\s+)?(?P<count>\d+)\s*(?:times|x|occurrences))?",
        t,
    )
    if not m:
        return None
    if m.group("freq"):
        freq = "yearly" if m.group("freq") == "annually" else m.group("freq")
        interval = 1
    else:
        unit = m.group("unit").rstrip("s")
        freq = {"day": "daily", "week": "weekly", "month": "monthly", "year": "yearly"}[unit]
        interval = int(m.group("n") or 1)
    until = None
    if m.group("until"):
        until = parse_date(m.group("until"))
        if until is None:
            return None
    count = int(m.group("count")) if m.group("count") else None
    if interval < 1 or (count is not None and count < 1):
        return None
    assert freq in FREQUENCIES
    return Repeat(freq, interval, until, count)


def _unescape(s: str) -> str:
    return s.replace("\\|", "|").strip()


# --- line level parsing ---------------------------------------------------------

def _parse_event_line(body: str, current: date | None, current_wd: int | None, warn) -> Event | None:
    """Parse the text of one event line (bullet already removed)."""
    rest = body.strip()

    # Optional leading date ("10.10.2026 20:00 Concert") or weekday ("Friday 18:00 Pizza").
    ev_date, ev_wd = current, current_wd
    m = _DATE_RE.match(rest)
    m_wd = None if m else _WEEKDAY_LEAD_RE.match(rest)
    if m_wd:
        ev_date, ev_wd = None, _WEEKDAY_LOOKUP[m_wd.group("wd").lower()]
        rest = rest[m_wd.end():]
    if m:
        ev_date = parse_date(m.group(0))
        if ev_date is None:
            warn(f"invalid date '{m.group(0)}'")
            return None
        ev_wd = None
        rest = rest[m.end():].lstrip(" :,–-\t")
        rest = rest.lstrip()

    start = end = None
    m_all = _ALL_DAY_RE.match(rest)
    if m_all:
        rest = rest[m_all.end():]
    else:
        m_range = _RANGE_RE.match(rest)
        if m_range:
            start = parse_time(m_range.group("start"))
            if start is None:
                warn(f"invalid time '{m_range.group('start')}'")
                return None
            if m_range.group("end"):
                end = parse_time(m_range.group("end"))
                if end is None:
                    warn(f"invalid time '{m_range.group('end')}'")
                    return None
            rest = rest[m_range.end():].lstrip(" :\t")
            m_dur = _DURATION_RE.match(rest)
            if m_dur:
                minutes = parse_duration(m_dur.group("dur"))
                if minutes is not None:
                    rest = rest[m_dur.end():]
                    if end is None:
                        end = _add_minutes(start, minutes)
            if end is None:
                end = _add_minutes(start, 60)
            if end == start:
                warn("start and end time are equal; using 1 hour")
                end = _add_minutes(start, 60)

    if ev_date is None and ev_wd is None:
        warn("event has no day (put it under a '## Monday' or '## Monday, 05.10.2026' heading)")
        return None

    parts = _FIELD_SPLIT_RE.split(rest)
    title = _unescape(parts[0]).rstrip(" :")
    fields: dict[str, str] = {}
    for part in parts[1:]:
        key, sep, value = part.partition(":")
        key_norm = _KEY_ALIASES.get(key.strip().lower())
        if not sep or key_norm is None:
            warn(f"unknown field '{part.strip()}' ignored (use at:, tag:, color:, repeat:, notes:)")
            continue
        fields[key_norm] = _unescape(value)

    if not title:
        warn("event has no title")
        return None

    repeat = None
    if fields.get("repeat") and ev_date is None:
        warn("repeat ignored: entries without a date already appear every week")
    elif fields.get("repeat"):
        repeat = parse_repeat(fields["repeat"])
        if repeat is None:
            warn(f"could not understand repeat '{fields['repeat']}' (event added without repeating)")

    color = fields.get("color", "")
    if color and not _valid_color(color):
        warn(f"unknown color '{color}' ignored")
        color = ""

    return Event(
        title=title,
        date=ev_date,
        start=start,
        end=end,
        location=fields.get("location", ""),
        tag=fields.get("tag", ""),
        color=color,
        notes=fields.get("notes", ""),
        repeat=repeat,
        weekday=ev_wd if ev_date is None else None,
    )


def _add_minutes(t: time, minutes: int) -> time:
    total = (t.hour * 60 + t.minute + minutes) % 1440
    return time(total // 60, total % 60)


def _valid_color(c: str) -> bool:
    from PIL import ImageColor

    try:
        ImageColor.getrgb(c)
        return True
    except ValueError:
        return False


def parse_text(text: str) -> ParseResult:
    result = ParseResult()
    current: date | None = None  # day set by a dated heading
    current_wd: int | None = None  # weekday set by an undated "## Monday" heading
    last_event_index: int | None = None
    notes: list[str] = []

    def flush_notes() -> None:
        nonlocal notes
        if last_event_index is not None and notes:
            ev = result.events[last_event_index]
            combined = "\n".join(x for x in [ev.notes, *notes] if x)
            result.events[last_event_index] = ev.with_notes(combined)
        notes = []

    for lineno, raw in enumerate(text.lstrip("﻿").splitlines(), start=1):
        line = raw.rstrip()
        stripped = line.strip()

        def warn(msg: str, _n=lineno, _l=stripped) -> None:
            result.warnings.append(f"Line {_n}: {msg}: {_l}")

        if stripped.startswith("```") or stripped.startswith("~~~"):
            continue  # code fences are transparent: their content is parsed
        if not stripped:
            flush_notes()
            last_event_index = None
            continue
        if re.fullmatch(r"[-*_=]{3,}", stripped) or stripped.startswith("<!--") or stripped.startswith(">"):
            continue

        # Indented, non-bullet-or-bullet line right after an event -> notes.
        if raw[:1] in (" ", "\t") and last_event_index is not None:
            note = _BULLET_RE.sub("", line, count=1) if _BULLET_RE.match(line) else stripped
            note = note.strip()
            if note.lower().startswith(("notes:", "note:")):
                note = note.split(":", 1)[1].strip()
            notes.append(note)
            continue

        flush_notes()
        last_event_index = None

        m_head = _HEADING_RE.match(line)
        if m_head:
            heading = m_head.group(2)
            d = parse_date(heading)
            wd = parse_weekday(heading)
            if d is not None:
                current, current_wd = d, None
                _check_weekday(heading, d, warn)
            elif _DATE_RE.search(heading):
                warn("invalid date in heading")
            elif wd is not None:
                current, current_wd = None, wd
            elif len(m_head.group(1)) == 1 and not result.title:
                title = re.sub(r"^(calendar|kalender)\s*:\s*", "", heading, flags=re.I)
                result.title = title.strip()
            continue

        # A plain line holding only a date ("Monday, 2026-10-05:") also sets the current day.
        if not _BULLET_RE.match(line) and _DATE_LINE_RE.fullmatch(stripped):
            d = parse_date(stripped)
            if d is None:
                warn("invalid date")
            else:
                current, current_wd = d, None
                _check_weekday(stripped, d, warn)
            continue
        if not _BULLET_RE.match(line) and parse_weekday(stripped) is not None:
            current, current_wd = None, parse_weekday(stripped)
            continue

        body = _BULLET_RE.sub("", line, count=1)
        is_bullet = body != line
        if not is_bullet and not (
            _DATE_RE.match(stripped) or _RANGE_RE.match(stripped) or _ALL_DAY_RE.match(stripped)
            or _WEEKDAY_LEAD_RE.match(stripped)
        ):
            warn("not an event line (events start with '- ')")
            continue

        ev = _parse_event_line(body, current, current_wd, warn)
        if ev is not None:
            result.events.append(ev)
            last_event_index = len(result.events) - 1

    flush_notes()
    return result


def _check_weekday(text: str, d: date, warn) -> None:
    """Warn when a heading like 'Tuesday, 05.10.2026' names the wrong weekday."""
    m = _WEEKDAY_WORD_RE.search(_DATE_RE.sub(" ", text))
    if m and _WEEKDAY_LOOKUP[m.group("wd").lower()] != d.weekday():
        warn(f"{m.group('wd')} does not match the date (it is a {WEEKDAYS[d.weekday()]}); the date was used")


def parse_file(path: str) -> ParseResult:
    with open(path, "rb") as fh:
        data = fh.read()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return parse_text(data.decode(enc))
        except UnicodeDecodeError:
            continue
    return parse_text(data.decode("utf-8", errors="replace"))


__all__ = ["ParseResult", "parse_text", "parse_file", "parse_date", "parse_time", "parse_duration", "parse_repeat", "parse_weekday"]
