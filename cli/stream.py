"""Stream processing helpers for ds-cli."""

from __future__ import annotations

import sys
import subprocess
import signal
import datetime
from .jsonl_parser import extract_result, format_event_for_stream, parse_jsonl_line


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

    This is the core execution loop for 'run'.

    The `cmd` list should already be the full claude invocation wrapped in
    ["script", "-q", "/dev/null", "claude", ...] (wrapping happens in the command function).
    """
    _, out_path, result_path = task_paths_tuple

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
        with open(jsonl_path, "w") as jf, open(out_path, "w") as of:
            last_ts = ""
            last_plan = ""

            for line_bytes in proc.stdout:
                try:
                    line = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
                except UnicodeDecodeError:
                    line = line_bytes.decode("latin-1", errors="replace").rstrip("\r\n")

                jf.write(line + "\n")
                jf.flush()

                if not line.startswith("{"):
                    continue

                events = parse_jsonl_line(line, last_ts)
                for event in events:
                    if event.ts:
                        last_ts = event.ts

                    if event.kind == "result_text" and event.text:
                        result = event.text
                        result_seen = True
                        continue

                    plan_text = format_event_for_stream(event)
                    if not plan_text or plan_text == last_plan:
                        continue

                    ts = event.ts or datetime.datetime.now().strftime("%H:%M:%S")
                    disp = f"{ts} {plan_text}"
                    print(disp, file=sys.stderr, flush=True)
                    of.write(disp + "\n")
                    of.flush()
                    last_plan = plan_text

    except KeyboardInterrupt:
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
