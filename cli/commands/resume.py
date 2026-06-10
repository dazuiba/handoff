"""handoff resume command.

Unifies "reopen a past conversation" into one verb, keyed by seq (or run-id):

  handoff resume <seq>                  — interactive: drop into `claude --resume`
  handoff resume <seq> - <<'EOF' ...    — non-interactive: dispatch a new task to
  handoff resume <seq> --text "..."       that same conversation (claude -p --resume),
                                          running through the normal run pipeline.

The seq → session mapping comes from the runs table: the selected row's
`session_id` is the underlying claude conversation. `--resume` does not fork, so
the original seq stays a stable handle — keep using it to add more turns.
"""

import os
import sys
import shlex

from ..core import get_db, find_run, short_path, row_value
from ..backend import set_backend_env, build_resume_args, resolve_backend_model
from ..config import Config


def cmd_resume(argv: list[str], config: Config):
    """handoff resume [<run-id|seq>] [--fast] [--pro] [--cwd <dir>]
    [(<input-file|-> | --text <prompt...>)]."""
    fast = False
    pro = False
    cwd = ""
    selector = ""
    input_src = ""
    text_mode = False
    text_parts = []
    have_selector = False

    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "-":
            input_src = "-"
        elif a == "--cwd":
            i += 1
            if i >= len(argv):
                print("handoff resume: --cwd requires a value", file=sys.stderr)
                sys.exit(2)
            cwd = argv[i]
        elif a == "--backend":
            print("handoff: --backend has been removed; use --fast or edit ~/.handoff/config.yaml", file=sys.stderr)
            sys.exit(2)
        elif a == "--text":
            text_mode = True
            if input_src:
                print("handoff resume: --text cannot be combined with an input file", file=sys.stderr)
                sys.exit(2)
            if i + 1 >= len(argv):
                print("handoff resume: --text requires a value", file=sys.stderr)
                sys.exit(2)
            if argv[i + 1] == "--":
                text_parts.extend(argv[i + 2:])
            else:
                text_parts.extend(argv[i + 1:])
            break
        elif a.startswith("--text="):
            text_mode = True
            if input_src:
                print("handoff resume: --text cannot be combined with an input file", file=sys.stderr)
                sys.exit(2)
            text_parts.append(a.split("=", 1)[1])
            text_parts.extend(argv[i + 1:])
            break
        elif a == "--pro":
            pro = True
        elif a == "--fast":
            fast = True
        elif a in ("-h", "--help"):
            from ..main import usage
            usage()
            sys.exit(0)
        elif a.startswith("-") and a != "-":
            print(f"handoff resume: unknown option {a}", file=sys.stderr)
            sys.exit(2)
        else:
            # First bare positional is the selector (seq/run-id); a second one is
            # an input file (prompt source).
            if not have_selector:
                selector = a
                have_selector = True
            elif text_mode:
                print("handoff resume: --text cannot be combined with an input file", file=sys.stderr)
                sys.exit(2)
            else:
                input_src = a
        i += 1

    # Resolve the target conversation.
    conn = get_db()
    row = find_run(conn, selector or None)

    if not row:
        conn.close()
        print("handoff resume: no run found", file=sys.stderr)
        sys.exit(1)

    session_id = row_value(row, "session_id", "") or row["uuid"]
    row_cwd = row["cwd"]
    saved_backend = row_value(row, "backend", "") or ""

    # Decide prompt source → interactive vs continuation.
    prompt_text = None
    if text_mode:
        prompt_text = " ".join(text_parts)
        if not prompt_text:
            print("handoff resume: --text requires a non-empty value", file=sys.stderr)
            sys.exit(2)
    elif input_src == "-" or (not input_src and not sys.stdin.isatty()):
        prompt_text = sys.stdin.read()
    elif input_src:
        if not os.path.isfile(input_src):
            print(f"handoff resume: input file not found: {input_src}", file=sys.stderr)
            sys.exit(2)
        with open(input_src) as f:
            prompt_text = f.read()

    if not cwd:
        cwd = row_cwd
    if not os.path.isdir(cwd):
        print(f"handoff resume: cwd not found: {cwd}", file=sys.stderr)
        sys.exit(2)

    # Backend: --fast wins; otherwise the conversation's saved backend, else default.
    if fast:
        backend_name = config.fast_backend
    else:
        backend_name = saved_backend or config.default_backend

    if prompt_text is None:
        # Interactive: reopen the conversation in claude (replaces this process).
        conn.close()
        _resume_interactive(config, backend_name, session_id, cwd, pro)
    else:
        # Non-interactive: dispatch a new turn through the run pipeline.
        conn.close()
        from .run import _execute
        _execute(cwd, prompt_text, backend_name, pro, config, resume_session_id=session_id)


def _resume_interactive(config: Config, backend_name: str, session_id: str, cwd: str, pro: bool):
    backend_cfg = config.get_backend(backend_name)
    if not backend_cfg:
        print(
            f"handoff: unknown backend '{backend_name}'. "
            f"Available: {', '.join(sorted(config.backends.keys()))}",
            file=sys.stderr,
        )
        sys.exit(2)

    model = resolve_backend_model(backend_cfg, config.default_model, config.pro_model, pro)
    backend_cfg["_resolved_model"] = model
    backend_cfg["_system_prompt"] = config.system_prompt

    set_backend_env(backend_cfg, config.default_model, config.pro_model, model)

    args = build_resume_args(
        backend_cfg, session_id,
        default_model=config.default_model,
        pro_model=config.pro_model,
    )

    print(f"cd {short_path(cwd)}; {' '.join(shlex.quote(p) for p in args)}", file=sys.stderr)
    os.chdir(cwd)
    os.execvp(args[0], args)
