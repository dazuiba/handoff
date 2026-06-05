"""ds-cli recall command."""

import os
import sys
import shlex

from ..core import get_db, find_run, short_path


def cmd_recall(argv: list[str], config=None):
    """ds-cli recall [<run-id|seq>] --cmd <command>"""
    cmd = ""
    selector = ""

    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--cmd":
            i += 1
            if i >= len(argv):
                print("ds-cli recall: --cmd requires a value", file=sys.stderr)
                sys.exit(2)
            cmd = argv[i]
        elif a.startswith("--cmd="):
            cmd = a[len("--cmd="):]
        elif a in ("-h", "--help"):
            from ..main import usage
            usage()
            sys.exit(0)
        elif a.startswith("-"):
            print(f"ds-cli recall: unknown option {a}", file=sys.stderr)
            sys.exit(2)
        else:
            selector = a
        i += 1

    if not cmd:
        print("ds-cli recall: --cmd required", file=sys.stderr)
        sys.exit(2)

    conn = get_db()
    row = find_run(conn, selector or None)
    conn.close()

    if not row:
        print("ds-cli recall: no run found", file=sys.stderr)
        sys.exit(1)

    if "${uuid}" in cmd:
        final_cmd = cmd.replace("${uuid}", row["uuid"])
    else:
        final_cmd = f"{cmd} {row['uuid']}"

    cwd = row["cwd"]
    print(f"cd {short_path(cwd)}; {final_cmd}", file=sys.stderr)
    os.execvp("sh", ["sh", "-c", f"cd {shlex.quote(cwd)} && {final_cmd}"])
