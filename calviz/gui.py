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
from .model import Calendar, Event, today, week_start
from .parser import ParseResult, parse_date, parse_file
from .render import RenderResult, export_week, render_week
from .resources import AI_GUIDE, ICON_PNG, SAMPLE
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
        self.ui_scale = max(1.0, self.winfo_fpixels("1i") / 96)
        self._render: RenderResult | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._redraw_job: str | None = None

        self._build_menu()
        self._build_toolbar()
        self.canvas = tk.Canvas(self, background="white", highlightthickness=0, cursor="arrow")
        self.canvas.pack(fill="both", expand=True)
        self.status = ttk.Label(self, anchor="w", padding=(8, 3))
        self.status.pack(fill="x", side="bottom")

        self.canvas.bind("<Configure>", lambda e: self.schedule_redraw())
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<MouseWheel>", lambda e: self.shift_week(-1 if e.delta > 0 else 1))
        self.canvas.bind("<Button-4>", lambda e: self.shift_week(-1))
        self.canvas.bind("<Button-5>", lambda e: self.shift_week(1))
        self.bind("<Left>", lambda e: self.shift_week(-1))
        self.bind("<Right>", lambda e: self.shift_week(1))
        self.bind("<Control-o>", lambda e: self.import_file())
        self.bind("<Control-a>", lambda e: self.add_file())
        self.bind("<Control-s>", lambda e: self.export_md())
        self.bind("<Control-e>", lambda e: self.export_image())

    # --- layout --------------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        m_file = tk.Menu(menubar, tearoff=False)
        m_file.add_command(label="Import… (replace calendar)", accelerator="Ctrl+O", command=self.import_file)
        m_file.add_command(label="Add events from file…", accelerator="Ctrl+A", command=self.add_file)
        m_file.add_separator()
        m_file.add_command(label="Export as .md…", accelerator="Ctrl+S", command=self.export_md)
        m_file.add_command(label="Export as image…", accelerator="Ctrl+E", command=self.export_image)
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
        menubar.add_cascade(label="View", menu=m_view)

        m_help = tk.Menu(menubar, tearoff=False)
        m_help.add_command(label="Save AI syntax guide (.md)…", command=self.save_guide)
        m_help.add_command(label="Save example file…", command=self.save_sample)
        m_help.add_command(label="Open autosave folder", command=self.open_data_dir)
        m_help.add_separator()
        m_help.add_command(label="About", command=self.about)
        menubar.add_cascade(label="Help", menu=m_help)
        self.config(menu=menubar)

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self, padding=(6, 6))
        bar.pack(fill="x")
        for text, cmd in [
            ("Import…", self.import_file),
            ("Add…", self.add_file),
            ("Export .md…", self.export_md),
            ("Export Image…", self.export_image),
        ]:
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=2)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(bar, text="◀", width=3, command=lambda: self.shift_week(-1)).pack(side="left", padx=2)
        ttk.Button(bar, text="Today", command=self.go_today).pack(side="left", padx=2)
        ttk.Button(bar, text="▶", width=3, command=lambda: self.shift_week(1)).pack(side="left", padx=2)
        ttk.Button(bar, text="Go to date…", command=self.go_to_date).pack(side="left", padx=6)

    # --- drawing -------------------------------------------------------------

    def schedule_redraw(self) -> None:
        if self._redraw_job:
            self.after_cancel(self._redraw_job)
        self._redraw_job = self.after(60, self.redraw)

    def redraw(self) -> None:
        self._redraw_job = None
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w < 50 or h < 50:
            return
        s = self.ui_scale
        self._render = render_week(self.cal, self.week, scale=s, width=int(w / s), height=int(h / s))
        self._photo = ImageTk.PhotoImage(self._render.image)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._photo, anchor="nw")
        n = len(self.cal.events)
        self.status.config(
            text=f"{n} event{'s' if n != 1 else ''}  ·  click an event for details  ·  autosaved to {storage.autosave_path()}"
        )

    def changed(self) -> None:
        try:
            storage.save(self.cal)
        except OSError as exc:
            messagebox.showwarning("Autosave failed", str(exc))
        self.redraw()

    # --- navigation ----------------------------------------------------------

    def shift_week(self, n: int) -> None:
        self.week += timedelta(weeks=n)
        self.redraw()

    def go_today(self) -> None:
        self.week = week_start(today())
        self.redraw()

    def go_first(self) -> None:
        first = self.cal.first_date()
        if first:
            self.week = week_start(first)
            self.redraw()

    def go_to_date(self) -> None:
        text = simpledialog.askstring("Go to date", "Date (YYYY-MM-DD):", parent=self)
        if not text:
            return
        d = parse_date(text)
        if d is None:
            messagebox.showerror("Go to date", f"'{text}' is not a valid date. Use YYYY-MM-DD.")
            return
        self.week = week_start(d)
        self.redraw()

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
        win = tk.Toplevel(self)
        win.title(ev.title)
        win.transient(self)
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=16)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=ev.title, font=("TkDefaultFont", 13, "bold"), wraplength=380).pack(anchor="w")
        rows = [("When", f"{occurrence:%A, %Y-%m-%d}  ·  {ev.time_label()}")]
        if ev.repeat:
            rows.append(("Repeats", f"{ev.repeat.describe()} (series starts {ev.date.isoformat()})"))
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
        self.go_first()
        self.changed()
        self.show_warnings(result.warnings, f"Imported {len(self.cal.events)} events.")

    def add_file(self) -> None:
        result = self._read("Add events from file")
        if not result:
            return
        added, skipped = self.cal.add(result.events)
        if not self.cal.title and result.title:
            self.cal.title = result.title
        if added:
            self.week = week_start(min(e.date for e in result.events))
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

    def export_md(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, title="Export calendar as Markdown", defaultextension=".md",
            initialfile=_safe_name(self.cal.title or "calendar") + ".md",
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt")],
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(to_markdown(self.cal))
        self.status.config(text=f"Exported {len(self.cal.events)} events to {path}")

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
        self._save_copy(AI_GUIDE, "AI_SYNTAX_GUIDE.md")

    def save_sample(self) -> None:
        self._save_copy(SAMPLE, "sample.md")

    def _save_copy(self, src, name: str) -> None:
        path = filedialog.asksaveasfilename(parent=self, initialfile=name, defaultextension=".md",
                                            filetypes=[("Markdown", "*.md")])
        if path:
            shutil.copyfile(src, path)

    def open_data_dir(self) -> None:
        folder = str(storage.data_dir())
        if hasattr(os, "startfile"):
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            messagebox.showinfo("Autosave folder", folder)

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
        self.fmt = tk.StringVar(value="PNG")

        ttk.Label(frm, text="Weeks", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(frm, text=f"Current week ({app.week:%Y-%m-%d})", value="current", variable=self.scope).grid(row=1, column=0, columnspan=2, sticky="w")
        n_weeks = len(app.cal.weeks_with_events())
        ttk.Radiobutton(frm, text=f"All weeks with events ({n_weeks} images into a folder)", value="all", variable=self.scope).grid(row=2, column=0, columnspan=2, sticky="w")

        ttk.Label(frm, text="Resolution", font=("TkDefaultFont", 10, "bold")).grid(row=3, column=0, sticky="w", pady=(12, 0))
        res = ttk.Frame(frm)
        res.grid(row=4, column=0, columnspan=2, sticky="w")
        for s in ("2", "3", "4", "6"):
            ttk.Radiobutton(res, text=f"{s}×  ({1400 * int(s)} px wide)", value=s, variable=self.scale).pack(anchor="w")

        ttk.Label(frm, text="Format", font=("TkDefaultFont", 10, "bold")).grid(row=5, column=0, sticky="w", pady=(12, 0))
        f = ttk.Frame(frm)
        f.grid(row=6, column=0, columnspan=2, sticky="w")
        ttk.Radiobutton(f, text="PNG (best quality)", value="PNG", variable=self.fmt).pack(side="left")
        ttk.Radiobutton(f, text="JPEG (smaller file)", value="JPEG", variable=self.fmt).pack(side="left", padx=10)

        btns = ttk.Frame(frm)
        btns.grid(row=7, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="Export…", command=self.run).pack(side="right", padx=6)

    def run(self) -> None:
        app = self.app
        scale = float(self.scale.get())
        ext = ".png" if self.fmt.get() == "PNG" else ".jpg"
        base = _safe_name(app.cal.title or "calendar")
        if self.scope.get() == "current":
            path = filedialog.asksaveasfilename(
                parent=self, title="Save image", defaultextension=ext,
                initialfile=f"{base}_{_week_label(app.week)}{ext}",
                filetypes=[("PNG image", "*.png"), ("JPEG image", "*.jpg *.jpeg")],
            )
            if not path:
                return
            export_week(app.cal, app.week, path, scale)
            app.status.config(text=f"Saved {path}")
        else:
            weeks = app.cal.weeks_with_events()
            if not weeks:
                messagebox.showinfo("Export image", "The calendar has no events.", parent=self)
                return
            folder = filedialog.askdirectory(parent=self, title="Choose a folder for the images")
            if not folder:
                return
            self.config(cursor="watch")
            self.update()
            for wk in weeks:
                export_week(app.cal, wk, os.path.join(folder, f"{base}_{_week_label(wk)}{ext}"), scale)
            self.config(cursor="")
            app.status.config(text=f"Saved {len(weeks)} images to {folder}")
        self.destroy()


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
