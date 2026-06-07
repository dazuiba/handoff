"""Shared JSONL viewer for ds-cli list (detail) and tail commands.

Uses Textual to render Claude stream-json output: compact progress log,
input prompt (markdown), and final result (markdown). No external cclean dependency.

Modes:
  - static:  list detail page; Escape dismisses back to list
  - follow:  `ds-cli tail`; Escape / Q exit the app
"""

from __future__ import annotations

import os
import asyncio
from typing import Optional

from textual import work
from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import (
    Footer,
    Markdown,
    TabbedContent,
    TabPane,
    Static,
)
from textual.containers import VerticalScroll
from textual.binding import Binding
from .jsonl_parser import ParsedEvent, format_event_for_viewer, read_events


# ═══════════════════════════════════════════════════════════════════════════════
# JsonlViewerScreen
# ═══════════════════════════════════════════════════════════════════════════════

class JsonlViewerScreen(Screen):
    """Shared JSONL viewer screen for ds-cli list (detail) and tail.

    Layout:
      - RunInfoBar (top bar)
      - TabbedContent (Stream / Prompt / Result)
      - Footer (key bindings)
    """

    BINDINGS = [
        Binding("escape,left", "back", "Back", show=True),
        Binding("o", "go_resume", "Open in Claude", show=True),
        Binding("c", "copy_session", "Copy Session", show=True),
        Binding("q", "quit", "Quit", show=True),
        Binding("1", "show_tab('stream')", "Stream", show=True),
        Binding("2", "show_tab('prompt')", "Prompt", show=True),
        Binding("3", "show_tab('result')", "Result", show=True),
    ]

    def __init__(
        self,
        jsonl_path: str,
        prompt_path: str,
        result_path: str,
        run_info: dict,
        mode: str = "static",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ):
        # Store parameters before super().__init__
        self._jl_path = jsonl_path
        self._p_path = prompt_path
        self._r_path = result_path
        self._r_info = run_info
        self._mode = mode
        self._last_ts = ""
        self._follow = (mode == "follow")
        self._fpos = 0
        self._result_text: Optional[str] = None
        self._stream_raw = ""      # accumulated stream content for incremental update
        self._last_stream_line = ""
        self._poll_interval = 0.5
        super().__init__(name=name, id=id, classes=classes)

    def compose(self) -> ComposeResult:
        ri = self._r_info
        yield Static(
            f"Run: {ri.get('run_id', '?')}  ·  "
            f"{ri.get('date', '?')}  ·  "
            f"cwd: {ri.get('cwd', '?')}",
            id="info_bar",
        )
        with TabbedContent(initial="stream"):
            with TabPane("Stream", id="stream"):
                with VerticalScroll(id="stream_scroll"):
                    yield Static("Loading…", id="stream_text", markup=False)
            with TabPane("Prompt", id="prompt"):
                yield Markdown("", id="prompt_md")
            with TabPane("Result", id="result"):
                yield Markdown("", id="result_md")
        yield Footer()

    def on_mount(self) -> None:
        # Load prompt markdown
        if os.path.isfile(self._p_path):
            try:
                with open(self._p_path, "r") as f:
                    pt = f.read().strip()
                if pt:
                    self.query_one("#prompt_md", Markdown).update(pt)
            except (OSError, UnicodeDecodeError):
                pass

        # Load result markdown
        if os.path.isfile(self._r_path):
            try:
                with open(self._r_path, "r") as f:
                    rt = f.read().strip()
                if rt:
                    self._result_text = rt
                    self.query_one("#result_md", Markdown).update(rt)
            except (OSError, UnicodeDecodeError):
                pass

        # Load JSONL stream — build compact event log as markdown code block.
        # We use Markdown widget (not RichLog) because Markdown consistently
        # works when the Screen is defined in an imported module.
        if os.path.isfile(self._jl_path):
            with open(self._jl_path, "r") as f:
                f.seek(self._fpos)
                events, self._last_ts = read_events(f, self._last_ts)
                self._fpos = f.tell()
            self._append_events(events)

        # Start follow worker in tail mode
        if self._follow:
            self._poll_jsonl()

    # ── follow worker ────────────────────────────────────────────────────

    @work(exclusive=True, thread=False)
    async def _poll_jsonl(self) -> None:
        while self._follow:
            if os.path.isfile(self._jl_path):
                try:
                    with open(self._jl_path, "r") as f:
                        f.seek(self._fpos)
                        events, self._last_ts = read_events(f, self._last_ts)
                        self._fpos = f.tell()
                    self._append_events(events)
                except (OSError, UnicodeDecodeError):
                    pass
            await asyncio.sleep(self._poll_interval)

    def _append_events(self, events: list[ParsedEvent]) -> None:
        if not events:
            return

        new_lines: list[str] = []
        for event in events:
            if event.kind in ("result_text", "error_text"):
                self._result_text = event.text
                try:
                    self.query_one("#result_md", Markdown).update(self._result_text)
                    self.query_one(TabbedContent).active = "result"
                except Exception:
                    pass
                continue

            line = format_event_for_viewer(event)
            if line and line != self._last_stream_line:
                new_lines.append(line)
                self._last_stream_line = line

        if not new_lines:
            return

        try:
            current = self._stream_raw or ""
            appended = "\n".join(new_lines)
            self._stream_raw = current + "\n" + appended if current else appended
            self.query_one("#stream_text", Static).update(self._stream_raw)
        except Exception:
            pass

    # ── actions ──────────────────────────────────────────────────────────

    def action_back(self) -> None:
        if self._mode == "static":
            self.dismiss()
        else:
            self._follow = False
            self.app.exit()

    def action_go_resume(self) -> None:
        rid = self._r_info.get("run_id", "")
        if hasattr(self.app, "_action_result"):
            self.app._action_result = f"go:{rid}"
        self._follow = False
        self.app.exit()

    def action_copy_session(self) -> None:
        import subprocess
        uid = self._r_info.get("uuid", "")
        if uid:
            try:
                subprocess.run(["pbcopy"], input=uid, text=True, check=True)
                self.notify(f"Copied: {uid}", severity="information", timeout=3)
            except (subprocess.CalledProcessError, FileNotFoundError):
                self.notify("Copy failed: pbcopy not available", severity="error")

    def action_quit(self) -> None:
        self._follow = False
        self.app.exit()

    def action_show_tab(self, tab_id: str) -> None:
        try:
            self.query_one(TabbedContent).active = tab_id
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# Tail entry point
# ═══════════════════════════════════════════════════════════════════════════════

class JsonlTailApp(App):
    """Standalone Textual app for `ds-cli tail`."""

    TITLE = "ds-cli tail"

    def __init__(self, jsonl_path: str, prompt_path: str, result_path: str, run_info: dict):
        self._a_jl = jsonl_path
        self._a_pp = prompt_path
        self._a_rp = result_path
        self._a_ri = run_info
        super().__init__()

    def on_mount(self) -> None:
        self.push_screen(JsonlViewerScreen(
            jsonl_path=self._a_jl,
            prompt_path=self._a_pp,
            result_path=self._a_rp,
            run_info=self._a_ri,
            mode="follow",
        ))


def run_tail(jsonl_path: str, prompt_path: str, result_path: str, run_info: dict) -> None:
    """Entry point for `ds-cli tail`."""
    JsonlTailApp(jsonl_path, prompt_path, result_path, run_info).run()


def make_viewer_screen(jsonl_path: str, prompt_path: str, result_path: str, run_info: dict) -> JsonlViewerScreen:
    """Create a viewer screen for embedding in another Textual app (list detail)."""
    return JsonlViewerScreen(
        jsonl_path=jsonl_path,
        prompt_path=prompt_path,
        result_path=result_path,
        run_info=run_info,
        mode="static",
    )
