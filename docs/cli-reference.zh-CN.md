# 命令参考

[← 返回 README](../README.zh-CN.md)

六个命令按使用者分两组：

| 使用者 | 命令 | 用途 |
| --- | --- | --- |
| **你** | `list`/`ls` / `tail` / `env` / `init` | 看任务列表、盯进度、查路径、初始化 |
| **AI**（skill / subagent） | `run` / `resume` | 派发新任务、续接已有会话 |

## 给你用的命令

### list / ls — 浏览历史任务

```bash
handoff list [--uuid] [--cwd]
handoff ls [--uuid] [--cwd]
```

打开交互式 TUI，浏览全部历史任务：

| 操作 | 行为 |
| --- | --- |
| 表格视图 | seq / run_id / 时间 / 状态 / backend / 摘要 / cwd |
| `Enter` | 查看详情（prompt 全文 + 解析后的 JSONL 事件流） |
| `G` | 重开那次会话接着聊（交互式 resume） |
| `C` | 复制 session UUID 到剪贴板（macOS `pbcopy`） |

自动刷新（2 秒间隔），详情视图打开时暂停刷新以免跳走。

| 标志 | 作用 |
| --- | --- |
| `--uuid` | 直接输出 UUID 列表（纯文本，非 TUI） |
| `--cwd` | 列表模式显示完整 cwd 路径 |

### tail — 实时跟踪输出

```bash
handoff tail [<run-id|seq>]
```

实时跟踪某条 run 的输出流（类似 `tail -f`）。省略参数则跟踪最近一次 run。适合诊断或围观后台任务执行过程。

### init — 初始化配置

```bash
handoff init [-y|--yes]
```

创建 `~/.handoff/config.yaml`（完整模板，填 token 即用），并链接 skill / agent 文件：

| 目标路径 | skill |
| --- | --- |
| `~/.claude/skills/handoff-ds/SKILL.md` | `/handoff-ds` |
| `~/.claude/skills/handoff-codex/SKILL.md` | `/handoff-codex` |
| `~/.claude/skills/handoff-opus/SKILL.md` | `/handoff-opus` |
| `~/.codex/agents/handoff-ds.toml` | `handoff-ds` subagent |

`-y` / `--yes` 跳过交互确认。已存在的 config.yaml 不会被覆盖。

## AI 调用的命令

你通常不直接敲这两个命令——skill / subagent 替你调用。这里只记录接口约定。

```bash
handoff run    [--backend <name>] [--cwd <dir>] [--pro] (<input-file|-> | --text <prompt...>)
handoff resume [<run-id|seq>] [--pro] [--cwd <dir>] [(<input-file|-> | --text <prompt...>)]
```

| | run | resume |
| --- | --- | --- |
| 作用 | 开新会话派发任务 | 把任务派进**已有会话**（上下文全保留），或无 prompt 时交互式重开 |
| 目标选择 | `--backend <name>`，省略用 `backends` 第一个条目 | 沿用原会话的 backend（session id 只对创建它的 CLI 有意义；显式指定不符会报错） |
| prompt 来源 | 文件 / `-`（stdin、heredoc）/ `--text` | 同左；**无 prompt = 交互式重开**，后台调用必须带 prompt |
| `--pro` | 用该 backend 的 `pro_model` | 不自动继承，需再次显式带上 |
| 会话句柄 | 新 run_id（如 `hd-0611-03`） | 每轮分配新 run_id，但多轮续接始终用**第一次**的 run_id（session_id 稳定不变） |

**输出协议**：启动后立即向 stdout 和 stderr 各打印一行 `RESULT=<结果文件路径>`。stderr 持续输出进度；stdout 在完成后打印最终结果正文。AI 调用者只关心 `RESULT=` 这一行——拿到路径后等通知、读 `.result.md`；面向用户回显时，home 下路径应缩写成 `~/.handoff/...`。

## 附录

### run id 编码

run_id 格式：`hd-<MMDD>-<SEQ_CODE>`。

| 部分 | 含义 |
| --- | --- |
| `MMDD` | 月日（如 `0611`） |
| `SEQ_CODE` | 当日计数器：`01`–`99` → 1–99；`A0`–`ZZ` → 100–1035（每日上限 1035） |

旧 `ds-` 前缀的历史记录不会被重命名，按 seq / run_id 查找继续有效。

### 落盘文件布局

```text
~/.handoff/
├── config.yaml              # 用户配置
├── runs/
│   ├── handoff.db           # SQLite（runs 表 + run_counters 表）
│   └── <run_id>-<uuid>.jsonl  # 每次运行的原始 JSONL 流
└── tasks/
    ├── <run_id>.prompt.txt  # 任务 prompt
    ├── <run_id>.out.txt     # 进度日志（stderr 流 + RESULT= 标记）
    └── <run_id>.result.md   # 最终结果
```

### 运行状态

| 状态 | 含义 |
| --- | --- |
| `running` | 正在执行 |
| `success` | 成功完成，`.result.md` 已写入 |
| `error` | 执行失败（backend 报错或未产出有效结果） |
| `interrupted` | 被 `Ctrl-C` 中断 |
