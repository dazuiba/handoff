"""Textual-based TUI for interactive run listing and detail viewing in ds-cli."""

from __future__ import annotations

from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static
from textual.binding import Binding
from textual.coordinate import Coordinate
from textual.message import Message

from .core import format_run_row, task_paths


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
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ):
        self._rows = rows          # sqlite3.Row objects
        self._full_cwd = full_cwd
        self._result: Optional[str] = None  # "go:<run_id>" or None
        super().__init__(name=name, id=id, classes=classes)

    @property
    def action_result(self) -> Optional[str]:
        return self._result

    def compose(self) -> ComposeResult:
        yield Static(" ds-cli runs  —  [Enter] Detail  [O] Open in Claude  [C] Copy Session  [Q] Quit", id="title_bar")
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
        }

        from .jsonl_viewer import make_viewer_screen
        viewer = make_viewer_screen(jsonl_path, prompt_path, result_path, run_info)
        self.app.push_screen(viewer)

    def action_go_resume(self) -> None:
        """Resume the selected session."""
        row = self._selected_row()
        if row is None:
            return
        self._result = f"go:{row['run_id']}"
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


class RunListApp(App):
    """Textual app wrapping the run list screen.

    Usage:
        app = RunListApp(rows, full_cwd)
        app.run()
        if app.action_result:
            # app.action_result == "go:<run_id>"
            ...
    """

    TITLE = "ds-cli list"
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

    def __init__(self, rows: list, full_cwd: bool = False):
        self._rows = rows
        self._full_cwd = full_cwd
        self._action_result: Optional[str] = None
        super().__init__()

    @property
    def action_result(self) -> Optional[str]:
        return self._action_result

    def on_mount(self) -> None:
        screen = RunListScreen(self._rows, self._full_cwd)
        self.push_screen(screen)

    def on_screen_dismiss(self, event: Screen.Dismissed) -> None:
        """Capture action result when a screen is dismissed."""
        if event.result and isinstance(event.result, str):
            self._action_result = event.result
