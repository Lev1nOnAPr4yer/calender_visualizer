"""Core data model: events, recurrence rules and the calendar container."""

from __future__ import annotations

import calendar as _cal
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from typing import Iterable, Iterator

FREQUENCIES = ("daily", "weekly", "monthly", "yearly")


@dataclass(frozen=True)
class Repeat:
    """A simple recurrence rule: every `interval` days/weeks/months/years."""

    freq: str  # one of FREQUENCIES
    interval: int = 1
    until: date | None = None
    count: int | None = None

    def describe(self) -> str:
        """Canonical text form, understood by the parser."""
        if self.interval == 1:
            text = self.freq
        else:
            unit = {"daily": "days", "weekly": "weeks", "monthly": "months", "yearly": "years"}[self.freq]
            text = f"every {self.interval} {unit}"
        if self.until:
            text += f" until {self.until.isoformat()}"
        elif self.count:
            text += f" {self.count} times"
        return text

    def dates(self, first: date, range_end: date) -> Iterator[date]:
        """Yield occurrence dates starting at `first`, up to and including `range_end`."""
        n = 0
        k = 0
        while True:
            if self.count is not None and n >= self.count:
                return
            d = self._nth(first, k)
            k += 1
            if d is None:  # e.g. Feb 31 for a monthly rule: skip that month
                if k > 10000:
                    return
                continue
            if d > range_end or (self.until and d > self.until):
                return
            n += 1
            yield d

    def _nth(self, first: date, k: int) -> date | None:
        step = k * self.interval
        if self.freq == "daily":
            return first + timedelta(days=step)
        if self.freq == "weekly":
            return first + timedelta(weeks=step)
        if self.freq == "monthly":
            months = first.month - 1 + step
            year, month = first.year + months // 12, months % 12 + 1
        else:  # yearly
            year, month = first.year + step, first.month
        if first.day > _cal.monthrange(year, month)[1]:
            return None
        return date(year, month, first.day)


@dataclass(frozen=True)
class Event:
    title: str
    date: date
    start: time | None = None  # None means all-day
    end: time | None = None
    location: str = ""
    tag: str = ""
    color: str = ""
    notes: str = ""
    repeat: Repeat | None = None

    @property
    def all_day(self) -> bool:
        return self.start is None

    @property
    def crosses_midnight(self) -> bool:
        return self.start is not None and self.end is not None and self.end <= self.start

    def with_notes(self, notes: str) -> "Event":
        return replace(self, notes=notes)

    def time_label(self) -> str:
        if self.all_day:
            return "All day"
        return f"{self.start:%H:%M}–{self.end:%H:%M}"


@dataclass(frozen=True)
class Segment:
    """A piece of an event occurrence that falls on one calendar day.

    Timed events that cross midnight produce two segments. Minutes are
    measured from 00:00 of `day`; `end_min` may be 1440 (= midnight).
    """

    event: Event
    day: date
    start_min: int = 0
    end_min: int = 0
    occurrence: date | None = None  # the date the occurrence started on

    @property
    def all_day(self) -> bool:
        return self.event.all_day


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


@dataclass
class Calendar:
    title: str = ""
    events: list[Event] = field(default_factory=list)

    def add(self, events: Iterable[Event]) -> tuple[int, int]:
        """Merge events; exact duplicates are skipped. Returns (added, skipped)."""
        existing = set(self.events)
        added = skipped = 0
        for ev in events:
            if ev in existing:
                skipped += 1
                continue
            self.events.append(ev)
            existing.add(ev)
            added += 1
        return added, skipped

    def replace_all(self, events: Iterable[Event], title: str = "") -> None:
        self.events = []
        self.title = title
        self.add(events)

    def remove(self, event: Event) -> None:
        self.events = [e for e in self.events if e != event]

    def sorted_events(self) -> list[Event]:
        return sorted(
            self.events,
            key=lambda e: (e.date, e.start is not None, e.start or time(0), e.title.lower()),
        )

    def first_date(self) -> date | None:
        return min((e.date for e in self.events), default=None)

    def occurrence_dates(self, event: Event, range_end: date) -> Iterator[date]:
        if event.repeat is None:
            if event.date <= range_end:
                yield event.date
            return
        yield from event.repeat.dates(event.date, range_end)

    def segments(self, start: date, end: date) -> list[Segment]:
        """All event pieces that fall on days in [start, end] (inclusive)."""
        out: list[Segment] = []
        look_back = start - timedelta(days=1)  # catch events crossing midnight into `start`
        for ev in self.events:
            for d in self.occurrence_dates(ev, end):
                if d < look_back:
                    continue
                if ev.all_day:
                    if start <= d <= end:
                        out.append(Segment(ev, d, occurrence=d))
                    continue
                s, e = _minutes(ev.start), _minutes(ev.end)
                if ev.crosses_midnight:
                    pieces = [(d, s, 1440), (d + timedelta(days=1), 0, e)]
                else:
                    pieces = [(d, s, e)]
                for day, a, b in pieces:
                    if start <= day <= end and b > a:
                        out.append(Segment(ev, day, a, b, occurrence=d))
        return out

    def weeks_with_events(self) -> list[date]:
        """Mondays of every week containing at least one event occurrence.

        Open-ended repeating events are only followed up to one year past the
        last dated event, so this list always stays finite.
        """
        if not self.events:
            return []
        last = max(e.date for e in self.events)
        horizon = max(last, max((e.repeat.until for e in self.events if e.repeat and e.repeat.until), default=last))
        horizon = min(horizon, last + timedelta(days=366))
        mondays = set()
        for seg in self.segments(self.first_date(), horizon + timedelta(days=1)):
            mondays.add(week_start(seg.day))
        return sorted(mondays)


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def today() -> date:
    return datetime.now().date()
