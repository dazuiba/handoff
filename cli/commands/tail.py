"""ds-cli tail command."""

import os
import sys
import subprocess
import datetime

from ..core import get_db, find_run, short_path, prompt_prefix


def cmd_tail(argv: list[str], config=None):
    """ds-cli tail [<run-id|seq>]"""
    selector = ""
    for a in argv:
        if a in ("-h", "--help"):
            from ..main import usage
            usage()
            sys.exit(0)
        elif a.startswith("-"):
            print(f"ds-cli tail: unknown option {a}", file=sys.stderr)
            sys.exit(2)
        else:
            selector = a

    conn = get_db()
    row = find_run(conn, selector or None)
    if not row:
        print("ds-cli tail: no run found", file=sys.stderr)
        sys.exit(1)

    jsonl_path = row["jsonl_path"]
    if not os.path.exists(jsonl_path):
        print(f"ds-cli tail: jsonl not found: {jsonl_path}", file=sys.stderr)
        sys.exit(1)

    # header line with run info
    try:
        dt = datetime.datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
        date_str = dt.strftime("%m-%d %H:%M")
    except (ValueError, TypeError):
        date_str = row["created_at"] or "?"
    prompt = prompt_prefix(row["prompt"], 10)
    cwd_disp = short_path(row["cwd"])

    print(
        f"run={row['run_id']}  date={date_str}  prompt=\"{prompt}\"  "
        f"cwd={cwd_disp}  uuid={row['uuid']}",
        file=sys.stderr,
    )

    conn.close()

    tail = subprocess.Popen(
        ["tail", "-n", "20", "-F", jsonl_path],
        stdout=subprocess.PIPE,
    )
    grep = subprocess.Popen(
        ["grep", "--line-buffered", "^{"],
        stdin=tail.stdout,
        stdout=subprocess.PIPE,
    )
    tail.stdout.close()
    cclean = subprocess.Popen(
        ["cclean", "-n"],
        stdin=grep.stdout,
    )
    grep.stdout.close()

    procs = [tail, grep, cclean]
    try:
        cclean.wait()
    except KeyboardInterrupt:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                p.kill()
        sys.exit(130)
