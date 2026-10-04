from calviz import storage
from calviz.model import Calendar
from calviz.parser import parse_text


def test_nothing_written_until_first_save_and_remove_cleans_up(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    folder = tmp_path / "CalendarVisualizer"

    assert storage.load().events == []
    assert not folder.exists()  # starting the program leaves no trace

    cal = Calendar("T", parse_text("## 2026-10-05\n- 10:00 X").events)
    storage.save(cal)
    assert storage.load().events == cal.events
    assert [p.name for p in folder.iterdir()] == ["calendar.md"]

    storage.remove_all_data()
    assert not folder.exists()
    assert list(tmp_path.iterdir()) == []
