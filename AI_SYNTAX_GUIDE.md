# Calendar Visualizer: Event File Syntax (guide for AI agents)

You are writing a plain-text file (`.md` or `.txt`) that the **Calendar Visualizer** program imports and
shows as a week view (Monday to Sunday, with hours). Follow this guide exactly. Output only the
calendar file content: no explanations, and no tables.

## 1. Two kinds of entries

| Kind | Day heading | Shown |
|---|---|---|
| **Weekly entry** (undated) | `## Monday` | on that weekday, in **every** week |
| **Dated entry** | `## Monday, 05.10.2026` | only on that date |

- If a file only has weekly entries, the program shows a plain weekly planner: weekday names only, with no dates.
- When at least one dated entry exists, the program shows real weeks you can click through.
  Weekly entries then appear in every one of those weeks.
- Use weekly entries for routines (work hours, gym, classes). Use dated entries for one-off appointments.
- You can mix both kinds in one file. Put the weekly entries first.

## 2. File structure

```markdown
# Calendar: <calendar title>

## Monday
- <event line>
- <event line>

## Friday
- <event line>

## Wednesday, 07.10.2026
- <event line>
  <optional note line, indented by 2 spaces>
```

- The first line, `# Calendar: <title>`, is optional and sets the calendar's name.
- A **day heading** is a `##` heading:
  - `## Monday` … `## Sunday` → a weekly entry.
  - `## Monday, 05.10.2026` → a dated entry. **Dates are always DD.MM.YYYY.** The date decides the day.
    The weekday name is only there to help people read it, but it must match the date.
- Every event line below a heading belongs to that day until the next heading.
- Write each heading once, list the weekly days in order Monday → Sunday, and list the dated days chronologically.
- Leave a blank line between sections.

## 3. Event lines

Every event is **one line that starts with `- `** (dash + space):

```
- <time> <Title> | <key>: <value> | <key>: <value>
```

### Time (pick one, always 24-hour clock)

| Form | Example | Meaning |
|---|---|---|
| `HH:MM-HH:MM` | `- 09:00-10:30 Team meeting` | start and end |
| `HH:MM` | `- 14:00 Dentist` | start only, lasts 1 hour |
| `HH:MM (duration)` | `- 14:00 (45m) Call with Anna` | start + duration: `30m`, `2h`, `1h30m` |
| `all day` | `- all day Mom's birthday` | all-day entry |

- Always use **two-digit hours and minutes** on the 24-hour clock: `07:00`, `13:30`, `21:15`.
  Never use am/pm.
- If the end time is earlier than the start time, the entry ends the next day:
  `- 22:00-01:00 Night shift` runs from 22:00 until 01:00 the next morning.

### Optional fields

Append fields after the title, each one separated by ` | `:

| Field | Example | Meaning |
|---|---|---|
| `at:` | `\| at: Room 4` | location |
| `tag:` | `\| tag: work` | category. All entries with the same tag share a colour. |
| `color:` | `\| color: red` or `\| color: #22c55e` | explicit colour (CSS colour name or hex). Overrides the tag colour. |
| `repeat:` | `\| repeat: weekly until 31.12.2026` | recurrence, **dated entries only** (see below) |
| `notes:` | `\| notes: bring laptop` | short note |

- Use short, lowercase, consistent tags (`work`, `family`, `sport`, `school`, …).
- A title must not contain a `|` character. If it needs one, write `\|`.

### Notes (longer descriptions)

Lines indented by two spaces directly under an entry become that entry's notes:

```
- 13:00-17:00 Workshop | at: Innovation Lab
  Bring laptop and notebook.
  Ask about the follow-up session.
```

### Repeating dated entries

Weekly entries already repeat every week, so never give them `repeat:`.
For dated entries, `repeat:` takes:

- `daily`, `weekly`, `monthly`, `yearly`
- `every N days` / `every N weeks` / `every N months` / `every N years`
- Optionally followed by an end: `until DD.MM.YYYY` **or** `N times`

Examples: `repeat: every 2 weeks until 31.12.2026`, `repeat: daily 5 times`.
Put the entry under the heading of its **first** occurrence.

Multi-day events (vacations, trips): use one all-day dated entry with `repeat: daily N times`,
e.g. `- all day Vacation in Italy | repeat: daily 7 times`.

### Entries without a heading

A line may also begin with its own day. It then needs no heading:

```
- Friday 18:00 Pizza night
- 10.10.2026 20:00-23:00 Concert | at: City Hall
```

## 4. Rules checklist

1. Dates are always `DD.MM.YYYY` (e.g. `05.10.2026`).
2. Times are always `HH:MM`, 24-hour (e.g. `07:00`, `19:30`).
3. Weekly routines go under `## Monday` … `## Sunday`. One-off appointments go under `## Weekday, DD.MM.YYYY`.
4. Write one entry per line, and start each one with `- `.
5. Fields come after the title, separated by ` | `, written as `key: value`.
6. Don't use tables, bold or italic text, or links on entry lines.
7. Don't add commentary lines between entries. The program reports unknown lines as warnings and skips them.
8. If no time is known, use `all day`.

## 5. Example: weekly planner (no dates)

```markdown
# Calendar: My Week

## Monday
- 07:00-08:00 Gym | tag: sport
- 09:00-17:00 Work | at: Office | tag: work

## Wednesday
- 19:00-20:30 Spanish class | at: Community college | tag: study

## Friday
- 22:00-01:00 Night out | tag: friends

## Sunday
- 18:00 Plan next week | tag: home
```

## 6. Example: weekly routine plus dated appointments

```markdown
# Calendar: Autumn Plans

## Monday
- 09:00-17:00 Work | at: Office | tag: work

## Thursday
- 18:00-19:00 Gym | tag: sport

## Tuesday, 06.10.2026
- all day Mom's birthday | tag: family | color: pink
- 14:00 Dentist | at: Dr. Weber, Main St. 12 | color: red

## Friday, 09.10.2026
- 15:00-16:00 Project review | tag: work | repeat: every 2 weeks until 18.12.2026
  Prepare the status slides.
```
