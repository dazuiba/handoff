# Design notes: codex backend integration

These notes record the stage-2 research (`plans/handoff/02-multi-backend.md` §0) that
drove the codex backend implementation. Measured against the locally installed
`codex-cli 0.139.0` plus the official non-interactive docs
(<https://developers.openai.com/codex/noninteractive>). Do not re-derive from memory —
re-run the probes below if the codex CLI is upgraded.

## 1. Machine-readable output (`codex exec --json`)

`codex exec --json [PROMPT]` prints one JSON object per line (JSONL) — the
**experimental event schema**. Event taxonomy (confirmed from the binary's embedded
strings and live output):

| event `type`      | meaning / fields |
| ----------------- | ---------------- |
| `thread.started`  | `{"thread_id": "<uuid>"}` — the session id (see §2) |
| `turn.started`    | turn begins (no useful fields) |
| `item.started`    | `{"item": {"id", "type", "status": "in_progress", ...}}` |
| `item.updated`    | same shape as item.started, incremental |
| `item.completed`  | `{"item": {"id", "type", ...}}` — terminal per item |
| `turn.completed`  | `{"usage": {"input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens"}}` |
| `turn.failed`     | `{"error": {"message": "..."}}` |
| `error`           | `{"message": "..."}` — transient/connection errors (e.g. reconnect retries) |

**Item types** (the `item.type` field): `agent_message`, `reasoning`,
`command_execution`, `file_change`, `mcp_tool_call`, `web_search`, `todo_list`
(plan updates). Observed shapes:

- `agent_message` → `{"type":"agent_message","text":"<final assistant text>"}`.
  **The final result text is the `text` of the last `agent_message` `item.completed`.**
- `command_execution` → `{"type":"command_execution","command":"bash -lc ls","status":"in_progress|completed","exit_code"?,"aggregated_output"?}`.
- `reasoning` → carries summarized reasoning text.

Mapping to handoff's three stream events:

- `session(id)` ← `thread.started.thread_id`
- `progress(text)` ← `item.*` for `agent_message` (text), `reasoning`, `command_execution`
  (command line). Unknown item types are skipped (forward-compatible).
- `result(text, is_error)` ← last `agent_message` text on `turn.completed`
  (`is_error=False`); on `turn.failed`/`error` → `is_error=True` with the error message.

The parser keys only off these documented stable fields and degrades gracefully
(unknown `type`/`item.type` ignored), so it survives minor schema drift.

## 2. Non-interactive resume — does NOT fork

`codex exec resume <SESSION_ID> [PROMPT]` exists and accepts `--json`. The
`SESSION_ID` is the `thread_id` from `thread.started`.

**Measured: resume does not fork.** `codex exec resume <id> ...` re-emits
`thread.started` with the *same* `thread_id`:

```
$ codex exec resume --json --skip-git-repo-check <ID> "say hi"
{"type":"thread.started","thread_id":"<same ID>"}
```

→ The first session id is a stable handle for every later turn, exactly like
claude's `--resume`. **No per-turn session_id rewrite is needed** (handoff already
carries the parent's `session_id` forward into the new run row; that stays correct
for codex). DB code (`cli/core.py`) needs no codex-specific change.

`codex exec resume` does **not** accept `--sandbox` / `-C` / `--cd`
(it inherits the original session's settings); it does accept `--json`,
`--skip-git-repo-check`, `-m`, and `--dangerously-bypass-approvals-and-sandbox`.

## 3. Unattended (no-confirmation) execution

For "independent cwd, fully automatic" use, the minimal flags are:

- `--sandbox workspace-write` — let the agent edit files in the workspace
  (use `danger-full-access` only if broader access is required; we default to
  `workspace-write` + `--add-dir` is available if needed).
- `--skip-git-repo-check` — handoff dispatches into arbitrary cwds, not always git repos.
- `-C <cwd>` / `--cd <cwd>` — set the working root (handoff also sets the subprocess
  cwd, but passing `-C` keeps codex's own notion of the workspace aligned).

`--dangerously-bypass-approvals-and-sandbox` skips *all* prompts and sandboxing; it is
stronger than we need for the default. We keep `--sandbox workspace-write` (writes
confined to the workspace) which is the right minimal grant. The user's
`~/.codex/config.toml` already sets `approval_policy = "never"`, but we do not rely on
that — handoff passes flags explicitly so it works regardless of user config.

Resume can't take `--sandbox`; it inherits the original session's sandbox, so no flag
is passed there.

## 4. PTY wrapping — not needed for codex

The claude path wraps in `script -q /dev/null` because `claude -p` changes behavior
when stdout is not a TTY. `codex exec --json` is purpose-built for piped/non-interactive
use and emits clean JSONL to a pipe with no PTY. **codex's `type_defaults` set `pty: []`
(no wrapper).** Confirmed: piping codex exec stdout to a file produced well-formed JSONL.

## 5. Auth / environment

codex uses its own login state (`~/.codex/auth.json`, ChatGPT tokens or
`OPENAI_API_KEY`) — handoff sets **no** `ANTHROPIC_*` env for codex backends and does
**not** run the placeholder-token check (codex/opus go through login state). The codex
backend's `model` (`gpt-5.5`) is passed via `-m {model}`.

> Note on this machine: the logged-in codex workspace currently returns
> `402 Payment Required {"code":"deactivated_workspace"}`, so live codex model turns
> can't complete here. The event-schema, session-id-stability, resume-no-fork, flag,
> and PTY findings above were all verified directly (they don't require a successful
> model turn). A full end-to-end codex run will succeed once the account is reactivated;
> the parser is written to the documented success-path schema (`item.completed`
> agent_message → `turn.completed`).
