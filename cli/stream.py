"""Stream processing helpers for ds-cli.

Handles JSONL reading/writing, cclean-integration progress display,
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

    This is the core execution loop for 'run'.

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
            text=True, encoding="utf-8", errors="replace", bufsize=1,
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
