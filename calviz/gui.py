"""Tkinter desktop window: week view plus Import / Add / Export actions."""

from __future__ import annotations

import os
import re
import shutil
import tkinter as tk
from datetime import date, timedelta
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import ImageTk

from . import __version__, storage
from . import viewrange as vr
from .ics import to_ics
from .model import PLANNER_WEEK, WEEKDAYS, Calendar, Event, fmt_date, today, week_start
from .parser import ParseResult, parse_date, parse_entry, parse_file
from .render import RenderResult, export_week, render_week, tag_colors
from .resources import AI_GUIDE, ICON_PNG
from .writer import to_markdown

FILETYPES_IN = [("Calendar text", "*.md *.txt"), ("Markdown", "*.md"), ("Text", "*.txt"), ("All files", "*.*")]


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Calendar Visualizer")
        self.geometry("1280x820")
        self.minsize(800, 500)
        try:
            self._icon = tk.PhotoImage(file=str(ICON_PNG))
            self.iconphoto(True, self._icon)
        except tk.TclError:
            pass

        try:
            self.cal = storage.load()
        except Exception as exc:  # a broken autosave must never stop the program from starting
            messagebox.showwarning("Calendar Visualizer", f"Could not load the saved calendar:\n{exc}")
            self.cal = Calendar()
        self.week = week_start(today())
        if self.cal.is_dated():  # open on the current week, or the next week that has dated entries
            weeks = self.cal.weeks_with_events()
            upcoming = [w for w in weeks if w >= self.week]
            if self.week not in weeks:
                self.week = upcoming[0] if upcoming else weeks[-1]
        self.ui_scale = max(1.0, self.winfo_fpixels("1i") / 96)
        self._render: RenderResult | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._redraw_job: str | None = None
        # "Weekly routine only": hide dated entries everywhere (view + exports) without deleting them.
        self.routine_only = tk.BooleanVar(value=False)
        # Visible hours (display minutes, 01:00 -> 01:00 next day). Grows when entries are added, never shrinks
        # by itself; changed by the range bar and the mouse wheel; remembered in view.json.
        self.view = storage.load_view() or vr.default_view(self.cal.events)
        self._save_view_job: str | None = None
        self._bar_drag: tuple[str, float] | None = None
        # Wheel input is collected and applied once per idle cycle (smooth, no backlog).
        self._wheel = {"zoom": 0.0, "pan": 0.0, "week": 0.0, "y": 0.0}
        self._wheel_job: str | None = None
        # While zooming/scrolling/dragging, the notes row keeps its height so the grid doesn't jump.
        self._interacting = False
        self._hold_rows = 0
        self._interact_job: str | None = None

        self._build_menu()
        self._build_toolbar()
        self.status = ttk.Label(self, anchor="w", padding=(8, 3))
        self.status.pack(fill="x", side="bottom")
        area = tk.Frame(self, background="white")
        area.pack(fill="both", expand=True)
        self.bar = tk.Canvas(area, width=78, background="white", highlightthickness=0, cursor="sb_v_double_arrow")
        self.bar.pack(side="right", fill="y")
        self.canvas = tk.Canvas(area, background="white", highlightthickness=0, cursor="arrow")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar.bind("<Button-1>", self.on_bar_press)
        self.bar.bind("<B1-Motion>", self.on_bar_drag)
        self.bar.bind("<ButtonRelease-1>", self.on_bar_release)
        self.bar.bind("<Double-Button-1>", lambda e: self.fit_to_entries())
        self.bar.bind("<MouseWheel>", lambda e: self.on_wheel(e, e.delta / 120, force_pan=True))
        self.bar.bind("<Button-4>", lambda e: self.on_wheel(e, 1, force_pan=True))
        self.bar.bind("<Button-5>", lambda e: self.on_wheel(e, -1, force_pan=True))

        # Redraw continuously while the window is being resized (not only when the drag ends).
        self.canvas.bind("<Configure>", lambda e: self.schedule_redraw())
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Motion>", self.on_motion)
        # Wheel scrolls the hours, Ctrl + wheel zooms around the pointer, Shift + wheel changes the week.
        # Windows reports delta in steps of 120 per notch (smaller for touchpads / smooth mice).
        self.canvas.bind("<MouseWheel>", lambda e: self.on_wheel(e, e.delta / 120))
        self.canvas.bind("<Button-4>", lambda e: self.on_wheel(e, 1))
        self.canvas.bind("<Button-5>", lambda e: self.on_wheel(e, -1))
        # Shortcuts are ignored while typing in the quick-add box (arrows move the cursor there).
        for key, action in [
            ("<Left>", lambda: self.shift_week(-1)),
            ("<Right>", lambda: self.shift_week(1)),
            ("<Control-o>", self.import_file),
            ("<Control-a>", self.add_file),
            ("<Control-s>", self.export_md),
            ("<Control-e>", self.export_image),
            ("<Control-i>", self.export_ics),
        ]:
            self.bind(key, lambda e, a=action: None if e.widget is self.quick else a())
        self.bind("<Control-n>", lambda e: self.focus_quick_add())
        self.bind("<Control-r>", lambda e: (self.routine_only.set(not self.routine_only.get()), self.toggled_routine()))

    # --- layout --------------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        m_file = tk.Menu(menubar, tearoff=False)
        m_file.add_command(label="Import… (replace calendar)", accelerator="Ctrl+O", command=self.import_file)
        m_file.add_command(label="Add events from file…", accelerator="Ctrl+A", command=self.add_file)
        m_file.add_command(label="New entry (type in the box)", accelerator="Ctrl+N", command=self.focus_quick_add)
        m_file.add_separator()
        m_file.add_command(label="Export as .md…", accelerator="Ctrl+S", command=self.export_md)
        m_file.add_command(label="Export as image…", accelerator="Ctrl+E", command=self.export_image)
        m_file.add_command(label="Export as .ics (Thunderbird, Outlook…)…", accelerator="Ctrl+I", command=self.export_ics)
        m_file.add_separator()
        m_file.add_command(label="Rename calendar…", command=self.rename)
        m_file.add_command(label="Clear calendar…", command=self.clear)
        m_file.add_separator()
        m_file.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=m_file)

        m_view = tk.Menu(menubar, tearoff=False)
        m_view.add_command(label="Previous week", accelerator="←", command=lambda: self.shift_week(-1))
        m_view.add_command(label="Next week", accelerator="→", command=lambda: self.shift_week(1))
        m_view.add_command(label="This week", command=self.go_today)
        m_view.add_command(label="Go to date…", command=self.go_to_date)
        m_view.add_command(label="First event", command=self.go_first)
        m_view.add_separator()
        m_view.add_checkbutton(label="Weekly routine only (hide dated entries)", accelerator="Ctrl+R",
                               variable=self.routine_only, command=self.toggled_routine)
        menubar.add_cascade(label="View", menu=m_view)
        self.m_view = m_view

        m_help = tk.Menu(menubar, tearoff=False)
        m_help.add_command(label="Save AI syntax guide (.md)…", command=self.save_guide)
        m_help.add_command(label="Open autosave folder", command=self.open_data_dir)
        m_help.add_command(label="Remove all my data and quit…", command=self.remove_data_and_quit)
        m_help.add_separator()
        m_help.add_command(label="About", command=self.about)
        menubar.add_cascade(label="Help", menu=m_help)
        self.config(menu=menubar)

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self, padding=(6, 6))
        bar.pack(fill="x")
        for text, cmd in [
            ("Import…", self.import_file),
            ("Add file…", self.add_file),
        ]:
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=2)
        export = ttk.Menubutton(bar, text="Export")
        m_export = tk.Menu(export, tearoff=False)
        m_export.add_command(label="Image (.png)…", command=self.export_image)
        m_export.add_command(label="Calendar file (.ics) for Thunderbird, Outlook…", command=self.export_ics)
        m_export.add_command(label="Text (.md)…", command=self.export_md)
        export["menu"] = m_export
        export.pack(side="left", padx=2)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        self.nav_buttons = [
            ttk.Button(bar, text="◀", width=3, command=lambda: self.shift_week(-1)),
            ttk.Button(bar, text="Today", command=self.go_today),
            ttk.Button(bar, text="▶", width=3, command=lambda: self.shift_week(1)),
            ttk.Button(bar, text="Go to date…", command=self.go_to_date),
        ]
        for b in self.nav_buttons:
            b.pack(side="left", padx=2)
        ttk.Checkbutton(bar, text="Weekly routine only", variable=self.routine_only,
                        command=self.toggled_routine).pack(side="left", padx=(8, 2))

        # Quick add: one entry typed as "Mo, 8-9, Schoolwork, tag: Uni"
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(bar, text="Add entry", command=self.quick_add).pack(side="right", padx=2)
        self.quick = tk.Entry(bar, relief="solid", borderwidth=1, highlightthickness=1,
                              highlightbackground="#c4c4c4", highlightcolor="#3b82f6")
        self.quick.pack(side="left", fill="x", expand=True, padx=2, ipady=3)
        self.quick.bind("<Return>", lambda e: self.quick_add())
        self.quick.bind("<KP_Enter>", lambda e: self.quick_add())
        self.quick.bind("<FocusIn>", lambda e: self._quick_placeholder(False))
        self.quick.bind("<FocusOut>", lambda e: self._quick_placeholder(True))
        self.quick.bind("<Key>", lambda e: self._quick_error(False), add="+")
        self._quick_hint = True
        self._quick_placeholder(True)

    # --- drawing -------------------------------------------------------------

    @property
    def dated(self) -> bool:
        """Real weeks are shown only once some entry has a date; before that it is a weekly planner."""
        return self.view_cal.is_dated()

    @property
    def view_cal(self) -> Calendar:
        """What is shown and exported: everything, or only the undated weekly routine."""
        if self.routine_only.get():
            return Calendar(self.cal.title, [e for e in self.cal.events if not e.dated])
        return self.cal

    def toggled_routine(self) -> None:
        self.redraw()
        if self.routine_only.get():
            hidden = sum(1 for e in self.cal.events if e.dated)
            self.status.config(text=f"Weekly routine only: {hidden} dated entr{'ies are' if hidden != 1 else 'y is'} "
                                    "hidden (not deleted). Turn the toggle off to show them again.")

    def schedule_redraw(self) -> None:
        # Coalesce a burst of resize events into one render as soon as Tk is idle.
        # No timer: the view follows the mouse while the window is being dragged.
        if self._redraw_job is None:
            self._redraw_job = self.after_idle(self.redraw)

    def redraw(self) -> None:
        if self._redraw_job is not None:
            self.after_cancel(self._redraw_job)
            self._redraw_job = None
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w < 50 or h < 50:
            return
        s = self.ui_scale
        dated = self.dated
        self._render = render_week(
            self.view_cal, self.week if dated else PLANNER_WEEK, scale=s,
            width=int(w / s), height=int(h / s), show_dates=dated, tags=tag_colors(self.cal), view=self.view,
            min_note_rows=self._hold_rows if self._interacting else 0,
        )
        if self._interacting:
            self._hold_rows = max(self._hold_rows, self._render.note_rows)
        self._photo = ImageTk.PhotoImage(self._render.image)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._photo, anchor="nw")
        self._draw_bar()
        self._update_nav(dated)
        n = len(self.view_cal.events)
        if self.routine_only.get():
            mode = "weekly routine only (dated entries hidden)"
        elif dated:
            mode = "dated calendar"
        else:
            mode = "weekly planner (add entries with a date to switch to real weeks)"
        self.status.config(text=f"{n} entr{'ies' if n != 1 else 'y'}  ·  {mode}  ·  click an entry for details")

    # --- visible hours: range bar + wheel zoom -----------------------------------

    def _bar_geometry(self) -> tuple[float, float]:
        if self._render and self._render.grid[1] > self._render.grid[0]:
            return self._render.grid
        return 10.0, max(20.0, self.bar.winfo_height() - 10.0)

    def _bar_y(self, minutes: float) -> float:
        top, bottom = self._bar_geometry()
        return top + (minutes - vr.DAY_START) / (vr.DAY_END - vr.DAY_START) * (bottom - top)

    def _bar_minutes(self, y: float) -> float:
        top, bottom = self._bar_geometry()
        rel = min(max((y - top) / max(bottom - top, 1), 0.0), 1.0)
        return vr.DAY_START + rel * (vr.DAY_END - vr.DAY_START)

    def _draw_bar(self) -> None:
        b = self.bar
        b.delete("all")
        top, bottom = self._bar_geometry()
        tx0, tx1 = 52, 64  # the track
        b.create_rectangle(tx0, top, tx1, bottom, fill="#f3f4f6", outline="#d1d5db")
        b.create_text((tx0 + tx1) / 2, top - 12, text="Hours", fill="#6b7280", font=("TkDefaultFont", 8))
        for m in range(vr.DAY_START, vr.DAY_END + 1, 180):  # small ticks every 3 hours
            y = self._bar_y(m)
            b.create_line(tx1, y, tx1 + 5, y, fill="#9ca3af")
        y0, y1 = self._bar_y(self.view[0]), self._bar_y(self.view[1])
        b.create_rectangle(tx0, y0, tx1, y1, fill="#bfdbfe", outline="#3b82f6", width=1)
        for y, m in ((y0, self.view[0]), (y1, self.view[1])):
            b.create_rectangle(tx0 - 4, y - 4, tx1 + 4, y + 4, fill="#3b82f6", outline="#1d4ed8")
            b.create_text(tx0 - 8, y, text=vr.label(m), anchor="e", fill="#1f2937", font=("TkDefaultFont", 9, "bold"))

    def on_bar_press(self, e) -> None:
        self._begin_interaction()
        y0, y1 = self._bar_y(self.view[0]), self._bar_y(self.view[1])
        if abs(e.y - y0) <= 8:
            self._bar_drag = ("start", 0.0)
        elif abs(e.y - y1) <= 8:
            self._bar_drag = ("end", 0.0)
        elif y0 < e.y < y1:
            self._bar_drag = ("band", self._bar_minutes(e.y) - self.view[0])
        else:  # clicked outside the band: move the nearest handle there
            self._bar_drag = ("start", 0.0) if e.y < y0 else ("end", 0.0)
            self.on_bar_drag(e)

    def on_bar_drag(self, e) -> None:
        if not self._bar_drag:
            return
        kind, offset = self._bar_drag
        m = self._bar_minutes(e.y)
        if kind == "start":
            new = vr.set_start(self.view, m)
        elif kind == "end":
            new = vr.set_end(self.view, m)
        else:
            new = vr.pan(self.view, round((m - offset - self.view[0]) / 30) * 30)
        self.set_view(new, save=False)

    def on_wheel(self, e, notches: float, force_pan: bool = False) -> None:
        """Collect wheel input; it is applied once per idle cycle in _apply_wheel."""
        if not notches:
            return
        w = self._wheel
        if e.state & 0x0001 and not force_pan:  # Shift: previous / next week
            w["week"] += notches
        elif e.state & 0x0004 and not force_pan:  # Ctrl: zoom around the pointer
            w["zoom"] += notches
            w["y"] = e.y
        else:  # plain wheel: move the visible hours up / down
            w["pan"] += notches
        if self._wheel_job is None:
            self._wheel_job = self.after_idle(self._apply_wheel)

    def _apply_wheel(self) -> None:
        self._wheel_job = None
        w = self._wheel
        weeks = int(w["week"])  # whole notches only (touchpads send many small ones)
        w["week"] -= weeks
        if weeks:
            self.shift_week(-1 if weeks > 0 else 1)
        if not (w["zoom"] or w["pan"]):
            return
        self._begin_interaction(release_after=700)
        view = self.view
        anchor = None
        if w["zoom"]:
            anchor = self._render.minutes_at(w["y"]) if self._render else sum(view) / 2
            new = vr.zoom_notches(view, w["zoom"], anchor, vr.fit_view(self.view_cal.events))
            if new == vr.fit_view(self.view_cal.events):
                anchor = None  # the "all entries" stop moves the view on purpose
            view = new
        if w["pan"]:
            view = vr.pan_notches(view, w["pan"])
        w["zoom"] = w["pan"] = 0.0
        self.set_view(view)
        if anchor is not None:
            self._pin_anchor(anchor, w["y"])

    def _pin_anchor(self, anchor: float, y: float) -> None:
        """If the grid moved (notes row changed height), shift the view so `anchor` stays under the pointer."""
        if not self._render:
            return
        top, bottom = self._render.grid
        if bottom <= top:
            return
        span = self.view[1] - self.view[0]
        rel = min(max((y - top) / (bottom - top), 0.0), 1.0)
        start = anchor - rel * span
        if abs(start - self.view[0]) > 0.25:
            self.set_view((start, start + span))

    def _begin_interaction(self, release_after: int | None = None) -> None:
        self._interacting = True
        if self._interact_job:
            self.after_cancel(self._interact_job)
            self._interact_job = None
        if release_after:
            self._interact_job = self.after(release_after, self._end_interaction)

    def _end_interaction(self) -> None:
        self._interact_job = None
        self._interacting = False
        self._hold_rows = 0
        y = self._wheel["y"]
        anchor = self._render.minutes_at(y) if self._render else None
        self.redraw()  # let the notes row settle to its natural height ...
        if anchor is not None and self._bar_drag is None:
            self._pin_anchor(anchor, y)  # ... without moving what is under the pointer

    def on_bar_release(self, e) -> None:
        self._bar_drag = None
        self._save_view_soon()
        self._end_interaction()

    def pan_view(self, delta: float) -> None:
        self.set_view(vr.pan(self.view, delta))

    def fit_to_entries(self) -> None:
        fit = vr.fit_view(self.view_cal.events)
        if fit:
            self.set_view(fit)

    def widen_view(self, events) -> None:
        """Make room for newly added entries (the range never shrinks by itself)."""
        self.set_view(vr.widen(self.view, vr.entries_span(events)))

    def set_view(self, view: tuple[float, float], save: bool = True) -> None:
        view = vr.clamp(view)
        if view != self.view:
            self.view = view
            self.redraw()
            self.status.config(text=f"Showing {vr.label(view[0])}–{vr.label(view[1])}  ·  wheel moves, Ctrl + wheel "
                                    "zooms, Shift + wheel changes the week, double-click the bar to fit all entries")
            if save:
                self._save_view_soon()

    def _save_view_soon(self) -> None:
        if self._save_view_job:
            self.after_cancel(self._save_view_job)
        self._save_view_job = self.after(400, self._save_view)

    def _save_view(self) -> None:
        self._save_view_job = None
        try:
            storage.save_view(self.view)
        except OSError:
            pass

    def _update_nav(self, dated: bool) -> None:
        state = "normal" if dated else "disabled"
        for b in self.nav_buttons:
            b.config(state=state)
        for i in range(5):
            self.m_view.entryconfig(i, state=state)

    def changed(self) -> None:
        try:
            storage.save(self.cal)
        except OSError as exc:
            messagebox.showwarning("Autosave failed", str(exc))
        self.redraw()

    def _show_first_dated_week(self, events) -> None:
        dates = [e.date for e in events if e.dated]
        if dates:
            self.week = week_start(min(dates))

    # --- navigation ----------------------------------------------------------

    def shift_week(self, n: int) -> None:
        if not self.dated:
            return
        self.week += timedelta(weeks=n)
        self.redraw()

    def go_today(self) -> None:
        if not self.dated:
            return
        self.week = week_start(today())
        self.redraw()

    def go_first(self) -> None:
        first = self.cal.first_date()
        if first:
            self.week = week_start(first)
            self.redraw()

    def go_to_date(self) -> None:
        if not self.dated:
            return
        text = simpledialog.askstring("Go to date", "Date (DD.MM.YYYY):", parent=self)
        if not text:
            return
        d = parse_date(text)
        if d is None:
            messagebox.showerror("Go to date", f"'{text}' is not a valid date. Use DD.MM.YYYY.")
            return
        self.week = week_start(d)
        self.redraw()

    # --- quick add -----------------------------------------------------------

    QUICK_HINT = "e.g. Mo, 8-9, Schoolwork, tag: Uni"

    def _quick_placeholder(self, show: bool) -> None:
        if show and not self.quick.get():
            self.quick.insert(0, self.QUICK_HINT)
            self.quick.config(fg="#9ca3af")
            self._quick_hint = True
        elif not show and self._quick_hint:
            self.quick.delete(0, "end")
            self.quick.config(fg="black")
            self._quick_hint = False

    def _quick_error(self, on: bool) -> None:
        color = "#ef4444" if on else "#c4c4c4"
        self.quick.config(highlightbackground=color, highlightcolor="#ef4444" if on else "#3b82f6")

    def focus_quick_add(self) -> None:
        self.quick.focus_set()

    def quick_add(self) -> None:
        text = "" if self._quick_hint else self.quick.get().strip()
        if not text:
            self.focus_quick_add()
            return
        ev, warnings = parse_entry(text)
        if ev is None:
            self._quick_error(True)
            self.status.config(text=f"Not added: {warnings[0]}")
            return
        added, _ = self.cal.add([ev])
        self.widen_view([ev])
        if ev.dated:
            self.week = week_start(ev.date)
        self.changed()
        self.quick.delete(0, "end")
        self._quick_error(False)
        when = f"{WEEKDAYS[ev.date.weekday()]}, {fmt_date(ev.date)}" if ev.dated else f"every {ev.day_name}"
        msg = f"Added: {ev.title} ({when}, {ev.time_label()})" if added else f"Already in the calendar: {ev.title}"
        if warnings:
            msg += f"  ·  note: {warnings[0]}"
        if ev.dated and self.routine_only.get():
            msg += "  ·  hidden while 'Weekly routine only' is on"
        self.status.config(text=msg)

    # --- events --------------------------------------------------------------

    def on_motion(self, e) -> None:
        over = self._render and self._render.hit(e.x, e.y)
        self.canvas.config(cursor="hand2" if over else "arrow")

    def on_click(self, e) -> None:
        if not self._render:
            return
        hb = self._render.hit(e.x, e.y)
        if hb:
            self.show_event(hb.event, hb.occurrence)

    def show_event(self, ev: Event, occurrence: date) -> None:
        if ev.dated:
            when = f"{WEEKDAYS[occurrence.weekday()]}, {fmt_date(occurrence)}"
        else:
            when = f"Every {ev.day_name}"
        win = tk.Toplevel(self)
        win.title(ev.title)
        win.transient(self)
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=16)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=ev.title, font=("TkDefaultFont", 13, "bold"), wraplength=380).pack(anchor="w")
        rows = [("When", f"{when}  ·  {ev.time_label()}")]
        if ev.repeat:
            rows.append(("Repeats", f"{ev.repeat.describe()} (series starts {fmt_date(ev.date)})"))
        if ev.location:
            rows.append(("Where", ev.location))
        if ev.tag:
            rows.append(("Tag", ev.tag))
        if ev.notes:
            rows.append(("Notes", ev.notes))
        grid = ttk.Frame(frm)
        grid.pack(anchor="w", pady=(10, 14))
        for i, (k, v) in enumerate(rows):
            ttk.Label(grid, text=k + ":", foreground="#6b7280").grid(row=i, column=0, sticky="nw", padx=(0, 10), pady=2)
            ttk.Label(grid, text=v, wraplength=320, justify="left").grid(row=i, column=1, sticky="nw", pady=2)
        btns = ttk.Frame(frm)
        btns.pack(fill="x")

        def delete() -> None:
            what = "this repeating event (all occurrences)" if ev.repeat else "this event"
            if messagebox.askyesno("Delete event", f"Delete {what}?", parent=win):
                self.cal.remove(ev)
                win.destroy()
                self.changed()

        ttk.Button(btns, text="Delete", command=delete).pack(side="left")
        ttk.Button(btns, text="Close", command=win.destroy).pack(side="right")
        win.bind("<Escape>", lambda e: win.destroy())
        center_over(win, self)

    # --- file actions ----------------------------------------------------------

    def _read(self, title: str) -> ParseResult | None:
        path = filedialog.askopenfilename(parent=self, title=title, filetypes=FILETYPES_IN)
        if not path:
            return None
        try:
            result = parse_file(path)
        except OSError as exc:
            messagebox.showerror(title, f"Could not read the file:\n{exc}")
            return None
        if not result.events:
            self.show_warnings(result.warnings, "No events were found in this file.")
            return None
        return result

    def import_file(self) -> None:
        result = self._read("Import calendar (replaces the current one)")
        if not result:
            return
        if self.cal.events and not messagebox.askyesno(
            "Import", f"Replace the current calendar ({len(self.cal.events)} events) with the imported file?\n\n"
            "Tip: use 'Add…' to merge instead."
        ):
            return
        self.cal.replace_all(result.events, result.title)
        self.widen_view(result.events)
        self.go_first()
        self.changed()
        self.show_warnings(result.warnings, f"Imported {len(self.cal.events)} events.")

    def add_file(self) -> None:
        result = self._read("Add events from file")
        if not result:
            return
        added, skipped = self.cal.add(result.events)
        self.widen_view(result.events)
        if not self.cal.title and result.title:
            self.cal.title = result.title
        if added:
            self._show_first_dated_week(result.events)
        self.changed()
        msg = f"Added {added} event{'s' if added != 1 else ''}."
        if skipped:
            msg += f" {skipped} duplicate{'s were' if skipped != 1 else ' was'} skipped."
        self.show_warnings(result.warnings, msg)

    def show_warnings(self, warnings: list[str], headline: str) -> None:
        if not warnings:
            messagebox.showinfo("Calendar Visualizer", headline, parent=self)
            return
        win = tk.Toplevel(self)
        win.title("Import report")
        win.transient(self)
        frm = ttk.Frame(win, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=headline, font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        ttk.Label(frm, text=f"{len(warnings)} line(s) could not be used and were skipped:").pack(anchor="w", pady=(4, 6))
        txt = tk.Text(frm, width=90, height=min(20, len(warnings) + 1), wrap="word")
        txt.insert("1.0", "\n".join(warnings))
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)
        ttk.Button(frm, text="OK", command=win.destroy).pack(anchor="e", pady=(8, 0))
        center_over(win, self)

    def export_md(self) -> None:
        cal = self.view_cal
        title = "Export weekly routine as Markdown (dated entries left out)" if self.routine_only.get() \
            else "Export calendar as Markdown"
        path = filedialog.asksaveasfilename(
            parent=self, title=title, defaultextension=".md",
            initialfile=_safe_name(self.cal.title or "calendar") + ".md",
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt")],
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(to_markdown(cal))
        self.status.config(text=f"Exported {len(cal.events)} entries to {path}")

    def export_ics(self) -> None:
        if not self.cal.events:
            messagebox.showinfo("Export .ics", "The calendar is empty.", parent=self)
            return
        ExportIcsDialog(self)

    def export_image(self) -> None:
        ExportImageDialog(self)

    def rename(self) -> None:
        name = simpledialog.askstring("Rename calendar", "Calendar title:", initialvalue=self.cal.title, parent=self)
        if name is not None:
            self.cal.title = name.strip()
            self.changed()

    def clear(self) -> None:
        if messagebox.askyesno("Clear calendar", "Remove all events? (Export first if you want to keep them.)"):
            self.cal = Calendar()
            self.changed()

    def save_guide(self) -> None:
        path = filedialog.asksaveasfilename(parent=self, initialfile="AI_SYNTAX_GUIDE.md", defaultextension=".md",
                                            filetypes=[("Markdown", "*.md")])
        if path:
            shutil.copyfile(AI_GUIDE, path)

    def open_data_dir(self) -> None:
        folder = str(storage.data_dir())
        if not os.path.isdir(folder):
            messagebox.showinfo("Autosave folder", f"Nothing has been saved yet.\n\n{folder}")
            return
        if hasattr(os, "startfile"):
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            messagebox.showinfo("Autosave folder", folder)

    def remove_data_and_quit(self) -> None:
        folder = storage.data_dir()
        if not messagebox.askyesno(
            "Remove all my data",
            f"This deletes the saved calendar and the folder\n{folder}\nthen closes the program.\n\n"
            "Export your calendar first if you want to keep it. Continue?",
            icon="warning",
        ):
            return
        if self._save_view_job:  # don't recreate the folder right after removing it
            self.after_cancel(self._save_view_job)
            self._save_view_job = None
        storage.remove_all_data()
        messagebox.showinfo(
            "Data removed",
            "All data has been removed.\n\nTo remove the program itself, delete CalendarVisualizer.exe. "
            "Nothing else is left on your PC.",
        )
        self.destroy()

    def about(self) -> None:
        messagebox.showinfo(
            "About",
            f"Calendar Visualizer {__version__}\n\nTurns .md / .txt event lists into a calendar.\n"
            "Help → 'Save AI syntax guide' gives you the file describing the event syntax.",
        )


class ExportImageDialog(tk.Toplevel):
    def __init__(self, app: App) -> None:
        super().__init__(app)
        self.app = app
        self.title("Export image")
        self.transient(app)
        self.resizable(False, False)
        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)

        self.scope = tk.StringVar(value="current")
        self.scale = tk.StringVar(value="3")

        ttk.Label(frm, text="Weeks", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, sticky="w")
        if app.dated:
            ttk.Radiobutton(frm, text=f"Current week ({fmt_date(app.week)} – {fmt_date(app.week + timedelta(days=6))})",
                            value="current", variable=self.scope).grid(row=1, column=0, columnspan=2, sticky="w")
            n_weeks = len(app.view_cal.weeks_with_events())
            ttk.Radiobutton(frm, text=f"All weeks with dated entries ({n_weeks} images into a folder)", value="all",
                            variable=self.scope).grid(row=2, column=0, columnspan=2, sticky="w")
        else:
            ttk.Label(frm, text="The weekly planner (one image)").grid(row=1, column=0, columnspan=2, sticky="w")

        ttk.Label(frm, text="Resolution", font=("TkDefaultFont", 10, "bold")).grid(row=3, column=0, sticky="w", pady=(12, 0))
        res = ttk.Frame(frm)
        res.grid(row=4, column=0, columnspan=2, sticky="w")
        for s in ("2", "3", "4", "6"):
            ttk.Radiobutton(res, text=f"{s}×  ({1400 * int(s)} px wide)", value=s, variable=self.scale).pack(anchor="w")

        btns = ttk.Frame(frm)
        btns.grid(row=5, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="Export PNG…", command=self.run).pack(side="right", padx=6)
        self.bind("<Escape>", lambda e: self.destroy())
        center_over(self, app)

    def run(self) -> None:
        app = self.app
        scale = float(self.scale.get())
        ext = ".png"
        base = _safe_name(app.cal.title or "calendar")
        if not app.dated or self.scope.get() == "current":
            label = _week_label(app.week) if app.dated else "weekly-planner"
            path = filedialog.asksaveasfilename(
                parent=self, title="Save image", defaultextension=ext,
                initialfile=f"{base}_{label}{ext}",
                filetypes=[("PNG image", "*.png")],
            )
            if not path:
                return
            if app.dated:
                export_week(app.view_cal, app.week, path, scale, tags=tag_colors(app.cal), view=app.view)
            else:
                export_week(app.view_cal, PLANNER_WEEK, path, scale, show_dates=False, tags=tag_colors(app.cal),
                            view=app.view)
            app.status.config(text=f"Saved {path}")
        else:
            weeks = app.view_cal.weeks_with_events()
            if not weeks:
                messagebox.showinfo("Export image", "The calendar has no dated entries.", parent=self)
                return
            folder = filedialog.askdirectory(parent=self, title="Choose a folder for the images")
            if not folder:
                return
            self.config(cursor="watch")
            self.update()
            for wk in weeks:
                export_week(app.view_cal, wk, os.path.join(folder, f"{base}_{_week_label(wk)}{ext}"), scale,
                            tags=tag_colors(app.cal), view=app.view)
            self.config(cursor="")
            app.status.config(text=f"Saved {len(weeks)} images to {folder}")
        self.destroy()


