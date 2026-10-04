# Calendar Visualizer

A small Windows desktop program that turns plain `.md` / `.txt` event lists into a week calendar.

## Download

**[⬇ Download the latest release](https://github.com/zd82pxt4kr-alt/calender_visualizer/releases/latest)**

1. Under *Assets*, download **`CalendarVisualizer.exe`**. It's a single file and needs no installation.
2. Double-click it. The first time, Windows may say *"Windows protected your PC"* because the program isn't
   code-signed. Click **More info → Run anyway**.
3. Also download **`AI_SYNTAX_GUIDE.md`** if you want an AI agent to write calendar files for you.

## Removing it completely

The program has no installer and writes nothing to the registry. It only ever creates two things:

| What | Where |
|---|---|
| The program | wherever you saved `CalendarVisualizer.exe` |
| Your saved calendar | `%APPDATA%\CalendarVisualizer\` (created the first time you import or add something) |

To remove everything:

1. In the program, click **Help → Remove all my data and quit…**. This deletes the `%APPDATA%\CalendarVisualizer` folder.
2. Delete `CalendarVisualizer.exe`.

That's all. If you've already deleted the exe, paste `%APPDATA%` into the Explorer address bar and delete the `CalendarVisualizer` folder yourself.
Any `.md` or image files you exported stay wherever you saved them.

## Features

- **Import** reads a `.md`/`.txt` file and replaces the calendar with its events.
- **Add** reads a file and merges its events into the current calendar. Exact duplicates are skipped.
- **Export .md** saves the calendar back to the same readable syntax, so you can re-import it later.
- **Export Image** saves a high-resolution PNG/JPEG of the week view: the weekly planner, the current week, or every week that has dated entries. Scale 2×–6× gives images up to 8400 px wide.
- **[`AI_SYNTAX_GUIDE.md`](AI_SYNTAX_GUIDE.md)** is a file you hand to your AI agent so it can write calendar files for you. The exe also contains it: Help → *Save AI syntax guide*.

The calendar autosaves (to `%APPDATA%\CalendarVisualizer\calendar.md`) and is restored when you start the program.

## The syntax at a glance

```markdown
# Calendar: My Week

## Monday
- 07:00-08:00 Gym | tag: sport
- 09:00-17:00 Work | at: Office | tag: work

## Friday
- 22:00-01:00 Night out | tag: friends

## Tuesday, 06.10.2026
- all day Mom's birthday | color: pink
- 14:00 (45m) Dentist
  Bring the insurance card.
```

- `## Monday` … `## Sunday` hold **weekly entries**. They have no date and appear in every week.
- `## Tuesday, 06.10.2026` holds **dated entries**. Dates are DD.MM.YYYY.
- Each `- ` line is one entry. Times use the 24-hour clock: `09:00-10:30`, `14:00` (lasts 1 hour),
  `14:00 (45m)` or `all day`. `22:00-01:00` runs past midnight.
- Optional fields go after ` | `: `at:`, `tag:` (same tag means same colour), `color:`, `repeat:` (dated entries only), `notes:`.
- Lines indented under an entry become its notes.
- If the program can't understand a line, it skips it and lists it in an import report. It never stops the import.

**Weekly planner vs. dated weeks:** as long as there are only weekly entries, the program shows a single
Monday-to-Sunday planner with no dates. As soon as a dated entry is imported or added, it switches to real
weeks you can click through with ◀ ▶, and the weekly entries show up in every week.

The full specification is in [`AI_SYNTAX_GUIDE.md`](AI_SYNTAX_GUIDE.md). Examples:
[`examples/sample.md`](examples/sample.md) (weekly planner) and
[`examples/sample-dated.md`](examples/sample-dated.md) (dated).

## Using the program

| Action | How |
|---|---|
| Previous / next week | ◀ ▶ buttons, ← → keys or mouse wheel (once there are dated entries) |
| Event details / delete | click an event |
| Jump to a date | *Go to date…* (DD.MM.YYYY) |
| Shortcuts | Ctrl+O import, Ctrl+A add, Ctrl+S export .md, Ctrl+E export image |

## Publishing a new version

GitHub builds the exe for you. You never have to build anything on your PC.

1. On github.com, edit `calviz/__init__.py` and raise the version, e.g. `__version__ = "1.1.0"`.
2. Commit the change to the default branch.
3. The *Build Windows exe* workflow tests and builds the exe, then publishes Release **v1.1.0** with the exe attached.

A push that doesn't change the version still runs the tests and the build, but doesn't touch the existing release.

## For developers

```bash
pip install -r requirements-dev.txt
python run_calviz.py          # start the GUI
python -m pytest -q           # run the tests
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
