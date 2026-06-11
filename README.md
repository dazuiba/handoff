<div align="center">

# handoff

**Your coding agents should be delegating to each other.**

Hand work off to DeepSeek from inside Claude Code / Codex and save your flagship quota;
hand a hard problem off to Codex / Opus from inside a DeepSeek session and borrow a brain.
No tool-switching, no lost context.

[![PyPI](https://img.shields.io/pypi/v/handoff-cli)](https://pypi.org/project/handoff-cli/)
[![Python](https://img.shields.io/pypi/pyversions/handoff-cli)](https://pypi.org/project/handoff-cli/)

**English** · [简体中文](README.zh-CN.md)

</div>

<!-- assets/claude-code.jpg — ~720px wide — hero shot: one-sentence dispatch in Claude Code, main session only echoes RESULT=, agent reads .result.md and reports back -->
<img src="assets/claude-code.jpg" width="720" alt="Handing a task off to DeepSeek from Claude Code">

## Why handoff

If you juggle more than one coding agent, these will sound familiar:

- 💸 **"My Claude / Codex subscription never lasts the week"** — You say: *"Take the 3 tasks above and run them on 3 parallel `/handoff-ds`."* DeepSeek does execution work fast and cheap; save the flagship quota for decisions.
- 🤔 **"DeepSeek is stuck — I'd like a second opinion from Codex"** — You say: *"Ask `/handoff-codex` what it thinks."* No new terminal, no re-explaining the background; the answer lands back in your current session.
- 🔁 **"Pick up where the last dispatched task left off"** — You say: *"Resume that `/handoff-ds` session and do item 2."* Every file it changed, everything it read and concluded is still there.
- 🔄 **"Trying another model means a fresh session and retelling the whole story"** — Don't switch. Stay in the session you know; handoff brokers the task in the middle and brings the result back.

And that's the entire user interface: **one sentence inside your agent session.**

## Quick start

```bash
uv tool install handoff-cli
handoff init        # creates the config, links skill / agent files
```

Provide your DeepSeek token either way: set the `DEEPSEEK_API_KEY` environment variable, or put it in `~/.handoff/config.yaml`.

Then go back to Claude Code and say:

> Make a plan, then have `/handoff-ds` execute it.

The task runs in the background without blocking your session; when it finishes, the agent reads the result and reports back.

Upgrade with `uv tool upgrade handoff-cli`.

<details>
<summary>No uv / installing from source?</summary>

<br>

`pipx install handoff-cli` or `pip install handoff-cli` work just as well. From source:

```bash
git clone https://github.com/dazuiba/handoff && cd handoff
uv tool install -e .
handoff init
```

</details>

## Who you can hand work off to

| Prompt / agent | Delegates to | Under the hood | Best for |
| --- | --- | --- | --- |
| `/handoff-ds` | DeepSeek V4 | `claude -p` (DeepSeek's Anthropic-compatible endpoint) | Execution work: writing code, running tests, refactors, bulk edits |
| `/handoff-codex` | Codex (GPT-5.5) | `codex exec` | Heavy reasoning, second opinions, gnarly debugging |
| `/handoff-opus` | Claude Opus | `claude -p` | Decisions that deserve the top model |

> Codex has no slash commands; use the subagent of the same name instead — say "have `handoff-ds` execute the task above."

All three targets work out of the box: opus / codex reuse your local logins with zero config; deepseek only needs a token.

## After a task is dispatched

Dispatching and resuming are the AI's job (`handoff run` / `handoff resume` under the hood). These two are for you — browse the list, watch the progress:

<table>
<tr>
<td width="50%" valign="top">

**`handoff list`** — interactive TUI over your full task history. Read the full prompt, live status, and final result; press `G` on a row to reload that conversation and keep chatting.

</td>
<td width="50%" valign="top">

**`handoff tail <run-id>`** — follow a task's output stream live, like looking over its shoulder.

</td>
</tr>
<tr>
<td valign="top">

<!-- assets/list-tui.jpg — ~480px wide — TUI list + detail view, highlight G/C shortcuts -->
<img src="assets/list-tui.jpg" width="100%" alt="handoff list interactive TUI">

</td>
<td valign="top">

<!-- assets/tail.jpg — ~480px wide — handoff tail live stream -->
<img src="assets/tail.jpg" width="100%" alt="handoff tail live follow">

</td>
</tr>
</table>

Inside Claude Code there's also a zero-cost option: expand the background shell and the live progress stream is right there — rendered in the shell view, never burning your main session's context.

<details>
<summary><b>Dispatching tasks in parallel</b></summary>

<br>

Have your agent fire off several tasks in a single message; each runs and completes independently. handoff auto-increments run numbers so they never collide.

<!-- assets/parallel.jpg — ~621px wide — 2–3 background tasks from one message, each with its own RESULT= path -->
<img src="assets/parallel.jpg" width="621" alt="Parallel dispatch">

</details>

## How it works

1. Your agent hands the whole task to handoff, which runs it **in the background** — your session never blocks.
2. handoff launches the matching CLI (`claude -p` / `codex exec`) in an isolated context and streams the full output to disk.
3. The main session receives exactly one line: `RESULT=<path-to-result-file>`. Progress goes to the background shell view and `.out.txt` — **never** into your main context.
4. On completion the agent gets notified, reads `.result.md`, and reports back to you.
5. The `RESULT=` path encodes the run_id (e.g. `hd-0611-03`) — a stable handle for resuming: every follow-up round points at the same conversation.

<details>
<summary><b>Why it pays off: the math</b></summary>

<br>

For **transactional work** — writing code, running tests — DeepSeek V4 holds its own against Sonnet-class models at a fraction of the price. What's genuinely scarce, and worth a subscription, is the judgment of the one or two models at the very top (Opus / GPT-5.5).

| Option | Relative cost for the same work |
| --- | --- |
| Claude Sonnet | 1× (baseline) |
| DeepSeek official API | **1/3** |
| [OpenCode Go](https://opencode.ai/go?ref=D5926WCTD8) (includes DeepSeek V4) | **1/18** |

Let the flagship model communicate, decompose, and review; hand all execution off. A $20 subscription directing $5 of compute gets you ~$200 worth of work.

</details>

## Configuration

`handoff init` writes a complete `~/.handoff/config.yaml` — three backends, ready to go. The first one is the default. Only DeepSeek needs a token; opus and codex reuse your local logins with zero config.

```yaml
# ~/.handoff/config.yaml — handoff init generates this for you
backends:
  deepseek:                          # ← first = default
    type: claude
    model: deepseek-v4-flash
    pro_model: "deepseek-v4-pro[1m]"
    env:
      ANTHROPIC_BASE_URL: https://api.deepseek.com/anthropic
      ANTHROPIC_AUTH_TOKEN: "${DEEPSEEK_API_KEY}"   # set in shell, or replace with sk-...
      ANTHROPIC_MODEL: "{model}"

  opus:                              # local claude login — zero config
    type: claude
    ...

  codex:                             # local codex login — zero config
    type: codex
    ...
```

Want another Anthropic-compatible endpoint? Add a block under `backends`:

```yaml
backends:
  kimi:
    type: claude
    model: kimi-k3
    env:
      ANTHROPIC_BASE_URL: https://api.moonshot.cn/anthropic
      ANTHROPIC_AUTH_TOKEN: "${MOONSHOT_API_KEY}"
      ANTHROPIC_MODEL: "{model}"
```

The env block is entirely yours — every key=value you set is exported before the CLI launches. `{model}` substitutes the resolved model name, `${ENV_VAR}` expands from your shell.

Run `handoff env` to see where everything lives. Full details: **[configuration docs →](docs/configuration.zh-CN.md)**.

## More

- **[CLI reference →](docs/cli-reference.zh-CN.md)** — full usage of `run` / `resume` / `list` / `tail` / `env` / `init`, run-id encoding, on-disk file layout.
- **[Configuration →](docs/configuration.zh-CN.md)** — mechanism vs data layers, env block, `${ENV}` interpolation, include, custom backends.
- **[Design notes →](docs/design.zh-CN.md)** — why Claude Code uses background shells while Codex uses a subagent; the RESULT= protocol.
