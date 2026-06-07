"""ds-cli tail command."""

import sys
import os

from ..core import get_db, find_run, short_path, prompt_prefix, task_paths


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
    conn.close()

    if not row:
        print("ds-cli tail: no run found", file=sys.stderr)
        sys.exit(1)

    jsonl_path = row["jsonl_path"]
    if not os.path.exists(jsonl_path):
        print(f"ds-cli tail: jsonl not found: {jsonl_path}", file=sys.stderr)
        sys.exit(1)

    run_id = row["run_id"]
    prompt_path, out_path, result_path = task_paths(run_id)

    run_info = {
        "run_id": run_id,
        "date": row["created_at"],
        "cwd": short_path(row["cwd"]),
        "uuid": row["uuid"],
    }

    from ..jsonl_viewer import run_tail
    run_tail(jsonl_path, prompt_path, result_path, run_info)
