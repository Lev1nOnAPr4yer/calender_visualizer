from datetime import date

from calviz.model import Calendar
from calviz.parser import parse_file, parse_text
from calviz.render import _layout_columns, render_week
from calviz.resources import SAMPLE
from calviz.writer import to_markdown


def sample_calendar():
    r = parse_file(str(SAMPLE))
    assert not r.warnings
    return Calendar(r.title, r.events)


def test_round_trip():
    cal = sample_calendar()
    again = parse_text(to_markdown(cal))
    assert not again.warnings
    assert again.title == cal.title
    assert set(again.events) == set(cal.events)


def test_add_skips_duplicates():
    cal = sample_calendar()
    n = len(cal.events)
    added, skipped = cal.add(parse_file(str(SAMPLE)).events)
    assert (added, skipped) == (0, n)
    added, _ = cal.add(parse_text("## 2026-10-05\n- 20:00 New thing").events)
    assert added == 1 and len(cal.events) == n + 1


def test_recurrence_expansion():
    cal = Calendar(events=parse_text(
        "## 2026-10-05\n- 18:00 Gym | repeat: weekly until 2026-10-26\n"
        "## 2026-01-31\n- all day Pay rent | repeat: monthly 3 times\n"
    ).events)
    gym = [s.day for s in cal.segments(date(2026, 10, 1), date(2026, 12, 31)) if s.event.title == "Gym"]
    assert gym == [date(2026, 10, 5), date(2026, 10, 12), date(2026, 10, 19), date(2026, 10, 26)]
    rent = [s.day for s in cal.segments(date(2026, 1, 1), date(2026, 12, 31)) if s.event.title == "Pay rent"]
    # February has no 31st, so that month is skipped
    assert rent == [date(2026, 1, 31), date(2026, 3, 31), date(2026, 5, 31)]


def test_midnight_split_into_two_segments():
    cal = Calendar(events=parse_text("## 2026-10-09\n- 22:00-01:00 Concert").events)
    segs = cal.segments(date(2026, 10, 5), date(2026, 10, 11))
    assert [(s.day, s.start_min, s.end_min) for s in segs] == [
        (date(2026, 10, 9), 1320, 1440),
        (date(2026, 10, 10), 0, 60),
    ]


def test_overlap_layout():
    cal = Calendar(events=parse_text("## 2026-10-05\n- 09:00-11:00 A\n- 10:00-12:00 B\n- 11:00-12:00 C\n- 14:00 D").events)
    placed = {s.event.title: (c, n) for s, c, n in _layout_columns(cal.segments(date(2026, 10, 5), date(2026, 10, 5)))}
    assert placed["A"] == (0, 2) and placed["B"] == (1, 2) and placed["C"] == (0, 2)
    assert placed["D"] == (0, 1)


def test_weeks_with_events_is_finite_for_endless_repeats():
    cal = sample_calendar()
    weeks = cal.weeks_with_events()
    assert weeks[0] == date(2026, 10, 5)
    assert all(w.weekday() == 0 for w in weeks)
    assert len(weeks) < 60


def test_render_size_and_hitboxes():
    cal = sample_calendar()
    res = render_week(cal, date(2026, 10, 5), scale=2, width=1400, height=900, highlight_today=False)
    assert res.image.size == (2800, 1800)
    assert len(res.hitboxes) >= 15
    hb = res.hitboxes[-1]
    x0, y0, x1, y1 = hb.box
    assert res.hit((x0 + x1) / 2, (y0 + y1) / 2) is hb


def test_render_empty_calendar():
    res = render_week(Calendar(), date(2026, 10, 5))
    assert res.image.width == 1400 and not res.hitboxes
