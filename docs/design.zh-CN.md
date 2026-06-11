# 设计说明

[← 返回 README](../README.zh-CN.md)

本文档解释 handoff 的几个关键设计决策。

## 为什么 Claude Code 用后台 shell、Codex 用 subagent

在 Claude Code 和 Codex 里 handoff 任务的机制不同，各有原因：

**Claude Code — 后台 shell（`/handoff-ds` 等 skill）**

Claude Code 对后台 shell 支持极好：
- 能以**通知**方式感知任务完成——不需要轮询
- 展开后台 shell 就能看到实时进度（stderr），走 shell view，**不烧主会话上下文**
- 主 session 全程不阻塞、几乎不耗 token

所以直接把 `handoff run` 跑在后台 shell 是最优解。

**Codex — subagent（`handoff-ds` subagent）**

Codex 不支持通知，只能轮询。每轮询一次就消耗一次主 session 的 cache read，对动辄 5~20 分钟的任务会烧掉大量 token。但 Codex 能感知 **subagent 的完成事件**——

所以改用一个廉价的 `gpt-5.4-mini` low-effort subagent，**阻塞式**调用 `handoff run --backend deepseek <PROMPT_FILE> >/dev/null`：
- stderr 持续输出进度，防止 subagent 长时间静默超时
- stdout 的最终正文被丢弃（`>/dev/null`）
- 结束后只把一行 `RESULT=` 路径带回主 session

subagent 的完整指令见 `cli/skills/handoff-ds.toml`。

## RESULT= 协议

handoff 与 AI 调用者之间的交互只靠一行文本：

```
RESULT=/Users/sam/.handoff/tasks/hd-0611-03.result.md
```

这行同时编码了两条信息：

1. **结果文件路径**——完成后读它就拿到最终结论
2. **run_id**（`hd-0611-03`）——文件名主干去掉 `.result.md` 就是 run_id，它是续接的稳定句柄

协议约定：
- `RESULT=` 在任务启动时**立刻**打印到 stdout 和 stderr——调用者不等任务完成就能拿到路径
- stderr 持续输出进度（带时间戳），供人工观看或诊断
- stdout 在任务完成后打印最终结果正文（普通 shell 用户直接看到结果；AI 调用者应忽略 stdout 正文，只读 `.result.md`）
- 进度同时落盘到 `.out.txt`（与 `RESULT=` 路径同名，后缀换 `.out.txt`）
- 输入落盘到 `.prompt.txt`

这个极简协议让 handoff 能对接任何能执行 shell 命令的 AI 平台——skill 或 subagent 只需捕获 `RESULT=` 一行，其余全部交给文件系统。

## codex 集成

handoff 的 codex 后端基于对 `codex-cli 0.139.0` 的实测调研。关键结论：

### 事件流

`codex exec --json` 输出 JSONL 事件流。handoff 关心三类：

| handoff 信号 | codex 事件 |
| --- | --- |
| `session(id)` | `thread.started.thread_id` |
| `progress(text)` | `item.*` 中的 `agent_message`、`reasoning`、`command_execution` |
| `result(text)` | `turn.completed` 前最后一个 `agent_message` 的 `text` |

未知事件/类型直接跳过，容忍 minor schema drift。

### 会话续接

`codex exec resume <SESSION_ID> [PROMPT]` **不 fork**——返回相同的 `thread_id`。所以 handoff 的 session_id 稳定句柄策略对 codex 同样有效，不需要任何特殊处理。

### 自动执行

codex 默认需要确认才能执行命令。handoff 通过显式 flag 跳过所有交互：

- `--sandbox workspace-write` — 允许在工作区内编辑文件
- `--skip-git-repo-check` — handoff 可能在非 git 仓库目录工作
- `-C <cwd>` — 显式设定工作根目录

Resume 不能带 `--sandbox` / `-C`，继承原会话的设置。handoff 的 `continue_id_flags` 已正确区分两种路径。

### PTY

codex 不需要 PTY 包装——`codex exec --json` 本身就是为管道/非交互场景设计的，管道输出是干净的 JSONL。

### 认证

codex 使用自己的登录态（`~/.codex/auth.json` 或 `OPENAI_API_KEY`）——handoff 对 codex 型 backend 不设 `ANTHROPIC_*` 环境变量，也不跑 token 占位符检查。

### 流解析器

`CodexStreamParser`（`cli/stream.py`）实现了上述事件映射。codex 路径的详细启动配置见 `cli/backend_types.yaml` → `types.codex`。
