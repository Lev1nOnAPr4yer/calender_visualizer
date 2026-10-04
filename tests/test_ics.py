from datetime import date, datetime

import icalendar

from calviz.ics import first_weekly_date, to_ics
from calviz.parser import parse_text

TEXT = """# Calendar: Test
## Monday
- 07:00-08:00 Gym, tag: sport
## Friday
- 22:00-01:00 Night out
## Sunday
- all day Rest day
## Tuesday, 06.10.2026
- all day Mom's birthday, color: pink
- 14:00 Dentist, at: Dr. Weber, Main St. 12
  Bring the card; and the form.
## Friday, 09.10.2026
- 15:00-16:00 Review, repeat: every 2 weeks until 18.12.2026
- 08:00 Standup, repeat: daily 5 times
"""

EVENTS = parse_text(TEXT).events
START = date(2026, 10, 7)  # a Wednesday


def parsed(events=EVENTS, **kw):
    text = to_ics(events, "Test", weekly_start=START, **kw)
    cal = icalendar.Calendar.from_ical(text)
    return text, {str(v["SUMMARY"]): v for v in cal.walk("VEVENT")}


def test_valid_calendar_with_all_entries():
    text, ev = parsed()
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert len(ev) == len(EVENTS) == 7


def test_weekly_entries_repeat_from_start_date():
    _, ev = parsed()
    gym = ev["Gym"]
    assert gym["DTSTART"].dt == datetime(2026, 10, 12, 7, 0)  # first Monday on/after Wed 07.10.
    assert gym["RRULE"]["FREQ"] == ["WEEKLY"] and gym["RRULE"]["BYDAY"] == ["MO"]
    assert "UNTIL" not in gym["RRULE"]
    assert first_weekly_date(2, START) == START


def test_weekly_until():
    _, ev = parsed(weekly_until=date(2026, 12, 31))
    assert ev["Gym"]["RRULE"]["UNTIL"] == [datetime(2026, 12, 31, 23, 59, 59)]
    assert ev["Rest day"]["RRULE"]["UNTIL"] == [date(2026, 12, 31)]


def test_midnight_and_all_day():
    _, ev = parsed()
    night = ev["Night out"]
    assert night["DTSTART"].dt == datetime(2026, 10, 9, 22, 0)
    assert night["DTEND"].dt == datetime(2026, 10, 10, 1, 0)
    bday = ev["Mom's birthday"]
    assert bday["DTSTART"].dt == date(2026, 10, 6) and bday["DTEND"].dt == date(2026, 10, 7)
    assert "RRULE" not in bday


def test_dated_repeat_rules():
    _, ev = parsed()
    review = ev["Review"]["RRULE"]
    assert review["FREQ"] == ["WEEKLY"] and review["INTERVAL"] == [2]
    assert review["UNTIL"] == [datetime(2026, 12, 18, 23, 59, 59)]
    assert ev["Standup"]["RRULE"]["COUNT"] == [5]


def test_text_fields_and_escaping():
    text, ev = parsed()
    dentist = ev["Dentist"]
    assert str(dentist["LOCATION"]) == "Dr. Weber, Main St. 12"
    assert str(dentist["DESCRIPTION"]) == "Bring the card; and the form."
    assert "LOCATION:Dr. Weber\\, Main St. 12" in text
    assert ev["Gym"]["CATEGORIES"].cats == ["sport"]


def test_line_length_and_crlf():
    long = parse_text("## Monday\n- 10:00 " + "Very long title with ümlauts " * 10).events
    text = to_ics(long, "T", weekly_start=START)
    lines = text.split("\r\n")
    assert all(len(line.encode("utf-8")) <= 75 for line in lines)
    assert "\n" not in text.replace("\r\n", "")
    assert str(icalendar.Calendar.from_ical(text).walk("VEVENT")[0]["SUMMARY"]).startswith("Very long title")


def test_uids_stable_and_unique_and_subset():
    t1, _ = parsed()
    t2, _ = parsed()
    uids = lambda t: [l for l in t.split("\r\n") if l.startswith("UID:")]
    assert uids(t1) == uids(t2) and len(set(uids(t1))) == 7
    _, ev = parsed(EVENTS[:2])
    assert set(ev) == {"Gym", "Night out"}
