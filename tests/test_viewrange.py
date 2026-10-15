from datetime import date, time

from calviz.model import PLANNER_WEEK, Calendar
from calviz.parser import parse_text
from calviz.render import display_pieces, render_week
from calviz.viewrange import (
    DEFAULT_VIEW, MIN_SPAN, clamp, default_view, entries_span, fit_view, label, pan, set_end, set_start, widen, zoom,
)

MON = date(2026, 10, 5)


def cal(text):
    return Calendar(events=parse_text(text).events)


def pieces_of(c, title, week=MON):
    cols, cont = display_pieces(c, week)
    return [(i, s.start_min, s.end_min, id(s) in cont) for i, col in enumerate(cols) for s in col if s.event.title == title]


# --- pieces: one column = 01:00 -> 01:00 next day ---------------------------------

def test_late_night_is_one_block():
    assert pieces_of(cal("## 05.10.2026\n- 22:00-01:00 Party"), "Party") == [(0, 1320, 1500, False)]


def test_after_midnight_start_belongs_to_previous_day():
    assert pieces_of(cal("## 06.10.2026\n- 00:30-02:00 Snack"), "Snack") == [(0, 1470, 1500, False), (1, 60, 120, True)]


def test_long_night_splits_at_one():
    assert pieces_of(cal("## 05.10.2026\n- 23:00-03:00 Concert"), "Concert") == [(0, 1380, 1500, False), (1, 60, 180, True)]


def test_undated_sunday_night_is_one_block():
    assert pieces_of(cal("## Sunday\n- 23:00-01:00 Late show"), "Late show", PLANNER_WEEK) == [(6, 1380, 1500, False)]


def test_entry_at_0030_next_monday_shows_on_sunday():
    assert pieces_of(cal("## 12.10.2026\n- 00:30 Late"), "Late") == [(6, 1470, 1500, False)]


# --- notes row ----------------------------------------------------------------------

def test_continuation_outside_view_becomes_note_above_grid():
    c = cal("## 05.10.2026\n- 21:00-03:00 Concert\n## 06.10.2026\n- 08:00-09:00 Breakfast")
    res = render_week(c, MON, view=(480, 1320), highlight_today=False)
    grid_top, _ = res.grid
    concert = [hb for hb in res.hitboxes if hb.event.title == "Concert"]
    breakfast = [hb for hb in res.hitboxes if hb.event.title == "Breakfast"][0]
    note = [hb for hb in concert if hb.box[3] <= grid_top]
    assert len(note) == 1 and note[0].box[0] > breakfast.box[0] - 20  # Tuesday column
    assert breakfast.box[1] >= grid_top and note[0].box[3] <= breakfast.box[1]
    # Monday part 21:00-22:00 is visible (clipped), not a note
    assert any(hb.box[1] >= grid_top for hb in concert)


def test_entry_partly_inside_is_clipped_not_noted():
    c = cal("## 05.10.2026\n- 06:00-10:00 Early")
    res = render_week(c, MON, view=(480, 1320), highlight_today=False)
    hb = [h for h in res.hitboxes if h.event.title == "Early"]
    assert len(hb) == 1 and hb[0].box[1] >= res.grid[0]


# --- range helpers --------------------------------------------------------------------

def test_default_and_widen():
    assert DEFAULT_VIEW == (480, 1320)
    assert default_view([]) == (480, 1320)
    assert default_view(cal("## Mo\n- 06:10-07:00 Gym\n- 22:00-01:00 Late").events) == (360, 1500)
    assert widen((480, 1320), (600, 700)) == (480, 1320)  # never shrinks
    assert widen((480, 1320), None) == (480, 1320)


def test_entries_span_caps_at_one_am():
    ev = cal("## Mo\n- 23:00-04:00 Night shift").events
    assert entries_span(ev) == (1380, 1500)
    assert entries_span(cal("## Mo\n- all day X").events) is None


def test_clamp_limits():
    assert clamp((0, 2000)) == (60, 1500)
    assert clamp((600, 610)) == (600, 600 + MIN_SPAN)
    assert clamp((1450, 1500)) == (1500 - MIN_SPAN, 1500)


def test_zoom_bounds_and_anchor():
    v = (480, 1320)
    for _ in range(40):
        v = zoom(v, 0.8, 720)
    assert v[1] - v[0] == MIN_SPAN and v[0] <= 720 <= v[1]
    for _ in range(40):
        v = zoom(v, 1.25, 720)
    assert v == (60, 1500)
    # anchor stays at about the same relative position
    v2 = zoom((480, 1320), 0.8, 600)
    assert abs((600 - v2[0]) / (v2[1] - v2[0]) - (600 - 480) / 840) < 0.05


def test_zoom_stops_once_at_entries_span():
    fit = fit_view(cal("## Mo\n- 09:00-17:00 Work").events)
    assert fit == (540, 1020)
    v, seen = (480, 1320), []
    for _ in range(10):
        v = zoom(v, 0.8, 780, fit)
        seen.append(v)
    assert seen.count(fit) == 1
    v, seen = (720, 840), []
    for _ in range(12):
        v = zoom(v, 1.25, 780, fit)
        seen.append(v)
    assert seen.count(fit) == 1


def test_pan_and_handles():
    assert pan((480, 1320), 120) == (600, 1440)
    assert pan((480, 1320), 1000) == (660, 1500)
    assert set_start((480, 1320), 1300) == (1200, 1320)  # keeps 2 h
    assert set_end((480, 1320), 2000) == (480, 1500)
    assert label(1440) == "00:00" and label(1500) == "01:00" and label(510) == "08:30"


# --- smooth zoom / scroll (continuous, no rounding jitter) ---------------------------

def test_zoom_keeps_anchor_exactly_in_and_out():
    from calviz.viewrange import zoom_notches
    v, anchor = (480.0, 1320.0), 700.0
    rel0 = (anchor - v[0]) / (v[1] - v[0])
    for n in [1] * 10 + [-1] * 10 + [0.25] * 8:
        v = zoom_notches(v, n, anchor)
        assert abs((anchor - v[0]) / (v[1] - v[0]) - rel0) < 0.005


def test_fractional_notches_are_small_steps():
    from calviz.viewrange import pan_notches, zoom_notches
    v = (480.0, 1320.0)
    z = zoom_notches(v, 0.25, 900)
    assert 0.96 < (z[1] - z[0]) / 840 < 0.975
    p = pan_notches(v, -0.25)  # scrolling down a little -> later hours
    assert abs(p[0] - (480 + 0.025 * 840)) < 1e-6
    for _ in range(100):
        p = pan_notches(p, -1)
    assert p == (1500 - 840, 1500)


def test_fit_stop_still_hit_once_with_small_steps():
    from calviz.viewrange import zoom_notches
    fit = fit_view(cal("## Mo\n- 09:00-17:00 Work").events)
    v, seen = (480.0, 1320.0), []
    for _ in range(40):
        v = zoom_notches(v, 0.25, 780, fit)
        seen.append(v)
    assert seen.count(fit) == 1


def test_min_note_rows_keeps_grid_top_still():
    c = cal("## 05.10.2026\n- 07:00-08:00 Early\n- 12:00-13:00 Lunch")
    with_note = render_week(c, MON, view=(600, 1000), highlight_today=False, height=800)
    without = render_week(c, MON, view=(400, 1000), highlight_today=False, height=800, min_note_rows=1)
    assert with_note.note_rows == 1 and without.note_rows == 1
    assert with_note.grid[0] == without.grid[0]
