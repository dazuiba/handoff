"""Stream processing for handoff.

`execute_run` drives the backend subprocess and owns the common pipeline
(JSONL capture, status transitions, RESULT= protocol). What varies per backend
type is how its output stream is interpreted; that lives in the parsers:

  ClaudeStreamParser — claude `--output-format stream-json` JSONL
  CodexStreamParser  — `codex exec --json` experimental event JSONL
                       (schema notes: docs/design-notes-codex.md)

Parser contract:
  feed(line) / finish() return display events:
    ("progress", text) — progress line for stderr + .out.txt
    ("session", id)    — backend reported the real session id (codex
                         thread.started); execute_run persists it so the run
                         stays resumable
  result_text / result_is_error — final outcome, read after the stream ends
"""

from __future__ import annotations

import sys
import json
import subprocess
import signal
import datetime
from .jsonl_parser import extract_result, format_event_for_stream, parse_jsonl_line


def _now_ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


class ClaudeStreamParser:
    """Parses claude stream-json output. Faithful port of the original
    execute_run loop: same event handling, same pending/dedupe semantics."""

    def __init__(self):
        self.result_text = None
        self.result_is_error = False
        self.session_id = None
        self._last_ts = ""
        self._last_plan = ""
        self._pending = None  # (ts, plan_text)

    def feed(self, line: str) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        if not line.startswith("{"):
            return out

        events = parse_jsonl_line(line, self._last_ts)
        for event in events:
            if event.ts:
                self._last_ts = event.ts

            if event.kind == "result":
                self._pending = None
                continue

            if event.kind == "result_text" and event.text:
                self._pending = None
                self.result_text = event.text
                continue

            plan_text = format_event_for_stream(event)
            if not plan_text:
                self._flush(out)
                continue

            self._flush(out)
            ts = event.ts or _now_ts()
            self._pending = (ts, plan_text)
        return out

    def finish(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        self._flush(out)
        return out

    def _flush(self, out: list):
        if not self._pending:
            return
        ts, plan_text = self._pending
        self._pending = None
        if not plan_text or plan_text == self._last_plan:
            return
        out.append(("progress", f"{ts} {plan_text}"))
        self._last_plan = plan_text


def _first_line(text: str, limit: int = 200) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line[:limit]


class CodexStreamParser:
    """Parses `codex exec --json` events (see docs/design-notes-codex.md).

    session ← thread.started.thread_id; progress ← item events; result ← the
    last agent_message at turn.completed, or the error message on turn.failed.
    Unknown event/item types are skipped so minor schema drift is survivable.
    """

    def __init__(self):
        self.result_text = None
        self.result_is_error = False
        self.session_id = None
        self._last_agent_message = None

    def feed(self, line: str) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        line = line.strip()
        if not line.startswith("{"):
            return out
        try:
            obj = json.loads(line)
        except ValueError:
            return out
        if not isinstance(obj, dict):
            return out

        etype = obj.get("type")
        ts = _now_ts()

        if etype == "thread.started":
            tid = obj.get("thread_id")
            if tid:
                self.session_id = tid
                out.append(("session", tid))
                out.append(("progress", f"{ts} session {tid}"))
        elif etype in ("item.started", "item.completed"):
            item = obj.get("item") or {}
            itype = item.get("type")
            if itype == "command_execution" and etype == "item.started":
                command = item.get("command", "")
                if command:
                    out.append(("progress", f"{ts} $ {_first_line(command)}"))
            elif itype == "reasoning" and etype == "item.completed":
                text = item.get("text", "")
                if text:
                    out.append(("progress", f"{ts} {_first_line(text)}"))
            elif itype == "agent_message" and etype == "item.completed":
                text = item.get("text", "")
                if text:
                    self._last_agent_message = text
                    out.append(("progress", f"{ts} {_first_line(text)}"))
        elif etype == "turn.completed":
            if self._last_agent_message is not None:
                self.result_text = self._last_agent_message
                self.result_is_error = False
        elif etype == "turn.failed":
            message = (obj.get("error") or {}).get("message") or "turn failed"
            self.result_text = message
            self.result_is_error = True
            out.append(("progress", f"{ts} error: {_first_line(message)}"))
        elif etype == "error":
            # transient (e.g. reconnect retries) — surface but keep streaming
            message = obj.get("message", "")
            if message:
                out.append(("progress", f"{ts} error: {_first_line(message)}"))
        return out

    def finish(self) -> list[tuple[str, str]]:
        return []


def make_parser(backend_type: str):
    return CodexStreamParser() if backend_type == "codex" else ClaudeStreamParser()


def execute_run(
    cwd: str,
    prompt_text: str,
    cmd: list[str],
    conn,
    uid: str,
    jsonl_path: str,
    task_paths_tuple,
    backend_type: str = "claude",
):
    """Execute a backend run: pipe output to JSONL, display progress, extract result.

    This is the core execution loop for 'run'.

    The `cmd` list should already be the full backend invocation, including any
    PTY wrapper (wrapping happens in the command function).
    """
    _, out_path, result_path = task_paths_tuple

    def update_status(status: str):
        conn.execute("UPDATE runs SET status = ? WHERE uuid = ?", (status, uid))
        conn.commit()

    def emit_result_marker():
        disp = f"RESULT={result_path}"
        print(disp, file=sys.stderr, flush=True)
        with open(out_path, "a", encoding="utf-8") as of:
            of.write(disp + "\n")

    def finish_success(result_text: str):
        update_status("success")
        with open(result_path, "w", encoding="utf-8") as rf:
            rf.write(result_text)
        emit_result_marker()
        conn.close()
        print(result_text)
        sys.exit(0)

    parser = make_parser(backend_type)

    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdin=subprocess.DEVNULL,  # prompt travels in argv; never let the PTY
        # wrapper read our stdin (a non-tty stdin makes `script` flaky)
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    try:
        with open(jsonl_path, "w", encoding="utf-8") as jf, open(out_path, "w", encoding="utf-8") as of:

            def handle_events(events):
                for kind, payload in events:
                    if kind == "session":
                        # the backend assigned the real session id (codex);
                        # persist it so this run stays resumable
                        conn.execute(
                            "UPDATE runs SET session_id = ? WHERE uuid = ?",
                            (payload, uid),
                        )
                        conn.commit()
                    elif kind == "progress":
                        print(payload, file=sys.stderr, flush=True)
                        of.write(payload + "\n")
                        of.flush()

            for line_bytes in proc.stdout:
                try:
                    line = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
                except UnicodeDecodeError:
                    line = line_bytes.decode("latin-1", errors="replace").rstrip("\r\n")

                jf.write(line + "\n")
                jf.flush()

                handle_events(parser.feed(line))

            handle_events(parser.finish())

    except KeyboardInterrupt:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        update_status("interrupted")
        with open(result_path, "w", encoding="utf-8") as rf:
            rf.write("INTERRUPTED\n")
        emit_result_marker()
        print("\nhandoff run: interrupted", file=sys.stderr)
        conn.close()
        sys.exit(130)

    proc.wait()

    if parser.result_text is not None and not parser.result_is_error:
        finish_success(parser.result_text)

    if backend_type == "claude":
        result = extract_result(jsonl_path)
        if result:
            finish_success(result)

    update_status("error")
    diag = f"handoff run: no successful result found; exit status {proc.returncode}\nJSONL={jsonl_path}\n"
    if parser.result_is_error and parser.result_text:
        diag = f"handoff run: backend reported an error: {parser.result_text}\n" + diag
    print(diag.rstrip(), file=sys.stderr)
    print(f"JSONL={jsonl_path}", file=sys.stderr)
    with open(result_path, "w", encoding="utf-8") as rf:
        rf.write(diag)
    emit_result_marker()
    conn.close()
    sys.exit(1)
