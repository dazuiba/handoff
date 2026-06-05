"""ds-cli go command."""

import os
import sys
import shlex

from ..core import get_db, find_run, short_path, row_value
from ..backend import set_backend_env, build_resume_args, resolve_backend_model
from ..config import Config


def cmd_go(argv: list[str], config: Config):
    """ds-cli go [<run-id|seq>] [--backend <name>]"""
    backend_name = ""
    selector = ""

    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--backend":
            i += 1
            if i >= len(argv):
                print("ds-cli go: --backend requires a value", file=sys.stderr)
                sys.exit(2)
            backend_name = argv[i]
        elif a in ("-h", "--help"):
            from ..main import usage
            usage()
            sys.exit(0)
        elif a.startswith("-"):
            print(f"ds-cli go: unknown option {a}", file=sys.stderr)
            sys.exit(2)
        else:
            selector = a
        i += 1

    conn = get_db()
    row = find_run(conn, selector or None)
    conn.close()

    if not row:
        print("ds-cli go: no run found", file=sys.stderr)
        sys.exit(1)

    # Determine backend: saved backend, explicit override, or default
    if not backend_name:
        backend_name = row_value(row, "backend", "") or config.default_backend

    backend_cfg = config.get_backend(backend_name)
    if not backend_cfg:
        print(
            f"ds-cli: unknown backend '{backend_name}'. "
            f"Available: {', '.join(sorted(config.backends.keys()))}",
            file=sys.stderr,
        )
        sys.exit(2)

    model = resolve_backend_model(backend_cfg, config.default_model, config.pro_model, False)
    backend_cfg["_resolved_model"] = model
    backend_cfg["_system_prompt"] = config.system_prompt

    set_backend_env(backend_cfg, config.default_model, config.pro_model, model)

    cwd = row["cwd"]
    uid = row["uuid"]
    args = build_resume_args(
        backend_cfg, uid,
        default_model=config.default_model,
        pro_model=config.pro_model,
    )

    print(f"cd {short_path(cwd)}; {' '.join(shlex.quote(p) for p in args)}", file=sys.stderr)
    os.chdir(cwd)
    os.execvp(args[0], args)
