"""Textual-based TUI for interactive run listing and detail viewing in handoff."""

from __future__ import annotations

from typing import Optional, Callable

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static
from textual.binding import Binding
from textual.coordinate import Coordinate
from textual.message import Message

from .core import format_run_row, task_paths

# Seconds between DB polls for auto-refresh.
POLL_INTERVAL = 5.0


class RunListScreen(Screen):
    """Main screen showing the run list in a DataTable.

    Key bindings:
      Enter / →   — open detail view for the selected run
      G           — resume the selected run's session
      C           — copy session UUID to clipboard
      Q / Esc     — quit
    """

    BINDINGS = [
        Binding("right,space", "select_run", "Detail", show=True),
        Binding("o", "go_resume", "Open in Claude", show=True),
        Binding("c", "copy_session", "Copy Session", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(
        self,
        rows: list,
        full_cwd: bool = False,
        refresh_fn: Callable[[], list] | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ):
        self._rows = rows          # sqlite3.Row objects
        self._full_cwd = full_cwd
        self._result: Optional[str] = None  # "resume:<run_id>" or None
        self._refresh_fn = refresh_fn
        self._fingerprint: str = ""               # change-detection fingerprint
        self._dirty: bool = False                 # data changed while detail view was active
        self._pending_cursor_run_id: str | None = None  # cursor-restore target
        super().__init__(name=name, id=id, classes=classes)

    @property
    def action_result(self) -> Optional[str]:
        return self._result

    def compose(self) -> ComposeResult:
        count = len(self._rows)
        run_label = "run" if count == 1 else "runs"
        yield Static(f" handoff runs  ·  {count} recent {run_label}", id="title_bar")
        yield DataTable(id="run_table", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#run_table", DataTable)
        table.add_columns("RUN", "DATE", "PROMPT", "CWD", "STATUS")

        if not self._rows:
            table.add_row("(no runs)", "", "", "", "")
            return

        for row in self._rows:
            fmt = format_run_row(row, self._full_cwd)
            table.add_row(
                fmt["id"],
                fmt["date"],
                fmt["prompt"][:40],
                fmt["cwd"],
                fmt.get("status", ""),
                key=fmt["id"],
            )

        table.focus()

        # Start periodic DB polling for auto-refresh
        if self._refresh_fn is not None:
            self._fingerprint = self._compute_fingerprint(self._rows)
            self.set_interval(POLL_INTERVAL, self._poll_refresh)

    def _selected_row(self):
        """Return the sqlite3.Row for the currently selected table row."""
        table = self.query_one("#run_table", DataTable)
        if table.row_count == 0:
            return None
        rc = table.cursor_row
        if rc >= len(self._rows):
            return None
        return self._rows[rc]

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle Enter key on a DataTable row."""
        event.stop()
        self._open_detail()

    def action_select_run(self) -> None:
        """Open detail view for the selected run."""
        self._open_detail()

    def _open_detail(self) -> None:
        """Shared detail-opening logic."""
        row = self._selected_row()
        if row is None:
            return

        jsonl_path = row["jsonl_path"]
        run_id = row["run_id"]
        prompt_path, out_path, result_path = task_paths(run_id)

        run_info = {
            "run_id": run_id,
            "date": row["created_at"],
            "cwd": row["cwd"],
            "uuid": row["uuid"],
            "out_path": out_path,
        }

        from .jsonl_viewer import make_viewer_screen
        viewer = make_viewer_screen(jsonl_path, prompt_path, out_path, result_path, run_info)
        self.app.push_screen(viewer)

    def action_go_resume(self) -> None:
        """Resume the selected session."""
        row = self._selected_row()
        if row is None:
            return
        self._result = f"resume:{row['run_id']}"
        # Write result to app so cmd_list can read it after run() returns
        if hasattr(self.app, '_action_result'):
            self.app._action_result = self._result
        self.app.exit()

    def action_copy_session(self) -> None:
        """Copy session UUID to clipboard."""
        import subprocess
        row = self._selected_row()
        if row is None:
            return
        uid = row["uuid"]
        if uid:
            try:
                subprocess.run(["pbcopy"], input=uid, text=True, check=True)
                self.notify(f"Copied: {uid}", severity="information", timeout=3)
            except (subprocess.CalledProcessError, FileNotFoundError):
                self.notify("Copy failed: pbcopy not available", severity="error")

    def action_quit(self) -> None:
        self.app.exit()

    # ── auto-refresh ───────────────────────────────────────────────────────

    @staticmethod
    def _compute_fingerprint(rows: list) -> str:
        """Lightweight change-detection fingerprint: run_id:status per row."""
        return "|".join(f"{r['run_id']}:{r['status']}" for r in rows)

    def _save_cursor_run_id(self) -> None:
        """Remember the currently selected run_id before a table rebuild."""
        if not self._rows:
            self._pending_cursor_run_id = None
            return
        try:
            table = self.query_one("#run_table", DataTable)
            if table.row_count > 0:
                rc = table.cursor_row
                if 0 <= rc < len(self._rows):
                    self._pending_cursor_run_id = self._rows[rc]["run_id"]
                    return
        except Exception:
            pass
        self._pending_cursor_run_id = None

    def _restore_cursor(self) -> None:
        """Move DataTable cursor to the previously selected run_id."""
        if self._pending_cursor_run_id is None:
            return
        target_id = self._pending_cursor_run_id
        self._pending_cursor_run_id = None

        for i, row in enumerate(self._rows):
            if row["run_id"] == target_id:
                try:
                    table = self.query_one("#run_table", DataTable)
                    if i < table.row_count:
                        table.cursor_coordinate = Coordinate(i, 0)
                except Exception:
                    pass
                return

    def _rebuild_table(self) -> None:
        """Clear and repopulate the DataTable from self._rows in place."""
        table = self.query_one("#run_table", DataTable)
        is_active = self.app.screen is self
        had_focus = table.has_focus if is_active else False

        table.clear()

        if not self._rows:
            table.add_row("(no runs)", "", "", "", "")
            self.query_one("#title_bar", Static).update(" handoff runs  ·  0 runs")
            return

        for row in self._rows:
            fmt = format_run_row(row, self._full_cwd)
            table.add_row(
                fmt["id"],
                fmt["date"],
                fmt["prompt"][:40],
                fmt["cwd"],
                fmt.get("status", ""),
                key=fmt["id"],
            )

        # Refresh title-bar count
        count = len(self._rows)
        run_label = "run" if count == 1 else "runs"
        self.query_one("#title_bar", Static).update(
            f" handoff runs  ·  {count} recent {run_label}"
        )

        self._restore_cursor()

        if had_focus:
            table.focus()

    def _poll_refresh(self) -> None:
        """Periodic timer callback: check for new/changed runs from the DB."""
        if self._refresh_fn is None:
            return

        try:
            fresh_rows = self._refresh_fn()
            if fresh_rows is None:
                return

            new_fp = self._compute_fingerprint(fresh_rows)
            if new_fp == self._fingerprint:
                return  # nothing changed
        except Exception:
            return  # transient DB error — skip this tick

        # Data changed — save cursor, update rows/fingerprint, rebuild
        self._save_cursor_run_id()
        self._fingerprint = new_fp
        self._rows = fresh_rows

        if self.app.screen is self:
            # List screen is active → rebuild immediately.
            self._rebuild_table()
        else:
            # Detail view (or another screen) is on top → defer rebuild so the
            # user isn't kicked back to the list.  Data is already updated;
            # rebuild happens on the next poll tick after the screen resumes.
            self._dirty = True

    def _on_screen_resume(self) -> None:
        """Called by Textual when this screen becomes active again after a pop."""
        super()._on_screen_resume()
        if self._dirty:
            self._dirty = False
            self._rebuild_table()


class RunListApp(App):
    """Textual app wrapping the run list screen.

    Usage:
        app = RunListApp(rows, full_cwd)
        app.run()
        if app.action_result:
            # app.action_result == "resume:<run_id>"
            ...
    """

    TITLE = "handoff list"
    CSS = """
    #title_bar {
        dock: top;
        height: 1;
        background: $accent;
        color: $text;
        text-style: bold;
        padding: 0 1;
    }
    """

    def __init__(self, rows: list, full_cwd: bool = False, refresh_fn: Callable[[], list] | None = None):
        self._rows = rows
        self._full_cwd = full_cwd
        self._refresh_fn = refresh_fn
        self._action_result: Optional[str] = None
        super().__init__()

    @property
    def action_result(self) -> Optional[str]:
        return self._action_result

    def on_mount(self) -> None:
        screen = RunListScreen(self._rows, self._full_cwd, refresh_fn=self._refresh_fn)
        self.push_screen(screen)

    def on_screen_dismiss(self, event: Screen.Dismissed) -> None:
        """Capture action result when a screen is dismissed."""
        if event.result and isinstance(event.result, str):
            self._action_result = event.result
