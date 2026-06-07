# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What ds-cli is

A CLI proxy for `claude` that dispatches coding tasks to configurable AI backends (default: DeepSeek API using anthropic-compatible endpoints). Users invoke it as a Claude Code skill (`/ds-cli`) or Codex subagent (`ds-agent`), rarely typing `ds-cli` directly.

## Commands

```bash
# No install needed if uv is on PATH — the entry point uses PEP 723 inline metadata
./ds-cli --help

# Dispatch a task
echo "Refactor X and add tests" | ./ds-cli run -
./ds-cli run --text "smoke test"
./ds-cli run --fast --pro - <<'EOF'
...prompt...
EOF

# Browse/manage past runs
./ds-cli list          # interactive TUI (curses) when stdout is a terminal
./ds-cli go <run-id>   # resume a past session
./ds-cli tail <run-id> # live-tail a run's output stream

# Update from git
./ds-cli update

# Initial setup (creates ~/.ds-cli/config.yaml, symlinks skill/agent files)
./ds-cli install -y
```

There are no test suites or linting setup in this repo.

## Architecture

### Entry point

`ds-cli` (root) is a thin script with `#!/usr/bin/env -S uv run --script` and PEP 723 inline metadata. It adds the `cli/` dir to `sys.path` and calls `cli.main.main()`.

### Command dispatch (`cli/main.py`)

`main()` parses `sys.argv[1]` and dispatches to the matching `cli/commands/<subcmd>.py`. Known commands: `run`, `list`, `go`, `tail`, `install`, `update`. Non-install/update commands trigger `Config()` initialization (validates user config, creates DB).

### Config (`cli/config.py`)

Two-layer deep merge: `cli/default_config.yaml` (bundled) → `~/.ds-cli/config.yaml` (user). User config only needs overrides. Backend resolution: `backends.<name>` is deep-merged onto `backend_template` so every backend inherits defaults (claude flags, PTY wrapper, env vars). `default_backend` / `fast_backend` keys select which backend `run` and `go` use. The user config supports `include:` directives with cycle detection.

### State (`cli/core.py`)

All state lives under `~/.ds-cli/`:
- `runs/dscli.db` — SQLite (WAL mode) with `runs` table (seq, run_id, uuid, cwd, prompt, jsonl_path, status, backend) and `run_counters` (daily auto-increment per day)
- `tasks/` — per-run files: `{run_id}.prompt.txt`, `.out.txt` (progress), `.result.md` (final)
- Run IDs: `ds-<SEQ_CODE>-<MMDD>` where SEQ_CODE is a 2-char encoding: `01`–`99` for 1–99, then `A0`–`ZZ` for 100–1035

### Backend resolution (`cli/backend.py`)

Functions that set environment variables and build `claude` CLI argument lists from resolved backend configs. Placeholder substitution supports `{model}`, `{prompt}`, `{session_id}`, `{system_prompt}`, `{default_model}`, `{pro_model}`, `{home}`. `build_claude_args()` produces the `claude -p <prompt> --output-format stream-json ...` invocation. `wrap_with_pty()` wraps it in `script -q /dev/null`.

### Execution pipeline (`cli/stream.py`)

`execute_run()` — the core of `run`:
1. Spawns `claude` (with PTY wrapper) as a subprocess, stdout captured
2. For each JSONL line from claude: writes line to `.jsonl` file, parses assistant plan text for stderr progress, writes progress to `.out.txt`
3. On `type: "result"` with `is_error: false`, extracts result text → writes `.result.md` and prints to stdout
4. `RESULT=<abs-path-to-result.md>` is printed to both stdout and stderr so callers can capture it

### TUI (`cli/tui.py`)

Curses-based interactive listing for `ds-cli list`. Renders a scrollable table of runs, supports detail view (shows prompt + parsed JSONL event stream), resume (`G`), and copy session UUID (`C` → pbcopy).

### Skill/subagent files

- `SKILL.md` — Claude Code skill definition with an interaction contract (heredoc template, always `run_in_background: true`, capture `RESULT=` path, read `.result.md` on completion)
- `ds-agent.toml` — Codex subagent definition (model, instructions to forward everything via `ds-cli run -` heredoc)

### Default config (`cli/default_config.yaml`)

Models: `deepseek-v4-flash` (default), `deepseek-v4-pro[1m]` (pro). Backend template includes `--dangerously-skip-permissions`, `--output-format stream-json`, `--verbose`, `--include-partial-messages`. System prompt directs the model to execute without asking for confirmation.

## Key constraints

- No `--backend` flag — normal/fast mode backend selection is config-driven
- `ensure_backend_token_ready()` blocks execution if token is still a placeholder (`<...>`)
- Max 1035 runs per day (ZZ seq_code limit)
- Statuses: `running`, `success`, `error`, `interrupted`
