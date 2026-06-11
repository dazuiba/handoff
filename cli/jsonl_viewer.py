"""Shared JSONL viewer for handoff list (detail) and tail commands.

Uses Textual to render Claude stream-json output: compact progress log,
input prompt (markdown), and final result (markdown). No external cclean dependency.

Modes:
  - static:  list detail page; Escape dismisses back to list
  - follow:  `handoff tail`; Escape / Q exit the app
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
    """Shared JSONL viewer screen for handoff list (detail) and tail.

    Layout:
      - RunInfoBar (top bar)
      - TabbedContent (Stream / Prompt / Result)
      - Footer (key bindings)
    """

    BINDINGS = [
        Binding("escape", "back", "← Back", show=True),
        Binding("o", "go_resume", "Open in Claude", show=True),
        Binding("c", "copy_session", "Copy Session", show=True),
        Binding("q", "quit", "Quit", show=True),
        Binding("tab", "next_tab", "Next Tab", show=True),
        Binding("shift+tab", "prev_tab", "Prev Tab", show=True),
        Binding("1", "show_tab('stream')", "Stream", show=True),
        Binding("2", "show_tab('output')", "Output", show=True),
        Binding("3", "show_tab('prompt')", "Prompt", show=True),
        Binding("4", "show_tab('result')", "Result", show=True),
        Binding("up,k", "scroll_active('up')", "Scroll up", show=False),
        Binding("down,j", "scroll_active('down')", "Scroll down", show=False),
        Binding("pageup", "scroll_active('page_up')", "Page up", show=False),
        Binding("pagedown", "scroll_active('page_down')", "Page down", show=False),
        Binding("home", "scroll_active('home')", "Top", show=False),
        Binding("end", "scroll_active('end')", "Bottom", show=False),
    ]

    def __init__(
        self,
        jsonl_path: str,
        prompt_path: str,
        out_path: str,
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
        self._o_path = out_path
        self._r_path = result_path
        self._r_info = run_info
        self._mode = mode
        self._last_ts = ""
        self._fpos = 0
        self._out_fpos = 0
        self._result_text: Optional[str] = None
        self._stream_raw = ""      # accumulated stream content for incremental update
        self._out_raw = ""         # accumulated .out.txt content
        self._last_stream_line = ""
        self._poll_interval = 0.5
        # Auto-follow state
        self._auto_follow = {"stream": True, "output": True}
        self._pending_new_count = {"stream": 0, "output": 0}
        self._keep_polling = True
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
            with TabPane("1 Stream JSONL", id="stream"):
                with VerticalScroll(id="stream_scroll"):
                    yield Static("Loading…", id="stream_text", markup=False)
            with TabPane("2 Output .out", id="output"):
                with VerticalScroll(id="output_scroll"):
                    yield Static("Loading…", id="output_text", markup=False)
            with TabPane("3 Prompt", id="prompt"):
                with VerticalScroll(id="prompt_scroll"):
                    yield Static("", id="prompt_text", markup=False)
            with TabPane("4 Result", id="result"):
                with VerticalScroll(id="result_scroll"):
                    yield Static("", id="result_text", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        # Load prompt text
        if os.path.isfile(self._p_path):
            try:
                with open(self._p_path, "r", encoding="utf-8", errors="replace") as f:
                    pt = f.read().strip()
                if pt:
                    self.query_one("#prompt_text", Static).update(
                        self._text_with_path("Prompt", self._p_path, pt)
                    )
            except (OSError, UnicodeDecodeError):
                pass
        else:
            self.query_one("#prompt_text", Static).update(self._text_with_path("Prompt", self._p_path, ""))

        # Load result text
        if os.path.isfile(self._r_path):
            try:
                with open(self._r_path, "r", encoding="utf-8", errors="replace") as f:
                    rt = f.read().strip()
                if rt:
                    self._result_text = rt
                    self.query_one("#result_text", Static).update(
                        self._text_with_path("Result", self._r_path, rt)
                    )
            except (OSError, UnicodeDecodeError):
                pass
        else:
            self.query_one("#result_text", Static).update(self._text_with_path("Result", self._r_path, ""))

        # Load JSONL stream.
        self._stream_raw = self._header_line("JSONL", self._jl_path)
        self.query_one("#stream_text", Static).update(self._stream_raw)
        if os.path.isfile(self._jl_path):
            with open(self._jl_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._fpos)
                events, self._last_ts = read_events(f, self._last_ts)
                self._fpos = f.tell()
            self._append_events(events)

        self._out_raw = self._header_line("Output", self._o_path)
        self.query_one("#output_text", Static).update(self._out_raw)
        self._append_output_from_file()

        # Scroll to bottom after initial load
        self._scroll_to_bottom("stream")
        self._scroll_to_bottom("output")

        # Start poll worker for all modes (live updates for running runs)
        self._poll_jsonl()

    # ── follow worker ────────────────────────────────────────────────────

    @work(exclusive=True, thread=False)
    async def _poll_jsonl(self) -> None:
        while self._keep_polling:
            if os.path.isfile(self._jl_path):
                try:
                    with open(self._jl_path, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(self._fpos)
                        events, self._last_ts = read_events(f, self._last_ts)
                        self._fpos = f.tell()
                    self._append_events(events)
                except (OSError, UnicodeDecodeError):
                    pass

            self._append_output_from_file()

            # Check scroll position to update auto-follow state
            self._sync_auto_follow("stream")
            self._sync_auto_follow("output")

            await asyncio.sleep(self._poll_interval)

    def on_unmount(self) -> None:
        """Ensure poll loop exits when screen is removed."""
        self._keep_polling = False

    def _sync_auto_follow(self, tab_id: str) -> None:
        """Update _auto_follow based on current scroll position."""
        try:
            scroll = self.query_one(f"#{tab_id}_scroll", VerticalScroll)
            self._auto_follow[tab_id] = scroll.is_vertical_scroll_end
        except Exception:
            pass

    def _scroll_to_bottom(self, tab_id: str) -> None:
        """Scroll stream container to bottom."""
        try:
            self.query_one(f"#{tab_id}_scroll", VerticalScroll).scroll_end(animate=False)
        except Exception:
            pass

    def _update_info_bar(self) -> None:
        """Update info bar with auto-follow status."""
        try:
            ri = self._r_info
            parts = [
                f"Run: {ri.get('run_id', '?')}",
                ri.get("date", "?"),
                f"cwd: {ri.get('cwd', '?')}",
            ]
            status_parts = []
            for tab_id, label in (("stream", "stream"), ("output", "output")):
                if self._auto_follow[tab_id]:
                    status_parts.append(f"{label}: follow")
                elif self._pending_new_count[tab_id]:
                    status_parts.append(f"{label}: {self._pending_new_count[tab_id]} new")
                else:
                    status_parts.append(f"{label}: paused")
            parts.append(" | ".join(status_parts))
            self.query_one("#info_bar", Static).update("  ·  ".join(parts))
        except Exception:
            pass

    def _header_line(self, label: str, path: str) -> str:
        return f"{label}: {os.path.abspath(os.path.expanduser(path))}"

    def _text_with_path(self, label: str, path: str, body: str) -> str:
        header = self._header_line(label, path)
        return f"{header}\n\n{body}" if body else header

    def _append_text_block(self, tab_id: str, text: str) -> None:
        if not text:
            return
        self._sync_auto_follow(tab_id)
        attr = "_stream_raw" if tab_id == "stream" else "_out_raw"
        widget_id = "#stream_text" if tab_id == "stream" else "#output_text"
        current = getattr(self, attr) or ""
        updated = current + text if current.endswith("\n") or text.startswith("\n") else current + "\n" + text
        setattr(self, attr, updated)
        try:
            self.query_one(widget_id, Static).update(updated)
        except Exception:
            return

        new_count = text.count("\n") + (0 if text.endswith("\n") else 1)
        if self._auto_follow[tab_id]:
            self._scroll_to_bottom(tab_id)
            self._pending_new_count[tab_id] = 0
        else:
            self._pending_new_count[tab_id] += max(new_count, 1)
        self._update_info_bar()

    def _append_output_from_file(self) -> None:
        if not os.path.isfile(self._o_path):
            return
        try:
            size = os.path.getsize(self._o_path)
            if size < self._out_fpos:
                self._out_fpos = 0
            with open(self._o_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._out_fpos)
                chunk = f.read()
                self._out_fpos = f.tell()
        except OSError:
            return
        self._append_text_block("output", chunk)

    def _append_events(self, events: list[ParsedEvent]) -> None:
        if not events:
            return

        new_lines: list[str] = []
        for event in events:
            if event.kind in ("result_text", "error_text"):
                self._result_text = event.text
                try:
                    self.query_one("#result_text", Static).update(
                        self._text_with_path("Result", self._r_path, self._result_text)
                    )
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

        # Check if we should auto-follow before updating content
        self._sync_auto_follow("stream")

        try:
            current = self._stream_raw or ""
            appended = "\n".join(new_lines)
            self._stream_raw = current + "\n" + appended if current else appended
            self.query_one("#stream_text", Static).update(self._stream_raw)
        except Exception:
            return

        # Auto-scroll or track pending new content
        if self._auto_follow["stream"]:
            self._scroll_to_bottom("stream")
            self._pending_new_count["stream"] = 0
        else:
            self._pending_new_count["stream"] += len(new_lines)

        self._update_info_bar()

    # ── actions ──────────────────────────────────────────────────────────

    def action_back(self) -> None:
        self._keep_polling = False
        if self._mode == "static":
            self.dismiss()
        else:
            self.app.exit()

    def action_go_resume(self) -> None:
        self._keep_polling = False
        rid = self._r_info.get("run_id", "")
        if hasattr(self.app, "_action_result"):
            self.app._action_result = f"resume:{rid}"
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
        self._keep_polling = False
        self.app.exit()

    def action_show_tab(self, tab_id: str) -> None:
        try:
            self.query_one(TabbedContent).active = tab_id
        except Exception:
            pass

    def action_next_tab(self) -> None:
        try:
            tabs = self.query_one(TabbedContent)
            ids = [pane.id for pane in tabs.query(TabPane)]
            if not ids:
                return
            cur = tabs.active
            idx = ids.index(cur) if cur in ids else -1
            next_id = ids[(idx + 1) % len(ids)]
            tabs.active = next_id
        except Exception:
            pass

    def action_prev_tab(self) -> None:
        try:
            tabs = self.query_one(TabbedContent)
            ids = [pane.id for pane in tabs.query(TabPane)]
            if not ids:
                return
            cur = tabs.active
            idx = ids.index(cur) if cur in ids else 0
            prev_id = ids[(idx - 1) % len(ids)]
            tabs.active = prev_id
        except Exception:
            pass

    def action_scroll_active(self, direction: str) -> None:
        try:
            active = self.query_one(TabbedContent).active
            scroll = self.query_one(f"#{active}_scroll", VerticalScroll)
        except Exception:
            return

        if direction == "up":
            scroll.scroll_up(animate=False)
        elif direction == "down":
            scroll.scroll_down(animate=False)
        elif direction == "page_up":
            scroll.scroll_page_up(animate=False)
        elif direction == "page_down":
            scroll.scroll_page_down(animate=False)
        elif direction == "home":
            scroll.scroll_home(animate=False)
        elif direction == "end":
            scroll.scroll_end(animate=False)

        if active in self._auto_follow:
            self._sync_auto_follow(active)
            if self._auto_follow[active]:
                self._pending_new_count[active] = 0
            self._update_info_bar()


# ═══════════════════════════════════════════════════════════════════════════════
# Tail entry point
# ═══════════════════════════════════════════════════════════════════════════════

class JsonlTailApp(App):
    """Standalone Textual app for `handoff tail`."""

    TITLE = "handoff tail"

    def __init__(
        self,
        jsonl_path: str,
        prompt_path: str,
        out_path: str,
        result_path: str,
        run_info: dict,
    ):
        self._a_jl = jsonl_path
        self._a_pp = prompt_path
        self._a_op = out_path
        self._a_rp = result_path
        self._a_ri = run_info
        super().__init__()

    def on_mount(self) -> None:
        self.push_screen(JsonlViewerScreen(
            jsonl_path=self._a_jl,
            prompt_path=self._a_pp,
            out_path=self._a_op,
            result_path=self._a_rp,
            run_info=self._a_ri,
            mode="follow",
        ))


def run_tail(jsonl_path: str, prompt_path: str, result_path: str, run_info: dict) -> None:
    """Entry point for `handoff tail`."""
    out_path = run_info.get("out_path", "")
    JsonlTailApp(jsonl_path, prompt_path, out_path, result_path, run_info).run(mouse=False)


def make_viewer_screen(
    jsonl_path: str,
    prompt_path: str,
    out_path: str,
    result_path: str,
    run_info: dict,
) -> JsonlViewerScreen:
    """Create a viewer screen for embedding in another Textual app (list detail)."""
    return JsonlViewerScreen(
        jsonl_path=jsonl_path,
        prompt_path=prompt_path,
        out_path=out_path,
        result_path=result_path,
        run_info=run_info,
        mode="static",
    )
