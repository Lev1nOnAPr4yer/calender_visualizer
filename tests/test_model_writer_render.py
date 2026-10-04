from datetime import date, timedelta

from calviz.model import PLANNER_WEEK, Calendar
from calviz.parser import parse_file, parse_text
from calviz.render import _layout_columns, header_texts, render_week
from calviz.resources import SAMPLE, SAMPLE_DATED
from calviz.writer import to_markdown


def sample_calendar(path=SAMPLE_DATED):
    r = parse_file(str(path))
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
    added, skipped = cal.add(parse_file(str(SAMPLE_DATED)).events)
    assert (added, skipped) == (0, n)
    added, _ = cal.add(parse_text("## 2026-10-05\n- 20:00 New thing").events)
    assert added == 1 and len(cal.events) == n + 1


def test_recurrence_expansion():
    cal = Calendar(events=parse_text(
        "## 05.10.2026\n- 18:00 Gym | repeat: weekly until 26.10.2026\n"
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


# --- undated weekly planner -------------------------------------------------

PLANNER_AND_DATED = """# Calendar: Mixed
## Monday
- 07:00-08:00 Gym
## Sunday
- 23:00-01:00 Late show
## Wednesday, 07.10.2026
- 10:00 Dentist
"""


def test_undated_entries_appear_in_every_week():
    cal = Calendar(events=parse_text(PLANNER_AND_DATED).events)
    assert cal.is_dated()
    for monday in (date(2026, 1, 5), date(2026, 10, 5), date(2031, 6, 2)):
        segs = cal.segments(monday, monday + timedelta(days=6))
        gym = [s.day for s in segs if s.event.title == "Gym"]
        assert gym == [monday]
    # only the week with the dated entry counts as a week "with events"
    assert cal.weeks_with_events() == [date(2026, 10, 5)]


def test_undated_midnight_crossing_wraps_into_monday():
    cal = Calendar(events=parse_text(PLANNER_AND_DATED).events)
    segs = cal.segments(PLANNER_WEEK, PLANNER_WEEK + timedelta(days=6))
    late = sorted((s.day.weekday(), s.start_min, s.end_min) for s in segs if s.event.title == "Late show")
    assert late == [(0, 0, 60), (6, 1380, 1440)]


def test_planner_only_is_not_dated():
    cal = sample_calendar(SAMPLE)
    assert not cal.is_dated() and cal.first_date() is None and cal.weeks_with_events() == []
    res = render_week(cal, PLANNER_WEEK, show_dates=False, highlight_today=False)
    assert len(res.hitboxes) == 18  # 17 entries, the Friday night out continues into Saturday


def test_header_texts():
    sub, heads = header_texts(PLANNER_WEEK, show_dates=False)
    assert sub == "Weekly planner"
    assert heads[0] == ("MONDAY", "") and heads[6] == ("SUNDAY", "")
    assert "2001" not in sub
    sub, heads = header_texts(date(2026, 10, 5), show_dates=True)
    assert sub == "Week 41  ·  05.10.2026 – 11.10.2026"
    assert heads[0] == ("MON", "05.10.")


def test_mixed_round_trip_uses_dd_mm_yyyy():
    cal = Calendar("Mixed", parse_text(PLANNER_AND_DATED).events)
    md = to_markdown(cal)
    assert "## Monday\n" in md and "## Wednesday, 07.10.2026" in md
    assert "2026-" not in md
    assert md.index("## Monday\n") < md.index("07.10.2026")
    again = parse_text(md)
    assert not again.warnings and set(again.events) == set(cal.events)