class ExportIcsDialog(tk.Toplevel):
    """Pick entries (All / Dated / Weekly + checklist) and write them to one .ics file."""

    def __init__(self, app: App) -> None:
        super().__init__(app)
        self.app = app
        self.title("Export .ics")
        self.transient(app)
        self.minsize(520, 460)
        cal = app.cal
        # weekly entries first (by weekday), then dated ones chronologically
        self.items = [(ev, tk.BooleanVar(value=True)) for ev in cal.undated_events() + cal.dated_events()]
        for _, var in self.items:
            var.trace_add("write", lambda *a: self._update())

        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Which entries", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self.scope = tk.StringVar(value="weekly" if app.routine_only.get() else "all")
        n_weekly = sum(1 for ev, _ in self.items if not ev.dated)
        n_dated = len(self.items) - n_weekly
        radios = ttk.Frame(frm)
        radios.pack(anchor="w", pady=(2, 8))
        for value, text in [("all", f"All ({len(self.items)})"), ("dated", f"Dated only ({n_dated})"),
                            ("weekly", f"Weekly (undated) only ({n_weekly})")]:
            ttk.Radiobutton(radios, text=text, value=value, variable=self.scope,
                            command=self._fill).pack(side="left", padx=(0, 12))

        # Scrollable checklist
        box = ttk.Frame(frm, relief="solid", borderwidth=1)
        box.pack(fill="both", expand=True)
        self.list_canvas = tk.Canvas(box, highlightthickness=0, background="white", height=240)
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.list_canvas.yview)
        self.list_canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.list_canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.list_canvas, background="white")
        self._inner_id = self.list_canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all")))
        self.list_canvas.bind("<Configure>", lambda e: self.list_canvas.itemconfigure(self._inner_id, width=e.width))
        for w in (self.list_canvas, self.inner):
            w.bind("<Enter>", lambda e: self._wheel(True))
            w.bind("<Leave>", lambda e: self._wheel(False))

        row = ttk.Frame(frm)
        row.pack(fill="x", pady=(6, 10))
        ttk.Button(row, text="Select all", command=lambda: self._set_all(True)).pack(side="left")
        ttk.Button(row, text="Deselect all", command=lambda: self._set_all(False)).pack(side="left", padx=6)
        self.counter = ttk.Label(row)
        self.counter.pack(side="right")

        # Weekly entries need real dates in a calendar app: they become weekly repeating events.
        self.weekly_box = ttk.LabelFrame(frm, text="Weekly entries become events repeating every week", padding=8)
        self.weekly_box.pack(fill="x")
        monday = week_start(today())
        self.start_var = tk.StringVar(value=fmt_date(monday))
        self.until_var = tk.StringVar(value="")
        ttk.Label(self.weekly_box, text="Start on:").grid(row=0, column=0, sticky="w")
        self.start_entry = ttk.Entry(self.weekly_box, textvariable=self.start_var, width=12)
        self.start_entry.grid(row=0, column=1, sticky="w", padx=(4, 16))
        ttk.Label(self.weekly_box, text="Repeat until:").grid(row=0, column=2, sticky="w")
        self.until_entry = ttk.Entry(self.weekly_box, textvariable=self.until_var, width=12)
        self.until_entry.grid(row=0, column=3, sticky="w", padx=4)
        ttk.Label(self.weekly_box, text="(DD.MM.YYYY, empty = no end)", foreground="#6b7280").grid(row=0, column=4, sticky="w")
        self.date_error = ttk.Label(self.weekly_box, text="", foreground="#dc2626")
        self.date_error.grid(row=1, column=0, columnspan=5, sticky="w")
        for var in (self.start_var, self.until_var):
            var.trace_add("write", lambda *a: self._update())

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(12, 0))
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")
        self.export_btn = ttk.Button(btns, text="Export .ics…", command=self.run)
        self.export_btn.pack(side="right", padx=6)
        self.bind("<Escape>", lambda e: self.destroy())

        self._fill()
        center_over(self, app)

    # -- helpers --
    def _wheel(self, on: bool) -> None:
        if on:
            self.bind_all("<MouseWheel>", lambda e: self.list_canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
            self.bind_all("<Button-4>", lambda e: self.list_canvas.yview_scroll(-1, "units"))
            self.bind_all("<Button-5>", lambda e: self.list_canvas.yview_scroll(1, "units"))
        else:
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                self.unbind_all(seq)

    def destroy(self) -> None:
        self._wheel(False)
        super().destroy()

    def visible(self) -> list[tuple[Event, tk.BooleanVar]]:
        scope = self.scope.get()
        return [(ev, var) for ev, var in self.items
                if scope == "all" or (scope == "dated") == ev.dated]

    @staticmethod
    def _label(ev: Event) -> str:
        if ev.dated:
            day = f"{WEEKDAYS[ev.date.weekday()][:3]} {fmt_date(ev.date)}"
        else:
            day = f"Every {ev.day_name}"
        text = f"{day}   {ev.time_label()}   {ev.title}"
        if ev.repeat:
            text += f"   (repeats {ev.repeat.describe()})"
        if ev.tag:
            text += f"   [{ev.tag}]"
        return text

    def _fill(self) -> None:
        for child in self.inner.winfo_children():
            child.destroy()
        for ev, var in self.visible():
            tk.Checkbutton(self.inner, text=self._label(ev), variable=var, anchor="w", background="white",
                           activebackground="#eff6ff", highlightthickness=0).pack(fill="x", anchor="w", padx=4)
        self.list_canvas.yview_moveto(0)
        self._update()

    def _set_all(self, value: bool) -> None:
        for _, var in self.visible():
            var.set(value)

    def _dates(self) -> tuple[date | None, date | None, str]:
        start_txt, until_txt = self.start_var.get().strip(), self.until_var.get().strip()
        start = parse_date(start_txt)
        if start is None:
            return None, None, "Start date is not a valid date (DD.MM.YYYY)."
        until = None
        if until_txt:
            until = parse_date(until_txt)
            if until is None:
                return None, None, "'Repeat until' is not a valid date (DD.MM.YYYY)."
            if until < start:
                return None, None, "'Repeat until' is before the start date."
        return start, until, ""

    def selected(self) -> list[Event]:
        return [ev for ev, var in self.visible() if var.get()]

    def _update(self) -> None:
        vis = self.visible()
        chosen = self.selected()
        self.counter.config(text=f"{len(chosen)} of {len(vis)} selected")
        has_weekly = any(not ev.dated for ev in chosen)
        state = "normal" if has_weekly else "disabled"
        self.start_entry.config(state=state)
        self.until_entry.config(state=state)
        error = self._dates()[2] if has_weekly else ""
        self.date_error.config(text=error)
        self.export_btn.config(state="normal" if chosen and not error else "disabled")

    def run(self) -> None:
        events = self.selected()
        start, until, error = self._dates()
        if not events or (error and any(not ev.dated for ev in events)):
            return
        app = self.app
        path = filedialog.asksaveasfilename(
            parent=self, title="Export .ics", defaultextension=".ics",
            initialfile=_safe_name(app.cal.title or "calendar") + ".ics",
            filetypes=[("iCalendar file", "*.ics")],
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(to_ics(events, app.cal.title, weekly_start=start, weekly_until=until))
        app.status.config(text=f"Exported {len(events)} entr{'ies' if len(events) != 1 else 'y'} to {path}")
        self.destroy()


def center_over(win: tk.Toplevel, parent: tk.Misc) -> None:
    """Show a popup centred over the main window instead of the screen's top-left corner."""
    win.withdraw()  # hide until positioned, so it doesn't flash in the corner
    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
    x = max(0, min(x, win.winfo_screenwidth() - w))
    y = max(0, min(y, win.winfo_screenheight() - h))
    win.geometry(f"+{x}+{y}")
    win.deiconify()


def _week_label(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "calendar"


def main() -> None:
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # crisp rendering on high-DPI screens
        except Exception:
            pass
    App().mainloop()
