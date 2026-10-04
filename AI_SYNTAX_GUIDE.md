# Calendar Visualizer: Event File Syntax (guide for AI agents)

You are writing a plain-text file (`.md` or `.txt`) that the **Calendar Visualizer** program imports and
shows as a week view (Monday to Sunday, with hours). Follow this guide exactly. Output only the
calendar file content: no explanations, and no tables.

## 1. Two kinds of entries

| Kind | Day written as | Shown |
|---|---|---|
| **Weekly entry** (undated) | a weekday: `Monday`, `Mo`, `Montag`, … | on that weekday, in **every** week |
| **Dated entry** | a date: `05.10.2026` | only on that date |

- If a file only has weekly entries, the program shows a plain weekly planner: weekday names only, with no dates.
- When at least one dated entry exists, the program shows real weeks you can click through.
  Weekly entries then appear in every one of those weeks.
- Use weekly entries for routines (work hours, gym, classes). Use dated entries for one-off appointments.
- You can mix both kinds in one file. Put the weekly entries first.

## 2. Day names

Every weekday can be written in English or German, as a full name or an abbreviation (any capitalisation):

| Day | English | German |
|---|---|---|
| Monday | `Monday`, `Mon` | `Montag`, `Mo` |
| Tuesday | `Tuesday`, `Tue` | `Dienstag`, `Di` |
| Wednesday | `Wednesday`, `Wed` | `Mittwoch`, `Mi` |
| Thursday | `Thursday`, `Thu` | `Donnerstag`, `Do` |
| Friday | `Friday`, `Fri` | `Freitag`, `Fr` |
| Saturday | `Saturday`, `Sat` | `Samstag`, `Sa` |
| Sunday | `Sunday`, `Sun` | `Sonntag`, `So` |

Dates are always written **DD.MM.YYYY** (e.g. `05.10.2026`).

## 3. Two ways to write entries

### a) One entry per line (day in the line)

```
<day>, <time>, <title>, <key>: <value>, <key>: <value>
```

```
Mo, 08:00-09:00, Schoolwork, tag: uni
Fr, 18:00-20:00, Pizza night, at: Luigi's, tag: friends
Sa, all day, Farmers market
05.10.2026, 14:00, Dentist, at: Dr. Weber
```

The parts are separated by commas, and spaces after the commas are optional (`Mo,8-9,Schoolwork,tag:uni` also works).
The time is optional; leave it out for an all-day entry.

### b) Many entries under a day heading

```markdown
## Monday
- 07:00-08:00 Gym, tag: sport
- 09:00-17:00 Work, at: Office, tag: work

## Wednesday, 07.10.2026
- 10:00 Dentist, at: Dr. Weber
  Bring the insurance card.
```

- `## <weekday>` starts a block of weekly entries. `## <weekday>, DD.MM.YYYY` starts a block of dated entries.
  The weekday in a dated heading is only there to help people read it, but it must match the date.
- Every `- ` line below a heading belongs to that day until the next heading.
- Write each heading once, list the weekly days in order Monday → Sunday, and list the dated days chronologically.

Both styles can be mixed in one file.

## 4. Time

| Form | Example | Meaning |
|---|---|---|
| `HH:MM-HH:MM` | `09:00-10:30` | start and end |
| `HH:MM` | `14:00` | start only, lasts 1 hour |
| `HH:MM (duration)` | `14:00 (45m)` | start + duration: `30m`, `2h`, `1h30m` |
| `all day` | `all day` | all-day entry |

- Use the **24-hour clock**, and never use am/pm.
- Prefer two-digit `HH:MM` (`07:00`, `13:30`). Short forms like `8-9` or `8:30-10` are also understood in
  the one-line style, but `HH:MM` is clearer.
- If the end time is earlier than the start time, the entry ends the next day:
  `22:00-01:00` runs from 22:00 until 01:00 the next morning.

## 5. Optional fields

Add fields after the title, separated by commas, written as `key: value`:

| Field | Example | Meaning |
|---|---|---|
| `at:` | `at: Room 4` | location |
| `tag:` | `tag: work` | category. All entries with the same tag share a colour. |
| `color:` | `color: red` or `color: #22c55e` | explicit colour (CSS colour name or hex). Overrides the tag colour. |
| `repeat:` | `repeat: weekly until 31.12.2026` | recurrence, **dated entries only** (see below) |
| `notes:` | `notes: bring laptop` | short note |

- Use short, lowercase, consistent tags (`work`, `uni`, `family`, `sport`, …).
- A comma that isn't followed by a `key:` stays part of the text. So `Lunch, Anna & Tom` is one title, and
  `at: Dr. Weber, Main St. 12` is one location.

### Notes (longer descriptions)

Lines indented by two spaces directly under an entry become that entry's notes:

```
- 13:00-17:00 Workshop, at: Innovation Lab
  Bring laptop and notebook.
```

### Repeating dated entries

Weekly entries already repeat every week, so never give them `repeat:`.
For dated entries, `repeat:` takes:

- `daily`, `weekly`, `monthly`, `yearly`
- `every N days` / `every N weeks` / `every N months` / `every N years`
- Optionally followed by an end: `until DD.MM.YYYY` **or** `N times`

Examples: `repeat: every 2 weeks until 31.12.2026`, `repeat: daily 5 times`.
Put the entry on the date of its **first** occurrence.

Multi-day events (vacations, trips): use one all-day dated entry with `repeat: daily N times`,
e.g. `01.08.2026, all day, Vacation in Italy, repeat: daily 7 times`.

## 6. Rules checklist

1. Dates are always `DD.MM.YYYY`.
2. Times use the 24-hour clock, preferably `HH:MM`.
3. Weekly routines get a weekday (no date). One-off appointments get a date.
4. Write one entry per line: either `day, time, title, fields` or `- time title, fields` under a heading.
5. Fields are `key: value` and separated by commas.
6. Don't use tables, bold or italic text, or links on entry lines.
7. Don't add commentary lines between entries. The program reports unknown lines as warnings and skips them.
8. If no time is known, leave the time out or write `all day`.

## 7. Example: weekly planner (no dates)

```markdown
# Calendar: My Week

## Monday
- 07:00-08:00 Gym, tag: sport
- 09:00-17:00 Work, at: Office, tag: work

## Friday
- 22:00-01:00 Night out, tag: friends

Mi, 19:00-20:30, Spanish class, at: Community college, tag: study
So, 18:00, Plan next week, tag: home
```

## 8. Example: weekly routine plus dated appointments

```markdown
# Calendar: Autumn Plans

## Monday
- 09:00-17:00 Work, at: Office, tag: work

Do, 18:00-19:00, Gym, tag: sport

## Tuesday, 06.10.2026
- all day Mom's birthday, tag: family, color: pink
- 14:00 Dentist, at: Dr. Weber, Main St. 12, color: red

## Friday, 09.10.2026
- 15:00-16:00 Project review, tag: work, repeat: every 2 weeks until 18.12.2026
  Prepare the status slides.
```
