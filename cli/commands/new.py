"""handoff new command.

Pre-allocates a run_id and returns the canonical .prompt.md path so the caller
can write the prompt directly to its final archive location before dispatching.

Usage:
  handoff new --backend <name> [--slug <slug>] [--write]

Stdout: one line — absolute path to the .prompt.md file.
By default the file is not created. With --write, stdin is written to the file.
"""

from __future__ import annotations

import os
import sys
import datetime

from ..core import (
    get_db,
    alloc_seq,
    backend_abbrev,
    slug_clean,
    TASKS_DIR,
)
from ..config import Config


def cmd_new(argv: list[str], config: Config):
    """handoff new --backend <name> [--slug <slug>] [--write]"""
    backend_arg = ""
    slug_arg = ""
    write_prompt = False

    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--backend":
            i += 1
            if i >= len(argv):
                print("handoff new: --backend requires a value", file=sys.stderr)
                sys.exit(2)
            backend_arg = argv[i]
        elif a.startswith("--backend="):
            backend_arg = a.split("=", 1)[1]
        elif a == "--slug":
            i += 1
            if i >= len(argv):
                print("handoff new: --slug requires a value", file=sys.stderr)
                sys.exit(2)
            slug_arg = argv[i]
        elif a.startswith("--slug="):
            slug_arg = a.split("=", 1)[1]
        elif a == "--write":
            write_prompt = True
        elif a in ("-h", "--help"):
            from ..main import usage
            usage()
            sys.exit(0)
        elif a.startswith("-"):
            print(f"handoff new: unknown option {a}", file=sys.stderr)
            sys.exit(2)
        i += 1

    backend_name = backend_arg or config.default_backend
    if not backend_name:
        print("handoff new: --backend is required (or set a default backend in config)", file=sys.stderr)
        sys.exit(2)

    # Validate backend exists in config
    backend_cfg = config.get_backend(backend_name)
    if not backend_cfg:
        print(
            f"handoff new: unknown backend '{backend_name}'. "
            f"Available: {', '.join(sorted(config.backends.keys()))}",
            file=sys.stderr,
        )
        sys.exit(2)

    b2 = backend_abbrev(backend_name)
    clean_slug = slug_clean(slug_arg) if slug_arg else "task"

    mmdd = datetime.date.today().strftime("%m%d")

    conn = get_db()
    _n, seq_code = alloc_seq(conn)
    conn.close()

    run_id = f"{mmdd}-{b2}-{seq_code}-{clean_slug}"
    prompt_path = os.path.join(TASKS_DIR, f"{run_id}.prompt.md")

    if write_prompt:
        if sys.stdin.isatty():
            print("handoff new: --write requires prompt text on stdin", file=sys.stderr)
            sys.exit(2)
        os.makedirs(os.path.dirname(prompt_path), exist_ok=True)
        with open(prompt_path, "w") as f:
            f.write(sys.stdin.read())

    print(prompt_path)
