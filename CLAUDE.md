# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What ds-cli is

A CLI proxy for `claude` that dispatches coding tasks to configurable AI backends (default: DeepSeek API using anthropic-compatible endpoints). Users invoke it as a Claude Code skill (`/ds-cli`) or Codex subagent (`ds-agent`), rarely typing `ds-cli` directly.

## Commands

```bash
# Install: uv tool install -e .  then run init
handoff --help

# Dispatch a task
echo "Refactor X and add tests" | handoff run -
handoff run --text "smoke test"
handoff run --fast --pro - <<'EOF'
...prompt...
EOF

# Browse/manage past runs
handoff list             # interactive TUI (curses) when stdout is a terminal
handoff resume <seq>     # reopen a past conversation interactively in claude
handoff resume <seq> -   # dispatch a follow-up task to that conversation (heredoc)
handoff tail <run-id>    # live-tail a run's output stream

# Initial setup (creates ~/.handoff/config.yaml, symlinks skill/agent files)
handoff init -y
```

There are no test suites or linting setup in this repo.

## Architecture

### Entry point

`ds-cli` (root) is a thin script with `#!/usr/bin/env -S uv run --script` and PEP 723 inline metadata. It adds the `cli/` dir to `sys.path` and calls `cli.main.main()`.

### Command dispatch (`cli/main.py`)

`main()` parses `sys.argv[1]` and dispatches to the matching `cli/commands/<subcmd>.py`. Known commands: `run`, `list`, `resume`, `tail`, `install`, `update`. Non-install/update commands trigger `Config()` initialization (validates user config, creates DB).

### Config (`cli/config.py`)

Two-layer deep merge: `cli/default_config.yaml` (bundled) → `~/.ds-cli/config.yaml` (user). User config only needs overrides. Backend resolution: `backends.<name>` is deep-merged onto `backend_template` so every backend inherits defaults (claude flags, PTY wrapper, env vars). `default_backend` / `fast_backend` keys select which backend `run` and `resume` use. The user config supports `include:` directives with cycle detection.

### State (`cli/core.py`)

All state lives under `~/.ds-cli/`:
- `runs/dscli.db` — SQLite (WAL mode) with `runs` table (seq, run_id, uuid, session_id, cwd, prompt, jsonl_path, status, backend) and `run_counters` (daily auto-increment per day). `session_id` is the underlying claude conversation: equals `uuid` for a fresh run, or the parent's `session_id` for a `resume` continuation. `get_db()` performs an in-place `ALTER TABLE` migration to add `session_id` (backfilled from `uuid`) on old databases.
- `tasks/` — per-run files: `{run_id}.prompt.txt`, `.out.txt` (progress), `.result.md` (final)
- Run IDs: `ds-<MMDD>-<SEQ_CODE>` where SEQ_CODE is a 2-char encoding: `01`–`99` for 1–99, then `A0`–`ZZ` for 100–1035

### Backend resolution (`cli/backend.py`)

Functions that set environment variables and build `claude` CLI argument lists from resolved backend configs. Placeholder substitution supports `{model}`, `{prompt}`, `{session_id}`, `{system_prompt}`, `{default_model}`, `{pro_model}`, `{home}`. `build_claude_args()` produces the `claude -p <prompt> --output-format stream-json ...` invocation; with `resume=True` it emits `continue_id_flags` (`--resume {session_id}`) instead of `session_id_flags` (`--session-id {session_id}`), turning the same pipeline into a non-interactive continuation of an existing conversation. `build_resume_args()` builds the interactive `claude --resume` invocation (no `-p`). `wrap_with_pty()` wraps it in `script -q /dev/null`.

### Execution pipeline (`cli/stream.py`)

`execute_run()` — the core of `run`:
1. Spawns `claude` (with PTY wrapper) as a subprocess, stdout captured
2. For each JSONL line from claude: writes line to `.jsonl` file, parses assistant plan text for stderr progress, writes progress to `.out.txt`
3. On `type: "result"` with `is_error: false`, extracts result text → writes `.result.md`; default mode also prints the result text to stdout
4. `run` prints `RESULT=<abs-path-to-result.md>` to both stdout and stderr at startup; stderr carries progress and a final `RESULT=` marker, while stdout prints the final result text for normal shell users

### Resume / continuation (`cli/commands/resume.py`)

`ds-cli resume <seq>` unifies "reopen a past conversation". It resolves the target via `find_run()` (by seq or run-id; empty → latest) and reads the row's `session_id`.
- **No prompt input** → interactive: `build_resume_args()` + `os.execvp` into `claude --resume` (the old `go` behavior).
- **With prompt input** (`-`/heredoc, `--text`, or a file arg after the selector) → non-interactive continuation: calls `run._execute(..., resume_session_id=session_id)`, which allocates a *new* run row (new run_id/seq/files) carrying the parent's `session_id`, then runs the normal `execute_run` pipeline with `claude -p <prompt> --resume <session_id>`.

Because `--resume` does not fork, the session_id is stable, so the **original seq stays a valid handle** for every later turn. Flags mirror `run` (`--fast`/`--pro`/`--cwd`); backend defaults to the conversation's saved backend unless `--fast` overrides. There is no separate `go` command.

### TUI (`cli/tui.py`)

Textual-based interactive listing for `ds-cli list`. Renders a scrollable `DataTable` of runs, supports detail view (shows prompt + parsed JSONL event stream), resume (`G`), and copy session UUID (`C` → pbcopy). Auto-refreshes via a `set_interval(POLL_INTERVAL=2.0s, …)` timer that re-queries the DB (`refresh_fn` passed from `cmd_list`); a lightweight `run_id:status` fingerprint gates rebuilds, the cursor is preserved by `run_id`, and rebuilds are deferred (`_dirty` + `_on_screen_resume`) while the detail view is on top so the user isn't kicked back. The DB connection stays open for the app's lifetime in TUI mode.

### Skill/subagent files

- `SKILL.md` — Claude Code skill definition with an interaction contract (heredoc template, always `run_in_background: true`, capture `RESULT=` path, read `.result.md` on completion)
- `ds-agent.toml` — Codex subagent definition (model, instructions to forward the prompt file via `ds-cli run <prompt-file> >/dev/null`, preserving stderr progress while dropping final stdout result text)

### Default config (`cli/default_config.yaml`)

Models: `deepseek-v4-flash` (default), `deepseek-v4-pro[1m]` (pro). Backend template includes `--dangerously-skip-permissions`, `--output-format stream-json`, `--verbose`, `--include-partial-messages`. System prompt directs the model to execute without asking for confirmation.

## Key constraints

- No `--backend` flag — normal/fast mode backend selection is config-driven
- `ensure_backend_token_ready()` blocks execution if token is still a placeholder (`<...>`)
- Max 1035 runs per day (ZZ seq_code limit)
- Statuses: `running`, `success`, `error`, `interrupted`
