"""Stream processing helpers for ds-cli.

Handles JSONL reading/writing, cclean integration, progress display,
and foreground result output.
"""

from __future__ import annotations

import sys
import json
import subprocess
import threading
import signal
import datetime

from .core import progress_preview, CCLEAN, extract_result


def read_tail_lines(jsonl_path: str, max_lines: int = 80) -> list[str]:
    try:
        with open(jsonl_path, "r") as f:
            raw = [line for line in f if line.startswith("{")]
    except FileNotFoundError:
        return [f"jsonl not found: {jsonl_path}"]

    raw = raw[-max(20, max_lines):]
    if not raw:
        return ["(no json lines)"]

    try:
        proc = subprocess.run(
            [CCLEAN, "-n"],
            input="".join(raw),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        lines = [line.rstrip() for line in proc.stdout.splitlines() if line.strip()]
        if lines:
            return lines[-max_lines:]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    display = []
    for line in raw:
        preview = progress_preview(line)
        if preview:
            try:
                t = json.loads(line).get("type", "")
            except json.JSONDecodeError:
                t = ""
            display.append(f"{t}\t{preview}")
    return display[-max_lines:] or ["(no displayable events)"]


def run_claude_foreground(
    cwd: str,
    prompt_text: str,
    session_id: str | None,
    jsonl_path: str,
    cmd: list[str],
    conn,
    uid: str,
    task_paths_tuple,
):
    """Run claude in foreground, writing to jsonl and displaying progress.

    Used by 'start --fg'.  The 'run' and 'run-demo' commands use _execute() instead.
    """
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    with open(jsonl_path, "w") as jf:
        for line_bytes in proc.stdout:
            try:
                line = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
            except UnicodeDecodeError:
                line = line_bytes.decode("latin-1", errors="replace").rstrip("\r\n")

            jf.write(line + "\n")
            jf.flush()

            if not line.startswith("{"):
                continue

            try:
                obj = json.loads(line)
                t = obj.get("type", "")
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                if t == "assistant":
                    c0 = obj["message"]["content"][0]
                    text = (c0.get("text") or c0.get("input") or "")[:70]
                    text = text.replace("\n", " ")
                    print(f"{ts} {t}\t{text}")
                elif t == "user":
                    text = (obj["message"]["content"][0].get("content", "") or "")[:70]
                    text = text.replace("\n", " ")
                    print(f"{ts} {t}\t{text}")
                elif t == "result":
                    print(f'{ts} result\tDONE: {obj.get("result", "")}')
                elif t == "system":
                    print(f"{ts} system\t{obj.get('subtype', '')}")
                elif t == "stream_event":
                    print(f"{ts} stream_event\t{obj.get('event', {}).get('type', '')}")
            except (json.JSONDecodeError, KeyError, IndexError):
                pass

    proc.wait()


def run_claude_background(cwd: str, prompt_text: str, session_id: str | None, jsonl_path: str, cmd: list[str]):
    """Run claude in background, writing to jsonl.

    Used by 'start' (without --fg).
    """
    with open(jsonl_path, "w") as jf:
        subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=jf,
            stderr=subprocess.STDOUT,
        )


def _pump_cclean(cclean, of):
    """Background thread to read cclean output and print to stderr."""
    for cleaned in cclean.stdout:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        disp = f"{ts} {cleaned.rstrip()}"
        print(disp, file=sys.stderr, flush=True)
        of.write(disp + "\n")
        of.flush()


def execute_run(
    cwd: str,
    prompt_text: str,
    cmd: list[str],
    conn,
    uid: str,
    jsonl_path: str,
    task_paths_tuple,
):
    """Execute a claude run: pipe output to JSONL, display progress, extract result.

    This is the core execution loop for 'run' and 'run-demo'.

    The `cmd` list should already be the full claude invocation wrapped in
    ["script", "-q", "/dev/null", "claude", ...] (wrapping happens in the command function).
    """
    from .core import task_paths
    prompt_path, out_path, result_path = task_paths_tuple

    def update_status(status: str):
        conn.execute("UPDATE runs SET status = ? WHERE uuid = ?", (status, uid))
        conn.commit()

    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    result = None
    result_seen = False

    try:
        cclean = subprocess.Popen(
            [CCLEAN, "-s", "compact"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1,
        )
    except (FileNotFoundError, OSError):
        cclean = None

    try:
        with open(jsonl_path, "w") as jf, open(out_path, "w") as of:
            pump_thread = None
            if cclean is not None:
                pump_thread = threading.Thread(
                    target=_pump_cclean, args=(cclean, of), daemon=True
                )
                pump_thread.start()

            for line_bytes in proc.stdout:
                try:
                    line = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
                except UnicodeDecodeError:
                    line = line_bytes.decode("latin-1", errors="replace").rstrip("\r\n")

                jf.write(line + "\n")
                jf.flush()

                if not line.startswith("{"):
                    continue

                if cclean is not None:
                    try:
                        cclean.stdin.write(line + "\n")
                        cclean.stdin.flush()
                    except (BrokenPipeError, ValueError):
                        cclean = None
                else:
                    preview = progress_preview(line)
                    if preview:
                        ts = datetime.datetime.now().strftime("%H:%M:%S")
                        try:
                            t = json.loads(line).get("type", "")
                        except json.JSONDecodeError:
                            t = ""
                        if t in ("assistant", "result"):
                            disp = f"{ts} {t}\t{preview}"
                            print(disp, file=sys.stderr)
                            of.write(disp + "\n")
                            of.flush()

                try:
                    obj = json.loads(line)
                    if obj.get("type") == "result":
                        if (
                            obj.get("subtype", "success") == "success"
                            and not obj.get("is_error", False)
                        ):
                            r = obj.get("result", "")
                            if r:
                                result = r
                                result_seen = True
                except json.JSONDecodeError:
                    pass

            if cclean is not None:
                try:
                    cclean.stdin.close()
                except (BrokenPipeError, ValueError):
                    pass
                if pump_thread is not None:
                    pump_thread.join(timeout=5)
                try:
                    cclean.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    cclean.kill()

    except KeyboardInterrupt:
        if cclean is not None:
            cclean.kill()
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        update_status("interrupted")
        print("\nds-cli run: interrupted", file=sys.stderr)
        with open(result_path, "w") as rf:
            rf.write("INTERRUPTED\n")
        conn.close()
        sys.exit(130)

    proc.wait()

    if result_seen:
        update_status("success")
        conn.close()
        with open(result_path, "w") as rf:
            rf.write(result)
        print(result)
        sys.exit(0)

    result = extract_result(jsonl_path)
    if result:
        update_status("success")
        conn.close()
        with open(result_path, "w") as rf:
            rf.write(result)
        print(result)
        sys.exit(0)

    update_status("error")
    diag = f"ds-cli run: no successful result found; exit status {proc.returncode}\nJSONL={jsonl_path}\n"
    print(diag.rstrip(), file=sys.stderr)
    print(f"JSONL={jsonl_path}", file=sys.stderr)
    with open(result_path, "w") as rf:
        rf.write(diag)
    conn.close()
    sys.exit(1)
