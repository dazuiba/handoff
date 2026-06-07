"""ds-cli list command."""

import sys

from ..core import get_db, format_run_row
from ..config import Config


def cmd_list(argv: list[str], config: Config):
    """ds-cli list [--uuid] [--cwd]"""
    show_uuid = False
    full_cwd = False

    for a in argv:
        if a == "--uuid":
            show_uuid = True
        elif a == "--cwd":
            full_cwd = True
        elif a in ("-h", "--help"):
            from ..main import usage
            usage()
            sys.exit(0)
        else:
            print(f"ds-cli list: unknown argument {a}", file=sys.stderr)
            sys.exit(2)

    conn = get_db()
    rows = conn.execute(
        "SELECT seq, run_id, uuid, cwd, prompt, created_at, jsonl_path, status, backend "
        "FROM runs ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    conn.close()

    if not rows:
        print("(no runs)")
        return

    if sys.stdin.isatty() and sys.stdout.isatty():
        from ..tui import RunListApp

        app = RunListApp(rows, full_cwd)
        app.run()

        if app.action_result and app.action_result.startswith("go:"):
            run_id = app.action_result[3:]
            from .go import cmd_go
            cmd_go([run_id], config)
        return

    header = ["RUN", "DATE", "PROMPT", "CWD"]
    if show_uuid:
        header.append("UUID")

    lines = ["  ".join(header)]
    for r in rows:
        fmt = format_run_row(r, full_cwd)
        cols = [
            fmt["id"].ljust(13),
            fmt["date"].ljust(11),
            fmt["prompt"].ljust(30),
            fmt["cwd"],
        ]
        if show_uuid:
            cols.append(fmt["uuid"])
        lines.append("  ".join(cols))

    print("\n".join(lines))
