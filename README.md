# ds-cli

`ds-cli` 的用户配置在：

```text
~/.ds-cli/config.yaml
```

第一次运行 `ds-cli`，或者执行 `ds-cli install` 时，`ds-cli` 会先检查这份配置是否存在。缺少配置时会进入初始化确认界面；`ds-cli install` 每次执行也会进入同一套确认界面，用来刷新 hard/soft link。界面会提示即将写入的内容：默认配置文件、`~/bin/ds-cli` 软链接、Codex agent 配置、Claude Code skill 链接。只有输入 `Y` 才会继续，其他输入都会退出。

初始化完成后，终端会打印实际写入或保留了哪些文件，并提示你回到这份 README 修改配置。

## 安装

需要 Python 3 和 PyYAML：

```bash
python3 -m pip install pyyaml
```

在仓库目录执行：

```bash
cd /Users/sam/dev/github/ds-cli
./ds-cli install
```

`ds-cli install` 会创建缺失的 `~/.ds-cli/config.yaml`，然后触发仓库里的 `install.sh`。如果配置已经存在，它不会覆盖配置，只会在确认后刷新链接。`install.sh` 只负责刷新这些链接：

```text
~/bin/ds-cli -> <repo>/ds-cli
~/.codex/agents/ds-agent.toml -> <repo>/ds-agent.toml
~/.claude/skills/ds-cli/SKILL.md -> <repo>/SKILL.md
```

安装后，Codex 可以通过 `ds-agent` 使用这套入口；Claude Code 会通过 `~/.claude/skills/ds-cli/SKILL.md` 看到同一套静态 skill 说明。

## 配置

首次写入的 `~/.ds-cli/config.yaml` 大致如下：

```yaml
default_backend: default
fast_backend: default

backends:
  default:
    description: "DeepSeek API"
    ANTHROPIC_AUTH_TOKEN: "<YOUR_TOKEN>"

  # opencode:
  #   description: "Local OpenCode proxy"
  #   ANTHROPIC_BASE_URL: "http://127.0.0.1:4000"
  #   ANTHROPIC_AUTH_TOKEN: "unused"
```

默认配置使用 DeepSeek Anthropic endpoint：

```text
https://api.deepseek.com/anthropic
```

你至少需要把 `<YOUR_TOKEN>` 改成真实 token。只要 token 仍然以 `<` 开头，`ds-cli run`、`start`、`go` 会在真正调用 `claude` 前直接报错，不会创建新的 run 记录。

`default_backend` 是普通模式使用的配置；`fast_backend` 是加 `--fast` 时使用的配置。命令行不提供 `--backend`，用户只需要在配置文件里决定普通模式和快速模式分别指向哪个 backend。

最小可用配置通常是：

```yaml
default_backend: default
fast_backend: default

backends:
  default:
    description: "DeepSeek API"
    ANTHROPIC_AUTH_TOKEN: "sk-your-token"
```

如果你要默认走本地 OpenCode proxy，可以自己添加 `opencode` 并切换指向：

```yaml
default_backend: opencode
fast_backend: default

backends:
  default:
    description: "DeepSeek API"
    ANTHROPIC_AUTH_TOKEN: "sk-your-token"

  opencode:
    description: "Local OpenCode proxy"
    ANTHROPIC_BASE_URL: "http://127.0.0.1:4000"
    ANTHROPIC_AUTH_TOKEN: "unused"
```

`http://127.0.0.1:4000` 背后的 proxy 可以参考：

```text
https://github.com/iTzFaisal/oc-cc-proxy/
```

## 使用

常用入口只需要区分普通模式和快速模式：

```bash
ds-cli run --cwd /path/to/project prompt.txt
ds-cli run --fast --cwd /path/to/project prompt.txt
ds-cli run --text "hi"
```

运行记录、prompt、进度和结果会写到：

```text
~/.ds-cli/runs/
~/.ds-cli/tasks/
```
