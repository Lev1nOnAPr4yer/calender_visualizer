from datetime import date, time

from calviz.model import Repeat
from calviz.parser import parse_duration, parse_repeat, parse_text, parse_time


def one(text):
    r = parse_text(text)
    assert not r.warnings, r.warnings
    assert len(r.events) == 1
    return r.events[0]


def test_heading_and_range():
    ev = one("## Monday, 2026-10-05\n- 09:00-10:30 Team meeting | at: Room 4 | tag: work\n")
    assert ev.date == date(2026, 10, 5)
    assert (ev.start, ev.end) == (time(9), time(10, 30))
    assert ev.title == "Team meeting"
    assert ev.location == "Room 4" and ev.tag == "work"


def test_title_from_h1():
    r = parse_text("# Calendar: Autumn\n## 2026-10-05\n- 10:00 X\n")
    assert r.title == "Autumn"


def test_start_only_defaults_to_one_hour():
    ev = one("## 2026-10-05\n- 14:00 Dentist")
    assert ev.end == time(15)


def test_duration():
    assert one("## 2026-10-05\n- 14:00 (45m) Call").end == time(14, 45)
    assert one("## 2026-10-05\n- 14:00 (1h30m) Call").end == time(15, 30)
    assert parse_duration("1.5h") == 90
    assert parse_duration("90 min") == 90
    assert parse_duration("soon") is None


def test_am_pm():
    ev = one("## 2026-10-05\n- 9am-2:30pm Workshop")
    assert (ev.start, ev.end) == (time(9), time(14, 30))
    assert parse_time("12am") == time(0)
    assert parse_time("12pm") == time(12)
    assert parse_time("25:00") is None


def test_all_day_and_no_time():
    assert one("## 2026-10-05\n- all day Birthday").all_day
    assert one("## 2026-10-05\n- Birthday").all_day


def test_inline_date_without_heading():
    ev = one("- 2026-10-10 20:00-23:00 Concert")
    assert ev.date == date(2026, 10, 10) and ev.start == time(20)


def test_german_date_format():
    assert one("## 05.10.2026\n- 10:00 X").date == date(2026, 10, 5)


def test_plain_date_line_sets_day():
    assert one("Monday, 2026-10-05:\n- 10:00 X").date == date(2026, 10, 5)


def test_midnight_crossing():
    ev = one("## 2026-10-09\n- 22:00-01:00 Concert")
    assert ev.crosses_midnight


def test_notes_indented():
    ev = one("## 2026-10-05\n- 10:00 X\n  line one\n  line two\n\n")
    assert ev.notes == "line one\nline two"


def test_title_with_colon_and_escaped_pipe():
    ev = one("## 2026-10-05\n- 10:00 Workshop: A \\| B | tag: t")
    assert ev.title == "Workshop: A | B" and ev.tag == "t"


def test_repeat():
    assert parse_repeat("weekly") == Repeat("weekly")
    assert parse_repeat("every 2 weeks until 2026-12-31") == Repeat("weekly", 2, date(2026, 12, 31))
    assert parse_repeat("daily 5 times") == Repeat("daily", 1, None, 5)
    assert parse_repeat("sometimes") is None


def test_bad_lines_warn_but_do_not_crash():
    r = parse_text("## 2026-10-05\n- 10:00 Good\nrandom prose here\n- 10:00 X | bogus: 1\n- 99:00 Bad\n- 10:00 Y | repeat: never\n")
    titles = [e.title for e in r.events]
    assert "Good" in titles and "X" in titles and "Y" in titles
    assert len(r.warnings) == 4  # prose, unknown field, invalid time, bad repeat


def test_event_without_date_warns():
    r = parse_text("- 10:00 Floating")
    assert not r.events and "no day" in r.warnings[0]


def test_code_fence_is_transparent():
    r = parse_text("```markdown\n## 2026-10-05\n- 10:00 X\n```\n")
    assert len(r.events) == 1 and not r.warnings


def test_weekday_heading_makes_undated_entries():
    r = parse_text("## Monday\n- 07:00-08:00 Gym\n## Every Friday\n- all day Pizza\n")
    assert not r.warnings
    assert [(e.title, e.date, e.weekday) for e in r.events] == [("Gym", None, 0), ("Pizza", None, 4)]


def test_inline_weekday_and_german_names():
    r = parse_text("- Friday 18:00 Pizza\n## Montag\n- 09:00 Arbeit\nSonntag:\n- 10:00 Lauf\n")
    assert not r.warnings
    assert [(e.title, e.weekday) for e in r.events] == [("Pizza", 4), ("Arbeit", 0), ("Lauf", 6)]


def test_weekday_word_in_title_is_not_a_day():
    ev = one("## 05.10.2026\n- Monday meeting prep")
    assert ev.date == date(2026, 10, 5) and ev.title == "Monday meeting prep"


def test_dated_heading_overrides_weekday_heading():
    r = parse_text("## Monday\n- 10:00 A\n## Tuesday, 06.10.2026\n- 10:00 B\n## Friday\n- 10:00 C\n")
    assert [(e.title, e.date, e.weekday) for e in r.events] == [
        ("A", None, 0), ("B", date(2026, 10, 6), None), ("C", None, 4)]


def test_wrong_weekday_for_date_warns():
    r = parse_text("## Tuesday, 05.10.2026\n- 10:00 X")
    assert r.events[0].date == date(2026, 10, 5)
    assert "does not match" in r.warnings[0]


def test_repeat_on_undated_entry_is_ignored():
    r = parse_text("## Monday\n- 10:00 X | repeat: weekly")
    assert r.events[0].repeat is None and "repeat ignored" in r.warnings[0]
