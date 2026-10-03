# Calendar Visualizer

A small Windows desktop program that turns plain `.md` / `.txt` event lists into a week calendar.

- **Import** reads a `.md`/`.txt` file and replaces the calendar with its events.
- **Add** reads a file and merges its events into the current calendar. Exact duplicates are skipped.
- **Export .md** saves the calendar back to the same readable syntax, so you can re-import it later.
- **Export Image** saves a high-resolution PNG/JPEG of the week view: the current week, or every week that has events. Scale 2×–6× gives images up to 8400 px wide.
- **[`AI_SYNTAX_GUIDE.md`](AI_SYNTAX_GUIDE.md)** is a file you hand to your AI agent so it can write calendar files for you. The exe also contains it: Help → *Save AI syntax guide*.

The calendar autosaves (to `%APPDATA%\CalendarVisualizer\calendar.md`) and is restored when you start the program.

## The syntax at a glance

```markdown
# Calendar: Autumn Plans

## Monday, 2026-10-05
- 09:00-10:30 Team meeting | at: Room 4 | tag: work
  Bring the Q3 slides.
- 12:30 (45m) Lunch with Anna | tag: friends
- 18:00-19:00 Gym | tag: sport | repeat: weekly until 2026-12-31

## Tuesday, 2026-10-06
- all day Mom's birthday | color: pink
- 14:00 Dentist

- 2026-10-10 20:00-23:00 Concert | at: City Hall
```

- A `## …YYYY-MM-DD…` heading starts a day. Each `- ` line under it is one event.
- Times can be `09:00-10:30`, `14:00` (lasts 1 hour), `14:00 (45m)` or `all day`. `22:00-01:00` runs past midnight.
- Optional fields go after ` | `: `at:`, `tag:` (same tag means same colour), `color:`, `repeat:`, `notes:`.
- Lines indented under an event become its notes.
- If the program can't understand a line, it skips it and lists it in an import report. It never stops the import.

The full specification is in [`AI_SYNTAX_GUIDE.md`](AI_SYNTAX_GUIDE.md), and [`examples/sample.md`](examples/sample.md) is a complete example.

## Using the program

| Action | How |
|---|---|
| Previous / next week | ◀ ▶ buttons, ← → keys or mouse wheel |
| Event details / delete | click an event |
| Jump to a date | *Go to date…* |
| Shortcuts | Ctrl+O import, Ctrl+A add, Ctrl+S export .md, Ctrl+E export image |

## Getting the .exe

**From GitHub Actions:** every push runs the *Build Windows exe* workflow. Open the run and download the
`CalendarVisualizer-windows` artifact. If you push a tag such as `v1.0.0`, the exe is also attached to a GitHub Release.

**Build it yourself on Windows** (needs Python 3.10+ from python.org):

```bat
build.bat
```

The result is `dist\CalendarVisualizer.exe`, a single file with no installation needed.

## Running from source

```bash
pip install -r requirements-dev.txt
python run_calviz.py          # start the GUI
python -m pytest -q           # run the tests
python run_calviz.py --selftest
```

## Project layout

| Path | Purpose |
|---|---|
| `calviz/parser.py` | text → events (forgiving, reports warnings) |
| `calviz/writer.py` | events → Markdown (round-trips through the parser) |
| `calviz/model.py` | `Event`, `Repeat`, `Calendar` (merge, recurrence expansion) |
| `calviz/render.py` | Pillow week-view renderer, used both on screen and for exports |
| `calviz/gui.py` | tkinter window |
| `calviz.spec` | PyInstaller recipe |

Fonts: DejaVu Sans (see `calviz/assets/DejaVu-LICENSE.txt`).
