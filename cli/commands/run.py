"""handoff run command."""

from __future__ import annotations

import os
import sys
import datetime

from ..core import (
    get_db, create_run, task_paths, UUID_RE,
    TASKS_DIR, parse_new_run_id, backend_abbrev,
)
from ..backend import (
    set_backend_env,
    build_args,
    backend_type,
    ensure_backend_token_ready,
    resolve_backend_model,
    wrap_with_pty,
)
from ..stream import execute_run
from ..config import Config


def _is_adopted_path(input_src: str) -> bool:
    """Return True if input_src is a .prompt.md file inside TASKS_DIR with new run_id format."""
    if not input_src or input_src == "-":
        return False
    abs_src = os.path.abspath(input_src)
    tasks_dir = os.path.abspath(TASKS_DIR)
    if not abs_src.startswith(tasks_dir + os.sep):
        return False
    basename = os.path.basename(abs_src)
    if not basename.endswith(".prompt.md"):
        return False
    stem = basename[: -len(".prompt.md")]
    return parse_new_run_id(stem) is not None


def cmd_run(argv: list[str], config: Config):
    """handoff run [--backend <name>] [--cwd <dir>] [--pro] (<input-file|-> | --text <prompt...>)."""
    pro = False
    cwd = ""
    backend_arg = ""
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
            i += 1
            if i >= len(argv):
                print("handoff run: --backend requires a value", file=sys.stderr)
                sys.exit(2)
            backend_arg = argv[i]
        elif a.startswith("--backend="):
            backend_arg = a.split("=", 1)[1]
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

    # Determine prompt source and whether to adopt a pre-allocated run_id.
    adopted_run_id: str | None = None

    if text_mode:
        if not text_parts:
            print("handoff run: --text requires a value", file=sys.stderr)
            sys.exit(2)
        prompt_text = " ".join(text_parts)
        if not prompt_text:
            print("handoff run: --text requires a non-empty value", file=sys.stderr)
            sys.exit(2)
        slug = "from-text"
    elif input_src == "-" or (not input_src and not sys.stdin.isatty()):
        prompt_text = sys.stdin.read()
        slug = "from-stdin"
    elif input_src:
        if not os.path.isfile(input_src):
            print(f"handoff run: input file not found: {input_src}", file=sys.stderr)
            sys.exit(2)

        if _is_adopted_path(input_src):
            # Adopt: file is already at the canonical tasks/ path with new format.
            stem = os.path.basename(input_src)[: -len(".prompt.md")]
            parsed = parse_new_run_id(stem)  # guaranteed non-None by _is_adopted_path
            _mmdd, file_b2, _seq_code, _slug = parsed  # type: ignore[misc]

            # Validate backend2 consistency.
            backend_name_candidate = backend_arg or config.default_backend
            expected_b2 = backend_abbrev(backend_name_candidate)
            if file_b2 != expected_b2:
                print(
                    f"handoff run: adopted file has backend '{file_b2}' but "
                    f"--backend resolves to '{backend_name_candidate}' (abbrev '{expected_b2}'). "
                    f"Use --backend matching the file's backend.",
                    file=sys.stderr,
                )
                sys.exit(2)

            with open(input_src) as f:
                prompt_text = f.read()
            adopted_run_id = stem
            slug = _slug  # unused when adopting, but kept for clarity
        else:
            with open(input_src) as f:
                prompt_text = f.read()
            slug = "from-file"
    else:
        print("handoff run: input file required, or use --text <prompt...> / pipe via '-'", file=sys.stderr)
        sys.exit(2)

    backend_name = backend_arg or config.default_backend

    _execute(cwd, prompt_text, backend_name, pro, config, slug=slug, adopted_run_id=adopted_run_id)


def _execute(
    cwd: str,
    prompt_text: str,
    backend_name: str,
    pro: bool,
    config: Config,
    resume_session_id: str | None = None,
    slug: str = "task",
    adopted_run_id: str | None = None,
):
    """Shared execution path for file, stdin, and --text run modes.

    When `resume_session_id` is given, the new run is appended to that existing
    claude conversation (`claude -p ... --resume <id>`) rather than starting a
    fresh session; the new row still gets its own run_id/seq/files but shares the
    session_id. Used by `handoff resume <seq> <prompt>`.

    When `adopted_run_id` is given, the pre-allocated run_id from `handoff new`
    is adopted: the seq counter is NOT re-incremented, and the prompt file is
    already at the canonical tasks/ path (not written again).
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

    # Check for duplicate dispatch when adopting a pre-allocated run_id.
    if adopted_run_id:
        existing = conn.execute(
            "SELECT run_id FROM runs WHERE run_id = ?", (adopted_run_id,)
        ).fetchone()
        if existing:
            conn.close()
            print(
                f"handoff run: run_id '{adopted_run_id}' already exists in DB — "
                f"duplicate dispatch rejected.",
                file=sys.stderr,
            )
            sys.exit(2)

    run_id, uid, jsonl_path = create_run(
        conn, cwd, prompt_text, backend_name,
        session_id=resume_session_id,
        slug=slug,
        run_id_override=adopted_run_id,
    )
    conn.commit()

    # tasks dir files
    prompt_path, out_path, result_path = task_paths(run_id)

    # Write prompt file only when not adopting (adopted file is already in place).
    if not adopted_run_id:
        with open(prompt_path, "w") as pf:
            pf.write(prompt_text)

    # Resolve model
    model = resolve_backend_model(backend_cfg, pro)
    if not model:
        print(
            f"handoff: backend '{backend_name}' resolves no model. "
            f"Set backends.{backend_name}.model in {config.user_config_path} "
            f"(pre-0.3 configs carried this in the now-removed top-level default_model).",
            file=sys.stderr,
        )
        sys.exit(2)
    backend_cfg["_resolved_model"] = model
    backend_cfg["_system_prompt"] = config.system_prompt

    btype = backend_type(backend_cfg)
    set_backend_env(backend_cfg, model, backend_cfg.get("pro_model", ""))
    if resume_session_id:
        session_id = resume_session_id
    elif btype == "claude":
        session_id = uid if UUID_RE.match(uid) else None
    else:
        # codex assigns the thread id itself; it arrives via the
        # thread.started event and is persisted by execute_run
        session_id = None

    print(f"RESULT={result_path}")
    print(f"RESULT={result_path}", file=sys.stderr)

    ts = datetime.datetime.now().strftime("%H:%M:%S")
    label = "resume" if resume_session_id else "start"
    print(f"{ts} {label}\tSESSION={session_id or 'pending'}", file=sys.stderr)

    # build backend command (wrapped in script for pty when the type needs it)
    backend_cmd = build_args(
        backend_cfg, prompt_text, session_id,
        model=model,
        pro_model=backend_cfg.get("pro_model", ""),
        resume=bool(resume_session_id),
        cwd=cwd,
    )
    cmd = wrap_with_pty(backend_cfg, backend_cmd)

    execute_run(
        cwd,
        prompt_text,
        cmd,
        conn,
        uid,
        jsonl_path,
        (prompt_path, out_path, result_path),
        backend_type=btype,
    )
