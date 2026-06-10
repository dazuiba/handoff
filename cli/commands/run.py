"""handoff run command."""

from __future__ import annotations

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
    """handoff run [--cwd <dir>] [--fast] [--pro] (<input-file|-> | --text <prompt...>)."""
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
                print("handoff run: --cwd requires a value", file=sys.stderr)
                sys.exit(2)
            cwd = argv[i]
        elif a == "--backend":
            print("handoff: --backend has been removed; use --fast or edit ~/.handoff/config.yaml", file=sys.stderr)
            sys.exit(2)
        elif a == "--text":
            text_mode = True
            if input_src:
                print("handoff run: --text cannot be combined with an input file", file=sys.stderr)
                sys.exit(2)
            if i + 1 >= len(argv):
                print("handoff run: --text requires a value", file=sys.stderr)
                sys.exit(2)
            if argv[i + 1] == "--":
                text_parts.extend(argv[i + 2:])
            else:
                text_parts.extend(argv[i + 1:])
            break
        elif a.startswith("--text="):
            text_mode = True
            if input_src:
                print("handoff run: --text cannot be combined with an input file", file=sys.stderr)
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
            print(f"handoff run: unknown option {a}", file=sys.stderr)
            sys.exit(2)
        else:
            if text_mode:
                print("handoff run: --text cannot be combined with an input file", file=sys.stderr)
                sys.exit(2)
            input_src = a
        i += 1

    if not cwd:
        cwd = os.getcwd()
    if not os.path.isdir(cwd):
        print(f"handoff run: cwd not found: {cwd}", file=sys.stderr)
        sys.exit(2)

    if text_mode:
        if not text_parts:
            print("handoff run: --text requires a value", file=sys.stderr)
            sys.exit(2)
        prompt_text = " ".join(text_parts)
        if not prompt_text:
            print("handoff run: --text requires a non-empty value", file=sys.stderr)
            sys.exit(2)
    elif input_src == "-" or (not input_src and not sys.stdin.isatty()):
        prompt_text = sys.stdin.read()
    elif input_src:
        if not os.path.isfile(input_src):
            print(f"handoff run: input file not found: {input_src}", file=sys.stderr)
            sys.exit(2)
        with open(input_src) as f:
            prompt_text = f.read()
    else:
        print("handoff run: input file required, or use --text <prompt...> / pipe via '-'", file=sys.stderr)
        sys.exit(2)

    backend_name = config.fast_backend if fast else config.default_backend

    _execute(cwd, prompt_text, backend_name, pro, config)


def _execute(
    cwd: str,
    prompt_text: str,
    backend_name: str,
    pro: bool,
    config: Config,
    resume_session_id: str | None = None,
):
    """Shared execution path for file, stdin, and --text run modes.

    When `resume_session_id` is given, the new run is appended to that existing
    claude conversation (`claude -p ... --resume <id>`) rather than starting a
    fresh session; the new row still gets its own run_id/seq/files but shares the
    session_id. Used by `handoff resume <seq> <prompt>`.
    """
    backend_cfg = config.get_backend(backend_name)
    if not backend_cfg:
        print(
            f"handoff: unknown backend '{backend_name}'. "
            f"Available: {', '.join(sorted(config.backends.keys()))}",
            file=sys.stderr,
        )
        sys.exit(2)

    ensure_backend_token_ready(backend_name, backend_cfg, config.user_config_path)

    conn = get_db()
    run_id, uid, jsonl_path = create_run(
        conn, cwd, prompt_text, backend_name, session_id=resume_session_id
    )
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
    if resume_session_id:
        session_id = resume_session_id
    else:
        session_id = uid if UUID_RE.match(uid) else None

    print(f"RESULT={result_path}")
    print(f"RESULT={result_path}", file=sys.stderr)

    ts = datetime.datetime.now().strftime("%H:%M:%S")
    label = "resume" if resume_session_id else "start"
    print(f"{ts} {label}\tSESSION={session_id}", file=sys.stderr)

    # build claude command (wrapped in script for pty)
    claude_cmd = build_claude_args(
        backend_cfg, prompt_text, session_id,
        model=model,
        default_model=config.default_model,
        pro_model=config.pro_model,
        resume=bool(resume_session_id),
    )
    cmd = wrap_with_pty(backend_cfg, claude_cmd)

    execute_run(
        cwd,
        prompt_text,
        cmd,
        conn,
        uid,
        jsonl_path,
        (prompt_path, out_path, result_path),
    )
