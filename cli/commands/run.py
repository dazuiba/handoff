"""ds-cli run command."""

import os
import sys
import datetime

from ..core import get_db, create_run, task_paths, UUID_RE
from ..backend import (
    set_backend_env,
    build_claude_args,
    ensure_backend_token_ready,
    resolve_backend_model,
    wrap_with_pty,
)
from ..stream import execute_run
from ..config import Config


def cmd_run(argv: list[str], config: Config):
    """ds-cli run [--cwd <dir>] [--fast] [--pro] (<input-file|-> | --text <prompt...>)."""
    fast = False
    pro = False
    cwd = ""
    input_src = ""
    text_mode = False
    text_parts = []

    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "-":
            input_src = "-"
        elif a == "--cwd":
            i += 1
            if i >= len(argv):
                print("ds-cli run: --cwd requires a value", file=sys.stderr)
                sys.exit(2)
            cwd = argv[i]
        elif a == "--backend":
            print("ds-cli: --backend has been removed; use --fast or edit ~/.ds-cli/config.yaml", file=sys.stderr)
            sys.exit(2)
        elif a == "--text":
            text_mode = True
            if input_src:
                print("ds-cli run: --text cannot be combined with an input file", file=sys.stderr)
                sys.exit(2)
            if i + 1 >= len(argv):
                print("ds-cli run: --text requires a value", file=sys.stderr)
                sys.exit(2)
            if argv[i + 1] == "--":
                text_parts.extend(argv[i + 2:])
            else:
                text_parts.extend(argv[i + 1:])
            break
        elif a.startswith("--text="):
            text_mode = True
            if input_src:
                print("ds-cli run: --text cannot be combined with an input file", file=sys.stderr)
                sys.exit(2)
            text_parts.append(a.split("=", 1)[1])
            text_parts.extend(argv[i + 1:])
            break
        elif a == "--pro":
            pro = True
        elif a in ("-h", "--help"):
            from ..main import usage
            usage()
            sys.exit(0)
        elif a == "--fast":
            fast = True
        elif a == "--":
            i += 1
            if i < len(argv):
                input_src = argv[i]
            break
        elif a.startswith("-"):
            print(f"ds-cli run: unknown option {a}", file=sys.stderr)
            sys.exit(2)
        else:
            if text_mode:
                print("ds-cli run: --text cannot be combined with an input file", file=sys.stderr)
                sys.exit(2)
            input_src = a
        i += 1

    if not cwd:
        cwd = os.getcwd()
    if not os.path.isdir(cwd):
        print(f"ds-cli run: cwd not found: {cwd}", file=sys.stderr)
        sys.exit(2)

    if text_mode:
        if not text_parts:
            print("ds-cli run: --text requires a value", file=sys.stderr)
            sys.exit(2)
        prompt_text = " ".join(text_parts)
        if not prompt_text:
            print("ds-cli run: --text requires a non-empty value", file=sys.stderr)
            sys.exit(2)
    elif input_src == "-" or (not input_src and not sys.stdin.isatty()):
        prompt_text = sys.stdin.read()
    elif input_src:
        if not os.path.isfile(input_src):
            print(f"ds-cli run: input file not found: {input_src}", file=sys.stderr)
            sys.exit(2)
        with open(input_src) as f:
            prompt_text = f.read()
    else:
        print("ds-cli run: input file required, or use --text <prompt...> / pipe via '-'", file=sys.stderr)
        sys.exit(2)

    backend_name = config.fast_backend if fast else config.default_backend

    _execute(cwd, prompt_text, backend_name, pro, config)


def _execute(cwd: str, prompt_text: str, backend_name: str, pro: bool, config: Config):
    """Shared execution path for file, stdin, and --text run modes."""
    backend_cfg = config.get_backend(backend_name)
    if not backend_cfg:
        print(
            f"ds-cli: unknown backend '{backend_name}'. "
            f"Available: {', '.join(sorted(config.backends.keys()))}",
            file=sys.stderr,
        )
        sys.exit(2)

    ensure_backend_token_ready(backend_name, backend_cfg, config.user_config_path)

    conn = get_db()
    run_id, uid, jsonl_path = create_run(conn, cwd, prompt_text, backend_name)
    conn.commit()

    # tasks dir files
    prompt_path, out_path, result_path = task_paths(run_id)

    with open(prompt_path, "w") as pf:
        pf.write(prompt_text)

    # Resolve model
    model = resolve_backend_model(backend_cfg, config.default_model, config.pro_model, pro)
    backend_cfg["_resolved_model"] = model
    backend_cfg["_system_prompt"] = config.system_prompt

    set_backend_env(backend_cfg, config.default_model, config.pro_model, model)
    session_id = uid if UUID_RE.match(uid) else None

    print(f"RESULT={result_path}")
    print(f"RESULT={result_path}", file=sys.stderr)

    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"{ts} start\tSESSION={uid}", file=sys.stderr)

    # build claude command (wrapped in script for pty)
    claude_cmd = build_claude_args(
        backend_cfg, prompt_text, session_id,
        model=model,
        default_model=config.default_model,
        pro_model=config.pro_model,
    )
    cmd = wrap_with_pty(backend_cfg, claude_cmd)

    execute_run(cwd, prompt_text, cmd, conn, uid, jsonl_path, (prompt_path, out_path, result_path))
