# ds-cli

`ds-cli` 用来把 Claude Code 跑在可配置的 Claude-compatible backend 上。它会把每次任务的 prompt、进度、结果和 session 记录到 `~/.ds-cli`，并提供一个 `ds-cli list` TUI 来查看和恢复历史任务。

默认 backend 是本机 OpenCode 代理：

```text
opencode-proxy -> http://127.0.0.1:4000
```

## 安装

需要 Python 3 和 PyYAML：

```bash
python3 -m pip install pyyaml
```

安装命令和 agent/skill 文件：

```bash
cd /Users/sam/dev/github/ds-cli
./install.sh
```

安装脚本会生成 `ds-agent.toml` 和 `SKILL.md`，把 `ds-cli` 链接到 `~/bin/ds-cli`，并把 agent/skill 链接到对应目录。

## 运行任务

从文件读取 prompt：

```bash
ds-cli run --cwd /path/to/project /path/to/prompt.txt
```

从 stdin 读取 prompt：

```bash
cat prompt.txt | ds-cli run --cwd /path/to/project -
```

快速测试：

```bash
ds-cli run-demo "今天周几"
```

使用 pro 模型档位：

```bash
ds-cli run --pro --cwd /path/to/project -
```

`run` 会把最终回答输出到 stdout，同时写入这些文件：

```text
~/.ds-cli/tasks/<run-id>.prompt.txt
~/.ds-cli/tasks/<run-id>.out.txt
~/.ds-cli/tasks/<run-id>.result.md
~/.ds-cli/runs/<run-id>-<session-id>.jsonl
```

`run-id` 类似 `ds-01-0605`。每天的序号是 `01..99`，之后是 `A0..ZZ`。

## 添加 backend

默认配置在程序内维护。用户只需要在这里写覆盖项：

```text
~/.ds-cli/config.yaml
```

例如添加一个 `fast` backend。它会继承内置的 `backend_template`，通常只需要补 token；如果不是默认 DeepSeek endpoint，再覆盖 URL：

```yaml
backends:
  fast:
    ANTHROPIC_AUTH_TOKEN: "sk-your-token"
```

使用这个 backend：

```bash
ds-cli run --backend fast --cwd /path/to/project -
ds-cli run-demo --backend fast "hi"
```

把它设为默认 backend：

```yaml
default_backend: fast
backends:
  fast:
    ANTHROPIC_AUTH_TOKEN: "sk-your-token"
```

`--fast` 已移除。以后统一用：

```bash
--backend <name>
```

## 查看和恢复

打开历史任务 TUI：

```bash
ds-cli list
```

快捷键：

```text
↑/↓ or j/k  移动
Enter       查看详情
C           复制 session id
G           恢复当前 session
q           退出
```

直接恢复某次任务：

```bash
ds-cli go ds-01-0605
```

`go` 默认使用这条 run 记录里保存的 backend。也可以手工覆盖：

```bash
ds-cli go ds-01-0605 --backend opencode-proxy
```

查看日志或最终结果：

```bash
ds-cli tail ds-01-0605
ds-cli result ds-01-0605
```

## agent 文件

`ds-agent.toml` 和 `SKILL.md` 是自动生成的。生成内容会内嵌当前可用 backend 表格，所以调用方不需要额外读取配置文件。

手动重新生成：

```bash
ds-cli sync-agents
```

`ds-cli` 启动时也会自动检查模板和配置文件的更新时间；如果它们比生成文件新，会自动同步。

## 清空运行状态

只删除 `~/.ds-cli` 下的运行数据，不删除项目源码：

```bash
./reset-state.sh
```

适合 schema 变化后重建数据库，或想清空历史任务时使用。

## 排障

缺 PyYAML：

```bash
python3 -m pip install pyyaml
```

backend 名称不生效时，先同步 agent 文件：

```bash
ds-cli sync-agents
```

然后检查：

```text
~/.ds-cli/config.yaml
```

任务失败时看日志：

```bash
ds-cli tail <run-id>
cat ~/.ds-cli/tasks/<run-id>.out.txt
```
