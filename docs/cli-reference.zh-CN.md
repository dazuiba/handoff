# 命令参考

[← 返回 README](../README.zh-CN.md)

你通常通过 skill（Claude Code）或 subagent（Codex）调用 handoff，但底层就是一个普通 CLI。本文档覆盖全部五个命令及所有标志。

## run — 派发新任务

```bash
handoff run [--backend <name>] [--cwd <dir>] [--pro] (<input-file|-> | --text <prompt...>)
```

启动一个独立的后台会话，把任务交给后端执行。`run` 和 `resume` 是给 AI（skill / subagent）调用的——人工用户通常通过 `/handoff-ds`、`/handoff-codex` 等 skill 间接使用。

**输入源**（三选一）：

| 形式 | 示例 |
| --- | --- |
| 从文件 | `handoff run prompt.txt` |
| 从 stdin | `handoff run - <<'EOF'` 或 `echo "..." \| handoff run -` |
| `--text` | `handoff run --text "smoke test"` |

**标志**：

| 标志 | 作用 |
| --- | --- |
| `--backend <name>` | 选择后端（内置：`deepseek`、`opus`、`codex`）。省略时使用 `default_backend` |
| `--cwd <dir>` | 指定工作目录，默认继承当前进程的 cwd |
| `--pro` | 使用当前后端配置的 `pro_model` 而非默认 `model` |

**输出协议**：

启动后立即向 stdout 和 stderr 各打印一行 `RESULT=<结果文件绝对路径>`。stderr 持续输出进度；stdout 在完成后打印最终结果正文。AI 调用者只关心 `RESULT=` 这一行——拿到路径后等通知、读 `.result.md` 即可。

## resume — 续接已有会话

```bash
handoff resume [<run-id|seq>] [--pro] [--cwd <dir>] [(<input-file|-> | --text <prompt...>)]
```

把新任务派发到一个**已有会话**（保留其全部上下文），或交互式重开那个会话接着聊。

**选择目标会话**：`<run-id|seq>` 可以是 run_id（如 `hd-0611-03`）或数字序号（如 `handoff list` 第一列的 seq）。省略则选最近一次。

**两种模式**：

| 有无 prompt | 行为 |
| --- | --- |
| **无 prompt** | 交互式重开：直接用对应后端把会话加载进 CLI，接着聊（`claude --resume` / `codex resume`） |
| **有 prompt**（`-`/`--text`/文件） | 非交互续派：分配新 run 行（新 run_id），但底层会话不变——上下文全部保留 |

**约束**：
- 续接必须沿用原会话的后端（`--resume` 的 session id 只对创建它的 CLI 有意义）。显式 `--backend` 与原会话不符会直接报错。
- 原会话用过的 `--pro` 不会自动继承——续接时需再次显式带上。
- 多轮续接始终用**第一次**那个 run_id（`session_id` 稳定不变）。

## list — 浏览历史任务

```bash
handoff list [--uuid] [--cwd]
```

打开交互式 TUI，浏览全部历史任务：

- 表格视图：seq / run_id / 时间 / 状态 / 后端 / 摘要 / cwd
- 选中某行按 `Enter` 查看详情（prompt 全文 + 解析后的 JSONL 事件流）
- 按 `G` 用对应后端重开那次会话（交互式 resume）
- 按 `C` 复制 session UUID 到剪贴板（macOS `pbcopy`）
- 自动刷新（2 秒间隔），详情视图打开时暂停刷新以免跳走

**标志**：

| 标志 | 作用 |
| --- | --- |
| `--uuid` | 直接输出 UUID 列表（纯文本，非 TUI） |
| `--cwd` | 列表模式显示完整 cwd 路径 |

## tail — 实时跟踪输出

```bash
handoff tail [<run-id|seq>]
```

实时跟踪某条 run 的输出流（类似 `tail -f`）。省略参数则跟踪最近一次 run。适合诊断或围观后台任务执行过程。

## init — 初始化配置

```bash
handoff init [-y|--yes]
```

创建 `~/.handoff/config.yaml`（含注释的最小模板），并在 `~/.claude/skills/` 和 `~/.codex/agents/` 下创建指向打包 skill 文件的链接：

| 目标路径 | skill |
| --- | --- |
| `~/.claude/skills/handoff-ds/SKILL.md` | `/handoff-ds` |
| `~/.claude/skills/handoff-codex/SKILL.md` | `/handoff-codex` |
| `~/.claude/skills/handoff-opus/SKILL.md` | `/handoff-opus` |
| `~/.codex/agents/handoff-ds.toml` | `handoff-ds` subagent |

`-y` / `--yes` 跳过交互确认。

## run id 编码

run_id 格式：`hd-<MMDD>-<SEQ_CODE>`。

- `MMDD`：月日（如 `0611`）
- `SEQ_CODE`：当日计数器，2 字符编码
  - `01`–`99` → 1–99
  - `A0`–`A9`, `AA`–`AZ`, `B0`–`ZZ` → 100–1035
- 每日上限 1035（`ZZ`）

旧 `ds-` 前缀的历史记录不会被重命名，但按 seq / run_id 查找继续有效。

## 落盘文件布局

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

## 运行状态

| 状态 | 含义 |
| --- | --- |
| `running` | 正在执行 |
| `success` | 成功完成，`.result.md` 已写入 |
| `error` | 执行失败（后端报错或未产出有效结果） |
| `interrupted` | 被 `Ctrl-C` 中断 |
