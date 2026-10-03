# Calendar Visualizer — Event File Syntax (guide for AI agents)

You are writing a plain-text file (`.md` or `.txt`) that the **Calendar Visualizer**
program imports and shows as a week calendar. Follow this guide exactly. Output only
the calendar file content: no explanations, and no tables.

## 1. File structure

```markdown
# Calendar: <calendar title>

## <Weekday>, <YYYY-MM-DD>
- <event line>
- <event line>
  <optional note line, indented by 2 spaces>

## <Weekday>, <YYYY-MM-DD>
- <event line>
```

- The first line, `# Calendar: <title>`, is optional and sets the calendar's name.
- A **day heading** is any `##` heading that contains a date in `YYYY-MM-DD` format.
  Every event line below it belongs to that day until the next day heading.
  The weekday name is optional and only there to help people read it. The date decides the day.
- Write each day heading once, and list the days in chronological order.
- Leave a blank line between day sections.

## 2. Event lines

Every event is **one line that starts with `- `** (dash + space):

```
- <time> <Title> | <key>: <value> | <key>: <value>
```

### Time (pick one)

| Form | Example | Meaning |
|---|---|---|
| `HH:MM-HH:MM` | `- 09:00-10:30 Team meeting` | start and end (24-hour clock) |
| `HH:MM` | `- 14:00 Dentist` | start only, lasts 1 hour |
| `HH:MM (duration)` | `- 14:00 (45m) Call with Anna` | start + duration: `30m`, `2h`, `1h30m`, `1.5h` |
| `all day` | `- all day Mom's birthday` | all-day event |

- Always use the **24-hour clock with two-digit minutes** (`09:00`, not `9`). The program
  also accepts `9am`/`2:30pm`, but 24-hour times are preferred.
- If the end time is earlier than the start, the event ends the next day:
  `- 22:00-01:00 Night shift` runs from 22:00 until 01:00 the next morning.
- A line with no time is treated as an all-day event. Still write `all day` to make this explicit.

### Optional fields

Append fields after the title, each one separated by ` | `:

| Field | Example | Meaning |
|---|---|---|
| `at:` | `\| at: Room 4` | location |
| `tag:` | `\| tag: work` | category. All events with the same tag share a colour. |
| `color:` | `\| color: red` or `\| color: #22c55e` | explicit colour (CSS colour name or hex). Overrides the tag colour. |
| `repeat:` | `\| repeat: weekly until 2026-12-31` | recurrence (see below) |
| `notes:` | `\| notes: bring laptop` | short note |

- Use short, lowercase, consistent tags (`work`, `family`, `sport`, `school`, …).
- A title must not contain a `|` character. If it needs one, write `\|`.

### Notes (longer descriptions)

Lines indented by two spaces directly under an event become that event's notes:

```
- 13:00-17:00 Workshop | at: Innovation Lab
  Bring laptop and notebook.
  Ask about the follow-up session.
```

### Repeating events

`repeat:` values:

- `daily`, `weekly`, `monthly`, `yearly`
- `every N days` / `every N weeks` / `every N months` / `every N years`
- Optionally followed by an end: `until YYYY-MM-DD` **or** `N times`

Examples: `repeat: weekly`, `repeat: every 2 weeks until 2026-12-31`, `repeat: daily 5 times`.
Put a repeating event under the day heading of its **first** occurrence.
A repeat without an end continues indefinitely.

Multi-day all-day events (vacations, trips): use one all-day event with `repeat: daily N times`,
e.g. `- all day Vacation in Italy | repeat: daily 7 times`.

### Events without a day heading

An event line may also begin with its own date. It then needs no heading:

```
- 2026-10-10 20:00-23:00 Concert | at: City Hall
- 2026-10-11 all day Hiking trip
```

## 3. Rules checklist

1. Dates are always `YYYY-MM-DD`.
2. Times are always `HH:MM` (24-hour).
3. Write one event per line, and start each one with `- `.
4. Fields come after the title, separated by ` | `, written as `key: value`.
5. Don't use tables, bold or italic text, or links on event lines.
6. Don't add commentary lines between events. The program reports unknown lines as warnings and skips them.
7. If no time is known, use `all day`.

## 4. Complete example

```markdown
# Calendar: Autumn Plans

## Monday, 2026-10-05
- 09:00-10:30 Team meeting | at: Room 4 | tag: work
  Bring the Q3 slides.
- 12:30 (45m) Lunch with Anna | at: Café Central | tag: friends
- 18:00-19:00 Gym | tag: sport | repeat: weekly until 2026-12-31

## Tuesday, 2026-10-06
- all day Mom's birthday | tag: family | color: pink
- 14:00 Dentist | at: Dr. Weber, Main St. 12 | color: red

## Friday, 2026-10-09
- 15:00-16:00 Weekly review | tag: work | repeat: weekly
- 22:00-01:00 Late concert | at: City Hall | tag: friends
```

## 5. Example: a study plan

```markdown
# Calendar: Exam Preparation

## Monday, 2026-11-02
- 08:00-10:00 Math: linear algebra | tag: math | repeat: every 2 days 6 times
- 10:30-12:00 History reading | tag: history
- all day Library open late | tag: info

## Wednesday, 2026-11-11
- 09:00-11:00 Math exam | at: Hall B | tag: exam | color: red
  Calculator allowed, no notes.
```
