# ds-cli

[中文](readme.md) · **English**

Let **SOTA models (Opus / GPT-5.5)** do only what they're best at, and hand everything else to DeepSeek.

`ds-cli` fans out execution to the background: each task runs in its own isolated context and returns just one result to your main session — under the hood it's a `claude` client wired to a DeepSeek endpoint.

Flagship intelligence is expensive, so spend it only where it's irreplaceable; send the coding and testing to far cheaper DeepSeek — **same money, more done**.

## Why

An underrated fact: for **transactional work** like writing code and running tests, DeepSeek V4 is already smarter than Sonnet or GPT-5.4 — and cheaper. The truly scarce thing worth paying for is just the one or two models at the very top (Opus / GPT-5.5).

So the division of labor should be:

- **The smartest flagship model does only three things**:  talk to you, break down the task, review the result
- **Everything else — the "grunt work"** — writing code, running tests, debugging, editing files — all goes to DeepSeek V4.

What it costs to do the same work:

| Plan | Relative unit cost (same work) |
| --- | --- |
| Claude Sonnet | 1× (baseline) |
| DeepSeek official API | **1/3** |
| [OpenCode Go](https://opencode.ai/go?ref=D5926WCTD8) (incl. DeepSeek V4) | **1/18** |

> OpenCode Go's **$5/month** is worth roughly **$60** of usage — i.e. **1/6** of the official DeepSeek price; official DeepSeek is in turn 1/3 of Sonnet, so OpenCode works out to 1/3 × 1/6 = **1/18** of the Sonnet baseline.

👉 Direct the flagship model with a **$20 Codex plan**, do the work on a **$5 OpenCode Go** — a total of **$25/month for roughly $200 worth of work (≈10×)**.

There's a second benefit too: a real task produces thousands of lines of progress output. Run it directly in your main session and that noise either blocks the session or gets read into context, needlessly burning your flagship model's tokens. ds-cli outsources execution as a whole package — **the main session only gets one `RESULT=` result path back**; progress streams live in a background shell view (see "Viewing and taking over running tasks" below) and **never enters** the main context.

## How to use

Have your agent draw up a plan first, then hand execution to ds-cli.

| | Claude Code | Codex |
| --- | --- | --- |
| Prompt | "Have `/ds-cli` execute the above task" | "Have `ds-agent` execute the above task" |
| Mechanism | Directly triggers the `ds-cli` command (background shell) | Spins up a subagent to run in the background |
| Watch progress | Expand the background shell view or `ds-cli tail` | `ds-cli tail` |

<details>
<summary>Why aren't the Codex/Claude mechanisms the same?</summary>

<br>

- **Claude Code has excellent background-shell support**: it can sense a task's "completion" via **notification**, and watch progress in real time (stderr). So you just run `ds-cli` in a background shell — the main session is never blocked and barely spends any tokens.
- **Codex has no notifications, only polling**: every poll costs one cache read of the main session, which burns a lot of tokens for tasks that easily take 5–10 minutes. But Codex can sense a **subagent's completion event** — so we instead use a cheap model (`gpt-5.4-low`) as the subagent, call `ds-cli run --from codex` in a **blocking** fashion, and return only one `RESULT=` path to the main session after completion.
  - Why not the even cheaper `gpt-5.4-mini`? Its instruction-following is too poor — it does the work itself instead of dutifully handing the task off to ds-cli.

</details>


### Claude Code — `/ds-cli` skill

> Make a plan, and have `/ds-cli` execute the above task.

Each task is dispatched as a **background shell command**; click to watch ds-cli's execution progress in real time, while the main session only gets one `RESULT=` result path.

<!-- replace with: assets/claude-code.jpg — suggested 621 wide — swap in a "real coding task" (not print hi): show background dispatch + main session echoing only RESULT= + reading .result.md to report on completion. -->
<img src="assets/claude-code.jpg" width="621" alt="Claude Code dispatching ds-cli in the background">

### Codex — `ds-agent` subagent

> Make a plan, and have `ds-agent` execute the above task.

Codex spins up a subagent to run in the background. To avoid pulling large results into the subagent context, `ds-agent` returns only one `RESULT=` line after completion; use `ds-cli tail` when you need progress.

<!-- replace with: assets/codex.jpg — suggested 621 wide — re-shoot a full image where the text isn't cut off on the right. -->
<img src="assets/codex.jpg" width="621" alt="Codex invoking the ds-agent subagent">

That's the whole idea: the flagship model handles breakdown and acceptance, DeepSeek V4 handles cheap execution.

## Viewing and taking over running tasks

Once a task is dispatched, there are two ways to watch its progress — and even pull it back to keep chatting.

**1. In Claude Code**: expand that background shell to see the live progress stream compressed by `cclean` — it goes to the shell view and **never enters** the main session context.

<!-- replace with: assets/shell.jpg — suggested 621 wide — the compact live progress stream after expanding the background shell, showing "visible but doesn't burn context". -->
<img src="assets/shell.jpg" width="621" alt="Live progress in the background shell">

**2. On the command line**:

<table>
<tr>
<td width="50%" valign="top">

`ds-cli list` — a scrollable TUI of past tasks; view the full prompt / result, press `G` to open that session with your configured backend (deepseek claude).

</td>
<td width="50%" valign="top">

`ds-cli tail <run-id>` — live-tail the output stream of a given run.

</td>
</tr>
<tr>
<td valign="top">

<!-- replace with: assets/list-tui.jpg — suggested ~480 wide — curses list + detail view, circling the G/C shortcuts. -->
<img src="assets/list-tui.jpg" width="100%" alt="ds-cli list interactive TUI">
<br>
In `ds-cli list`, select a row and press `G`, or run `ds-cli resume <seq>` directly, to reload that session with claude via the backend and keep chatting. You can also send a follow-up task non-interactively to the same session with `ds-cli resume <seq> - <<'EOF' ... EOF`.
</td>
<td valign="top">

<!-- replace with: assets/tail.jpg — suggested ~480 wide — ds-cli tail live output stream. -->
<img src="assets/tail.jpg" width="100%" alt="ds-cli tail live tracking">

</td>
</tr>
</table>

<details>
<summary><b>Dispatching multiple tasks in parallel</b></summary>

<br>

Fire off multiple background tasks in a single message; each completes and notifies independently. ds-cli auto-increments each run's seq so they don't interfere with one another.

<!-- replace with: assets/parallel.jpg — suggested 621 wide — dispatching 2–3 background tasks in one message, each getting a different RESULT= path. -->
<img src="assets/parallel.jpg" width="621" alt="Dispatching multiple tasks in parallel">

</details>

---

## Installation

### Homebrew (recommended)

```bash
brew install dazuiba/tap/ds-cli
```

After installing, run `ds-cli install` to initialize your config, then edit `~/.ds-cli/config.yaml` to fill in your token:

```yaml
default_backend: default
fast_backend: default
backends:
  default:
    env:
      ANTHROPIC_AUTH_TOKEN: "sk-your-token"   # defaults to https://api.deepseek.com/anthropic
```

### Online install

```bash
curl -fsSL https://raw.githubusercontent.com/dazuiba/ds-cli/main/install-online.sh | bash
```

Requires Python 3.10+ and git. The install script links ds-cli into the locations where Claude Code, Codex, and the shell each look:

```text
~/bin/ds-cli                       -> <checkout>/ds-cli            # command entry point
~/.codex/agents/ds-agent.toml      -> <checkout>/ds-agent.toml     # Codex subagent
~/.claude/skills/ds-cli/SKILL.md   -> <checkout>/SKILL.md          # Claude Code skill
```

After installing, edit `~/.ds-cli/config.yaml` to fill in your token. Minimal config:

```yaml
default_backend: default
fast_backend: default
backends:
  default:
    env:
      ANTHROPIC_AUTH_TOKEN: "sk-your-token"   # defaults to https://api.deepseek.com/anthropic
```

For the full config (local OpenCode proxy, model / system prompt overrides, all overridable fields) see **[Configuration docs →](docs/configuration.zh-CN.md)**.

> Prefer to clone it yourself? `git clone` the repo, then run `./ds-cli install` (requires `uv`).

## Updating

- **Homebrew install**: `brew upgrade dazuiba/tap/ds-cli`
- **Source checkout**: `ds-cli update` (pull the latest source and refresh the links)

## More

- **[Command reference →](docs/cli-reference.zh-CN.md)** — all usage of `run` / `list` / `resume` / `tail` / `install` / `update`, run id encoding and on-disk file layout.
- **[Configuration docs →](docs/configuration.zh-CN.md)** — backend merge mechanism, OpenCode proxy, full table of overridable fields.
