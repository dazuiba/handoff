"""ds-cli start command."""

import os
import sys

from ..core import get_db, create_run, task_paths, UUID_RE
from ..backend import set_backend_env, build_claude_args, resolve_backend_model, wrap_with_pty
from ..stream import run_claude_foreground, run_claude_background
from ..config import Config


def cmd_start(argv: list[str], config: Config):
    """ds-cli start [--cwd <dir>] <input-file> [--backend <name>] [--pro] [--fg] [-o <jsonl-file>]"""
    backend_name = ""
    pro = False
    fg = False
    cwd = ""
    input_src = ""
    output = ""

    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--cwd":
            i += 1
            if i >= len(argv):
                print("ds-cli start: --cwd requires a value", file=sys.stderr)
                sys.exit(2)
            cwd = argv[i]
        elif a == "-o":
            i += 1
            if i >= len(argv):
                print("ds-cli start: -o requires a value", file=sys.stderr)
                sys.exit(2)
            output = argv[i]
        elif a == "--backend":
            i += 1
            if i >= len(argv):
                print("ds-cli start: --backend requires a value", file=sys.stderr)
                sys.exit(2)
            backend_name = argv[i]
        elif a == "--pro":
            pro = True
        elif a == "--fg":
            fg = True
        elif a == "--fast":
            print(
                "ds-cli: --fast is removed; use '--backend <name>' instead. "
                "Configure a 'fast' backend in ~/.ds-cli/config.yaml",
                file=sys.stderr,
            )
            sys.exit(2)
        elif a in ("-h", "--help"):
            from ..main import usage
            usage()
            sys.exit(0)
        elif a == "--":
            i += 1
            if i < len(argv):
                input_src = argv[i]
            break
        elif a.startswith("-"):
            print(f"ds-cli start: unknown option {a}", file=sys.stderr)
            sys.exit(2)
        else:
            input_src = a
        i += 1

    if not cwd:
        cwd = os.getcwd()
    if not os.path.isdir(cwd):
        print(f"ds-cli start: cwd not found: {cwd}", file=sys.stderr)
        sys.exit(2)
    if not input_src:
        print("ds-cli start: input file required", file=sys.stderr)
        sys.exit(2)
    if not os.path.isfile(input_src):
        print(f"ds-cli start: input file not found: {input_src}", file=sys.stderr)
        sys.exit(2)

    if not backend_name:
        backend_name = config.default_backend

    with open(input_src) as f:
        prompt_text = f.read()

    conn = get_db()
    run_id, uid, jsonl_path = create_run(conn, cwd, prompt_text, backend_name)

    if output:
        jsonl_path = output
        conn.execute(
            "UPDATE runs SET jsonl_path = ? WHERE uuid = ?", (output, uid)
        )
    conn.commit()

    backend_cfg = config.get_backend(backend_name)
    if not backend_cfg:
        print(
            f"ds-cli: unknown backend '{backend_name}'. "
            f"Available: {', '.join(sorted(config.backends.keys()))}",
            file=sys.stderr,
        )
        sys.exit(2)

    model = resolve_backend_model(backend_cfg, config.default_model, config.pro_model, pro)
    backend_cfg["_resolved_model"] = model
    backend_cfg["_system_prompt"] = config.system_prompt

    set_backend_env(backend_cfg, config.default_model, config.pro_model, model)
    session_id = uid if UUID_RE.match(uid) else None

    print(f"SESSION={uid}", file=sys.stderr)
    print(f"JSONL={jsonl_path}", file=sys.stderr)

    claude_cmd = build_claude_args(
        backend_cfg, prompt_text, session_id,
        model=model,
        default_model=config.default_model,
        pro_model=config.pro_model,
    )

    wrapped_cmd = wrap_with_pty(backend_cfg, claude_cmd)
    pt = task_paths(run_id)

    if fg:
        run_claude_foreground(cwd, prompt_text, session_id, jsonl_path, wrapped_cmd, conn, uid, pt)
    else:
        run_claude_background(cwd, prompt_text, session_id, jsonl_path, wrapped_cmd)

    # run_claude_background returns immediately (Popen, no wait)
    # run_claude_foreground updates status inline. For bg, we still set status.
    conn.execute("UPDATE runs SET status = ? WHERE uuid = ?", ("done", uid))
    conn.commit()
    conn.close()
