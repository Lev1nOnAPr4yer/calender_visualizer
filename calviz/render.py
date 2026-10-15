"""Draw a week view (7 day columns, hour rows) with Pillow.

The same renderer is used for the on-screen view and for image export, so
what you see in the program is exactly what gets exported.
"""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache

from PIL import Image, ImageColor, ImageDraw, ImageFont

from .model import WEEKDAYS, Calendar, Event, Segment, fmt_date, today
from .viewrange import DAY_END, DAY_START, clamp, default_view
from .viewrange import label as view_label
from .resources import FONT_BOLD, FONT_REGULAR

PALETTE = [
    "#3b82f6",  # blue
    "#10b981",  # green
    "#f59e0b",  # amber
    "#8b5cf6",  # violet
    "#14b8a6",  # teal
    "#ec4899",  # pink
    "#f97316",  # orange
    "#6366f1",  # indigo
    "#84cc16",  # lime
    "#ef4444",  # red
]
DEFAULT_COLOR = "#3b82f6"

BG = (255, 255, 255)
GRID = (229, 231, 235)
GRID_HALF = (243, 244, 246)
TEXT = (17, 24, 39)
MUTED = (107, 114, 128)
TODAY_BG = (239, 246, 255)
WEEKEND_BG = (250, 250, 250)
NOW_LINE = (239, 68, 68)


@dataclass
class HitBox:
    box: tuple[float, float, float, float]  # in output-image pixels
    event: Event
    occurrence: date


@dataclass
class RenderResult:
    image: Image.Image
    hitboxes: list[HitBox] = field(default_factory=list)
    grid: tuple[float, float] = (0.0, 0.0)  # y of the hour grid's top and bottom, in pixels
    view: tuple[int, int] = (0, 0)  # visible range in display minutes

    def minutes_at(self, y: float) -> float:
        """Display minutes under pixel row `y` (clamped to the grid)."""
        top, bottom = self.grid
        if bottom <= top:
            return float(self.view[0])
        rel = min(max((y - top) / (bottom - top), 0.0), 1.0)
        return self.view[0] + rel * (self.view[1] - self.view[0])

    def hit(self, x: float, y: float) -> HitBox | None:
        for hb in reversed(self.hitboxes):
            x0, y0, x1, y1 = hb.box
            if x0 <= x <= x1 and y0 <= y <= y1:
                return hb
        return None


@lru_cache(maxsize=64)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REGULAR
    try:
        return ImageFont.truetype(str(path), max(size, 6))
    except OSError:
        return ImageFont.load_default(max(size, 6))


def tag_colors(cal: Calendar) -> dict[str, str]:
    """Give every tag its own palette colour (in alphabetical tag order)."""
    tags = sorted({e.tag.lower() for e in cal.events if e.tag})
    return {t: PALETTE[i % len(PALETTE)] for i, t in enumerate(tags)}


def event_color(ev: Event, tags: dict[str, str] | None = None) -> tuple[int, int, int]:
    if ev.color:
        try:
            return ImageColor.getrgb(ev.color)[:3]
        except ValueError:
            pass
    if ev.tag:
        key = ev.tag.lower()
        if tags and key in tags:
            return ImageColor.getrgb(tags[key])
        return ImageColor.getrgb(PALETTE[zlib.crc32(key.encode()) % len(PALETTE)])
    return ImageColor.getrgb(DEFAULT_COLOR)


