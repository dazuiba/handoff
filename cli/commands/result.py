"""ds-cli result command."""

import sys

from ..core import get_db, resolve_jsonl, extract_result


def cmd_result(argv: list[str], config=None):
    """ds-cli result <run-id|seq|jsonl>"""
    target = ""
    for a in argv:
        if a in ("-h", "--help"):
            from ..main import usage
            usage()
            sys.exit(0)
        elif a.startswith("-"):
            print(f"ds-cli result: unknown option {a}", file=sys.stderr)
            sys.exit(2)
        else:
            target = a

    if not target:
        print("ds-cli result: id or jsonl file required", file=sys.stderr)
        sys.exit(2)

    conn = get_db()
    jsonl_path = resolve_jsonl(target, conn)
    conn.close()

    text = extract_result(jsonl_path)
    if text:
        print(text)
        return
    print(f"ds-cli result: no successful result in {jsonl_path}", file=sys.stderr)
    sys.exit(1)
