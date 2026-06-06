# ds-cli

**English** · [中文](README.zh-CN.md)

GPT-5.5 / Opus plans; DeepSeek V4 codes.

You install ds-cli once — as a skill in Claude Code, or a subagent in Codex — then drive it in one line. You rarely type `ds-cli` by hand.

## How you use it

Ask your agent to plan, then hand the execution to ds-cli.

### Claude Code — the `/ds-cli` skill

> Make a plan, then have `/ds-cli` execute the tasks above.

Each task runs as a **background shell command**. Click it to watch ds-cli's live progress.

![Claude Code dispatching ds-cli in the background](assets/claude-code.jpg)

### Codex — the `ds-agent` subagent

> Make a plan, then have `ds-agent` execute the tasks above.

Codex runs the subagent in the background; you watch progress in the subagent view.

![Codex waking the ds-agent subagent](assets/codex.jpg)

That's the whole idea: the flagship model decomposes and checks the work; DeepSeek V4 executes it, cheaply.

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/dazuiba/ds-cli/main/install-online.sh | bash
```

Requires Python 3 and git. The installer links ds-cli into the places Claude Code, Codex, and your shell look:

```text
~/bin/ds-cli                       -> <checkout>/ds-cli            # command entry
~/.codex/agents/ds-agent.toml      -> <checkout>/ds-agent.toml     # Codex subagent
~/.claude/skills/ds-cli/SKILL.md   -> <checkout>/SKILL.md          # Claude Code skill
```

Then edit `~/.ds-cli/config.yaml` and set your token (see [Configure](#configure)).

> Prefer to clone yourself? `git clone` the repo, `pip install pyyaml`, and run `./ds-cli install`.

## Update

```bash
ds-cli update
```

Pulls the latest source into the checkout and refreshes the links.

## Configure

`~/.ds-cli/config.yaml` holds **only your overrides** — the bundled defaults (models, backend template, system prompt) are layered underneath automatically, so this file never needs to reference the source tree.

Minimal working config:

```yaml
default_backend: default   # backend for normal mode
fast_backend: default      # backend for --fast

backends:
  default:
    description: "DeepSeek API"
    env:
      ANTHROPIC_AUTH_TOKEN: "sk-your-token"
```

The default endpoint is `https://api.deepseek.com/anthropic`. While the token is still the `<YOUR_TOKEN>` placeholder, `ds-cli run` fails before calling anything.

To route through a local OpenCode proxy instead, add a backend and repoint:

```yaml
default_backend: opencode
fast_backend: default

backends:
  default:
    env:
      ANTHROPIC_AUTH_TOKEN: "sk-your-token"
  opencode:
    description: "Local OpenCode proxy"
    env:
      ANTHROPIC_BASE_URL: "http://127.0.0.1:4000"   # see github.com/iTzFaisal/oc-cc-proxy
      ANTHROPIC_AUTH_TOKEN: "unused"
```

Every overridable field (`default_model` / `pro_model` / `backend_template` / `system_prompt`, …) lives in `cli/default_config.yaml`. There is no `--backend` flag — which backend normal/fast mode uses is decided by `default_backend` / `fast_backend`.

## CLI reference

You normally invoke ds-cli through the skill/subagent, but it's a plain CLI underneath:

```bash
ds-cli run --cwd /path/to/project prompt.txt   # dispatch a task from a file
ds-cli run - <<'EOF'                            # …or from stdin
Refactor module X and add tests
EOF
ds-cli run --text "hi"                          # smoke-test your config

ds-cli run --pro  prompt.txt                    # use pro_model for harder tasks
ds-cli run --fast prompt.txt                    # use fast_backend (combinable with --pro)

ds-cli list                                     # list past tasks; view full prompt / result
ds-cli go   [<run-id|seq>]                      # resume a session with the backend
ds-cli tail [<run-id|seq>]                      # live-tail a run's output stream
```

A run id looks like `ds-<SEQ>-<MMDD>` (SEQ is a daily counter `01..99` / `A0..ZZ`). Each run persists `.prompt.txt`, `.out.txt` (progress), and `.result.md` (final result) under:

```text
~/.ds-cli/runs/     # per-run metadata / stream
~/.ds-cli/tasks/    # .prompt.txt / .out.txt / .result.md
```