def _tint(rgb: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    """Mix colour with white; amount=0 -> colour, 1 -> white."""
    return tuple(round(c + (255 - c) * amount) for c in rgb)


def _shade(rgb: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(round(c * (1 - amount)) for c in rgb)


def _layout_columns(segs: list[Segment]) -> list[tuple[Segment, int, int]]:
    """Assign overlapping segments to side-by-side columns.

    Returns (segment, column index, number of columns in its overlap group).
    """
    segs = sorted(segs, key=lambda s: (s.start_min, -s.end_min))
    placed: list[tuple[Segment, int, int]] = []
    group: list[tuple[Segment, int]] = []
    col_ends: list[int] = []
    group_end = -1

    def close_group() -> None:
        n = max((c for _, c in group), default=-1) + 1
        placed.extend((s, c, n) for s, c in group)

    for s in segs:
        if s.start_min >= group_end and group:
            close_group()
            group, col_ends = [], []
        for i, end in enumerate(col_ends):
            if end <= s.start_min:
                col_ends[i] = s.end_min
                group.append((s, i))
                break
        else:
            col_ends.append(s.end_min)
            group.append((s, len(col_ends) - 1))
        group_end = max(group_end, s.end_min)
    if group:
        close_group()
    return placed


def _ellipsize(draw: ImageDraw.ImageDraw, text: str, font, max_w: float) -> str:
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…" if text else ""


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: float, max_lines: int) -> list[str]:
    if max_lines <= 0 or max_w <= 0:
        return []
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _ellipsize(draw, lines[-1] + " …", font, max_w)
    return [_ellipsize(draw, ln, font, max_w) for ln in lines]


@dataclass
class Note:
    """An entry piece outside the visible hours, listed in the notes row of its column."""

    event: Event
    column: int
    text: str
    occurrence: date


def display_pieces(cal: Calendar, week_start: date) -> tuple[list[list[Segment]], set[int]]:
    """Timed entry pieces per day column; each column covers 01:00 -> 01:00 next day.

    Minutes in the returned segments are display minutes (60..1500). The second
    value holds id()s of pieces that continue an entry from the previous column.
    """
    columns: list[list[Segment]] = [[] for _ in range(7)]
    continued: set[int] = set()
    lo = week_start - timedelta(days=1)
    hi = week_start + timedelta(days=7)  # an entry at 00:30 next Monday belongs to Sunday
    for ev in cal.events:
        if ev.all_day:
            continue
        s = ev.start.hour * 60 + ev.start.minute
        e = ev.end.hour * 60 + ev.end.minute
        duration = e - s if e > s else e + 1440 - s
        for d in cal.occurrence_dates(ev, lo, hi):
            if d < lo:
                continue
            a = (d - week_start).days * 1440 + s
            b = a + duration
            for col in range(max(0, (a - DAY_END) // 1440), min(6, (b - DAY_START) // 1440) + 1):
                w0, w1 = col * 1440 + DAY_START, col * 1440 + DAY_END
                pa, pb = max(a, w0), min(b, w1)
                if pb > pa:
                    seg = Segment(ev, week_start + timedelta(days=col), pa - col * 1440, pb - col * 1440, occurrence=d)
                    columns[col].append(seg)
                    if a < w0:
                        continued.add(id(seg))
    return columns, continued


def render_week(
    cal: Calendar,
    week_start: date,
    scale: float = 1.0,
    width: int = 1400,
    height: int | None = None,
    highlight_today: bool = True,
    show_dates: bool = True,
    tags: dict[str, str] | None = None,
    view: tuple[int, int] | None = None,
) -> RenderResult:
    """Render the week starting at `week_start` (a Monday).

    `width`/`height` are in base units; the output image is that size times
    `scale`. If `height` is None it is chosen from the visible hour range.
    `view` is the visible range in display minutes (see viewrange); entries
    entirely outside it are listed as notes above the hour grid.
    With `show_dates=False` the week is drawn as an undated weekly planner:
    weekday names only, no dates, week numbers, months or years.
    """
    week_end = week_start + timedelta(days=6)
    view = clamp(view) if view is not None else default_view(cal.events)
    vs, ve = view
    tags = tags if tags is not None else tag_colors(cal)
    days = [week_start + timedelta(days=i) for i in range(7)]
    now_day = today()

    def is_today(day: date) -> bool:
        if not highlight_today:
            return False
        return day == now_day if show_dates else day.weekday() == now_day.weekday()

    u = scale  # base unit -> pixels
    title_h = 64
    dayhead_h = 46
    gutter = 64
    pad = 16

    # All-day rows
    allday: dict[date, list[Segment]] = {d: [] for d in days}
    for s in cal.segments(week_start, week_end):
        if s.all_day:
            allday[s.day].append(s)
    for lst in allday.values():
        lst.sort(key=lambda s: s.event.title.lower())
    allday_rows = max((len(v) for v in allday.values()), default=0)
    row_h = 24
    allday_h = (allday_rows * (row_h + 3) + 8) if allday_rows else 0

    # Timed pieces: inside the view they are blocks, entirely outside they become notes.
    columns, continued = display_pieces(cal, week_start)
    visible: list[list[Segment]] = [[] for _ in range(7)]
    notes: list[list[Note]] = [[] for _ in range(7)]
    for i, pieces in enumerate(columns):
        for seg in sorted(pieces, key=lambda x: x.start_min):
            if seg.end_min > vs and seg.start_min < ve:
                visible[i].append(seg)
                continue
            ev = seg.event
            if id(seg) in continued:
                text = f"↳ {ev.title} until {ev.end:%H:%M}"
            else:
                text = f"{ev.time_label()} {ev.title}"
            notes[i].append(Note(ev, i, text, seg.occurrence))
    note_rows = max((len(n) for n in notes), default=0)
    note_h = 19
    notes_h = (note_rows * (note_h + 2) + 6) if note_rows else 0

    hours = (ve - vs) / 60
    header_h = title_h + dayhead_h + allday_h + notes_h
    if height is None:
        hour_h = 58.0
        height = int(header_h + hours * hour_h + pad * 2)
    else:
        hour_h = max(20.0, (height - header_h - pad * 2) / hours)

    W, H = round(width * u), round(height * u)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    hit: list[HitBox] = []

    x0 = (pad + gutter) * u
    x1 = (width - pad) * u
    col_w = (x1 - x0) / 7
    grid_top = header_h * u
    grid_bottom = grid_top + hours * hour_h * u

    # Title
    subtitle, headers = header_texts(week_start, show_dates)
    title = cal.title or ("Calendar" if show_dates else "Weekly Planner")
    if not show_dates and not cal.title:
        subtitle = ""  # the default title already says it
    f_title = _font(round(24 * u), True)
    f_sub = _font(round(16 * u))
    d.text((pad * u, 18 * u), title, font=f_title, fill=TEXT)
    d.text((x1, 22 * u), subtitle, font=f_sub, fill=MUTED, anchor="ra")

    # Column backgrounds
    for i, day in enumerate(days):
        cx0 = x0 + i * col_w
        bg = None
        if is_today(day):
            bg = TODAY_BG
        elif day.weekday() >= 5:
            bg = WEEKEND_BG
        if bg:
            d.rectangle([cx0, title_h * u, cx0 + col_w, grid_bottom], fill=bg)

    # Day headers
    f_dname = _font(round(13 * u), True)
    f_dnum = _font(round(20 * u), True)
    for i, (day, (name, label)) in enumerate(zip(days, headers)):
        cx = x0 + i * col_w + col_w / 2
        accent = (37, 99, 235) if is_today(day) else None
        if label:
            d.text((cx, (title_h + 4) * u), name, font=f_dname, fill=accent or MUTED, anchor="ma")
            d.text((cx, (title_h + 20) * u), label, font=f_dnum, fill=accent or TEXT, anchor="ma")
        else:
            d.text((cx, (title_h + dayhead_h / 2 - 3) * u), name, font=f_dnum, fill=accent or TEXT, anchor="mm")

    # All-day events
    f_ev = _font(round(12 * u), True)
    top = (title_h + dayhead_h + 4) * u
    for i, day in enumerate(days):
        for r, s in enumerate(allday[day]):
            bx0 = x0 + i * col_w + 3 * u
            bx1 = x0 + (i + 1) * col_w - 3 * u
            by0 = top + r * (row_h + 3) * u
            by1 = by0 + row_h * u
            col = event_color(s.event, tags)
            d.rounded_rectangle([bx0, by0, bx1, by1], radius=4 * u, fill=col)
            txt = _ellipsize(d, s.event.title, f_ev, bx1 - bx0 - 12 * u)
            d.text((bx0 + 6 * u, (by0 + by1) / 2), txt, font=f_ev, fill=(255, 255, 255), anchor="lm")
            hit.append(HitBox((bx0, by0, bx1, by1), s.event, s.occurrence))

    # Notes row: entries outside the visible hours (e.g. "↳ Concert until 03:00")
    f_note = _font(round(11 * u), True)
    ntop = (title_h + dayhead_h + allday_h + 3) * u
    for i, col_notes in enumerate(notes):
        for r, note in enumerate(col_notes):
            bx0 = x0 + i * col_w + 3 * u
            bx1 = x0 + (i + 1) * col_w - 3 * u
            by0 = ntop + r * (note_h + 2) * u
            by1 = by0 + note_h * u
            col = event_color(note.event, tags)
            d.rounded_rectangle([bx0, by0, bx1, by1], radius=4 * u, fill=_tint(col, 0.85), outline=_tint(col, 0.5),
                                width=max(1, round(u)))
            d.rounded_rectangle([bx0, by0, bx0 + 4 * u, by1], radius=2 * u, fill=col)
            txt = _ellipsize(d, note.text, f_note, bx1 - bx0 - 14 * u)
            d.text((bx0 + 9 * u, (by0 + by1) / 2), txt, font=f_note, fill=_shade(col, 0.55), anchor="lm")
            hit.append(HitBox((bx0, by0, bx1, by1), note.event, note.occurrence))

    # Hour grid
    def y_of(minutes: float) -> float:
        return grid_top + (minutes - vs) / 60 * hour_h * u

    f_hour = _font(round(11 * u))
    label_halves = hour_h >= 90
    m = math.ceil(vs / 30) * 30
    while m <= ve:
        y = y_of(m)
        full = m % 60 == 0
        d.line([x0, y, x1, y], fill=GRID if full else GRID_HALF, width=max(1, round(u)))
        if full or label_halves:
            d.text((x0 - 8 * u, y), view_label(m), font=f_hour, fill=MUTED if full else _tint(MUTED, 0.3), anchor="rm")
        m += 30
    for i in range(8):
        x = x0 + i * col_w
        d.line([x, (title_h + dayhead_h - 6) * u, x, grid_bottom], fill=GRID, width=max(1, round(u)))
    d.line([x0, grid_top, x1, grid_top], fill=(209, 213, 219), width=max(1, round(1.5 * u)))
    d.line([x0, grid_bottom, x1, grid_bottom], fill=GRID, width=max(1, round(u)))

    # Timed events (clipped to the view, but labelled with their real times)
    f_time = _font(round(11 * u))
    f_title_ev = _font(round(12.5 * u), True)
    line_h = 15 * u
    for i in range(7):
        for s, c, n in _layout_columns(visible[i]):
            sub_w = (col_w - 6 * u) / n
            bx0 = x0 + i * col_w + 3 * u + c * sub_w
            bx1 = bx0 + sub_w - 2 * u
            by0 = y_of(max(s.start_min, vs)) + 1 * u
            by1 = max(y_of(min(s.end_min, ve)) - 1 * u, by0 + 14 * u)
            col = event_color(s.event, tags)
            d.rounded_rectangle([bx0, by0, bx1, by1], radius=5 * u, fill=_tint(col, 0.82), outline=_tint(col, 0.45), width=max(1, round(u)))
            d.rounded_rectangle([bx0, by0, bx0 + 4 * u, by1], radius=2 * u, fill=col)
            tx = bx0 + 9 * u
            tw = bx1 - tx - 4 * u
            ty = by0 + 4 * u
            avail = int((by1 - ty - 2 * u) // line_h)
            dark = _shade(col, 0.55)
            ev = s.event
            is_cont = id(s) in continued
            if avail <= 1:
                one = f"↳ {ev.title} until {ev.end:%H:%M}" if is_cont else f"{ev.start:%H:%M} {ev.title}"
                d.text((tx, ty - 2 * u), _ellipsize(d, one, f_title_ev, tw), font=f_title_ev, fill=dark)
            else:
                for ln in _wrap(d, ev.title, f_title_ev, tw, avail - 1):
                    d.text((tx, ty), ln, font=f_title_ev, fill=dark)
                    ty += line_h
                extras = [ev.time_label()]
                if ev.location:
                    extras.append(ev.location)
                for extra in extras:
                    if ty + line_h > by1 - 2 * u:
                        break
                    d.text((tx, ty), _ellipsize(d, extra, f_time, tw), font=f_time, fill=_shade(col, 0.35))
                    ty += line_h
            hit.append(HitBox((bx0, by0, bx1, by1), ev, s.occurrence))

    # "Now" line (00:00-00:59 is drawn at the end of the previous day's column)
    if highlight_today:
        from datetime import datetime

        now = datetime.now()
        mins = now.hour * 60 + now.minute
        disp_day = now_day
        if mins < DAY_START:
            mins += 1440
            disp_day = now_day - timedelta(days=1)
        cols = [i for i, day in enumerate(days)
                if (day == disp_day if show_dates else day.weekday() == disp_day.weekday())]
        if cols and vs <= mins <= ve:
            i = cols[0]
            y = y_of(mins)
            d.line([x0 + i * col_w, y, x0 + (i + 1) * col_w, y], fill=NOW_LINE, width=max(2, round(2 * u)))
            r = 4 * u
            d.ellipse([x0 + i * col_w - r, y - r, x0 + i * col_w + r, y + r], fill=NOW_LINE)

    return RenderResult(img, hit, grid=(grid_top, grid_bottom), view=view)


def header_texts(week_start: date, show_dates: bool) -> tuple[str, list[tuple[str, str]]]:
    """Subtitle and per-day (name, date label) texts for the week header."""
    days = [week_start + timedelta(days=i) for i in range(7)]
    if not show_dates:
        return "Weekly planner", [(WEEKDAYS[d.weekday()].upper(), "") for d in days]
    week_end = days[-1]
    subtitle = f"Week {week_start.isocalendar()[1]}  ·  {fmt_date(week_start)} – {fmt_date(week_end)}"
    return subtitle, [(WEEKDAYS[d.weekday()][:3].upper(), f"{d.day:02d}.{d.month:02d}.") for d in days]


def export_week(
    cal: Calendar, week_start: date, path: str, scale: float = 3.0, show_dates: bool = True,
    tags: dict[str, str] | None = None, view: tuple[int, int] | None = None,
) -> None:
    result = render_week(cal, week_start, scale=scale, highlight_today=False, show_dates=show_dates, tags=tags,
                         view=view)
    result.image.save(path, dpi=(72 * scale, 72 * scale))
