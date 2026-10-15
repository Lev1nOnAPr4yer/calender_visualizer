"""The visible time range of the week view ("view"), as display minutes.

A day column runs from 01:00 of that day to 01:00 of the next day, so display
minutes go from 60 (01:00) to 1500 (25:00 = 01:00 next day). Anything between
00:00 and 01:00 belongs to the previous day's column.
"""

from __future__ import annotations

import math
from typing import Iterable

from .model import Event

DAY_START = 60  # 01:00
DAY_END = 1500  # 01:00 of the next day
MIN_SPAN = 120  # closest zoom: 2 hours
DEFAULT_VIEW = (8 * 60, 22 * 60)
STEP = 15  # auto-widening rounds to quarter hours
ZOOM_PER_NOTCH = 1.15  # one wheel notch zooms by 15 %
PAN_PER_NOTCH = 0.10  # one wheel notch scrolls by 10 % of the visible span

View = tuple[float, float]  # continuous while scrolling/zooming; rounded only where it helps


def _floor(m: float) -> int:
    return int(math.floor(m / STEP) * STEP)


def _ceil(m: float) -> int:
    return int(math.ceil(m / STEP) * STEP)


def clamp(view: View) -> View:
    """Keep a view inside 01:00..01:00 and at least 2 hours long."""
    start, end = sorted((float(view[0]), float(view[1])))
    span = min(max(end - start, MIN_SPAN), DAY_END - DAY_START)
    start = min(max(start, DAY_START), DAY_END - span)
    return start, start + span


def display_start(minutes: int) -> int:
    """Clock minutes -> display minutes: 00:00-00:59 belongs to the previous day (24:00-24:59)."""
    return minutes + 1440 if minutes < DAY_START else minutes


def entry_extent(ev: Event) -> View | None:
    """Where a timed entry sits in its own display day (end capped at 01:00 next day)."""
    if ev.all_day:
        return None
    s = ev.start.hour * 60 + ev.start.minute
    e = ev.end.hour * 60 + ev.end.minute
    duration = e - s if e > s else e + 1440 - s
    start = display_start(s)
    return start, min(start + duration, DAY_END)


def entries_span(events: Iterable[Event]) -> View | None:
    """Start of the earliest entry -> end of the latest entry (None if nothing is timed)."""
    extents = [x for x in (entry_extent(ev) for ev in events) if x]
    if not extents:
        return None
    return min(a for a, _ in extents), max(b for _, b in extents)


def widen(view: View, span: View | None) -> View:
    """Grow `view` so it includes `span`; never shrinks."""
    if span is None:
        return clamp(view)
    return clamp((min(view[0], _floor(span[0])), max(view[1], _ceil(span[1]))))


def default_view(events: Iterable[Event]) -> View:
    return widen(DEFAULT_VIEW, entries_span(events))


def fit_view(events: Iterable[Event]) -> View | None:
    """The 'earliest entry -> latest entry' stop, as a valid view."""
    span = entries_span(events)
    if span is None:
        return None
    return clamp((_floor(span[0]), _ceil(span[1])))


def zoom(view: View, factor: float, anchor: float, fit: View | None = None) -> View:
    """Zoom around `anchor` (display minutes). factor > 1 zooms out, < 1 zooms in.

    The time under the anchor stays where it is. When the earliest->latest
    entry range (`fit`) lies between the current and the next zoom level, the
    zoom stops exactly there once.
    """
    start, end = view
    span = end - start
    new_span = min(max(span * factor, MIN_SPAN), DAY_END - DAY_START)
    if fit is not None and fit != view:
        fit_span = fit[1] - fit[0]
        if (span < fit_span <= new_span) or (new_span <= fit_span < span):
            return fit
    rel = (anchor - start) / span if span else 0.5
    rel = min(max(rel, 0.0), 1.0)
    new_start = anchor - rel * new_span  # exact: the time under the pointer stays put
    return clamp((new_start, new_start + new_span))


def zoom_notches(view: View, notches: float, anchor: float, fit: View | None = None) -> View:
    """Zoom by wheel notches (1 notch = 120 wheel delta); positive notches zoom in."""
    return zoom(view, ZOOM_PER_NOTCH ** (-notches), anchor, fit)


def pan_notches(view: View, notches: float) -> View:
    """Scroll by wheel notches; positive notches move to earlier hours."""
    return pan(view, -notches * PAN_PER_NOTCH * (view[1] - view[0]))


def pan(view: View, delta: float) -> View:
    """Move the whole range by `delta` minutes, keeping its length."""
    span = view[1] - view[0]
    start = min(max(view[0] + delta, DAY_START), DAY_END - span)
    return start, start + span


def set_start(view: View, start: float) -> View:
    start = min(max(round(start / 30) * 30, DAY_START), view[1] - MIN_SPAN)
    return float(start), view[1]


def set_end(view: View, end: float) -> View:
    end = max(min(round(end / 30) * 30, DAY_END), view[0] + MIN_SPAN)
    return view[0], float(end)


def label(minutes: float) -> str:
    """Display minutes -> 'HH:MM' (24:00 shows as 00:00, 25:00 as 01:00)."""
    m = int(round(minutes)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"
