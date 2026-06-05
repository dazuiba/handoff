---
name: ds-cli
description: 把一个独立的编码或调查任务整包交给 ds-cli 后端执行。后台运行，完成后自动通知。支持并行多任务。后端选择：opencode-proxy（默认），无。
---

# ds-cli Skill

<interaction_contract>
This skill is executed by Claude Code (an AI agent). The following rules are BINDING and must be followed exactly — do not deviate, simplify, or reinterpret them.

## 命令模板（每次必须照抄，不得修改结构）

```bash
ds-cli run - <<'__DS_EOF__'
[prompt 内容]
__DS_EOF__
```

**关键规则（违反任何一条都会导致命令失败或行为异常）：**

- `run_in_background: true` **必须启用**：ds-cli 耗时 2~20 分钟，前台执行会阻塞整个会话
- heredoc 界定符用 `__DS_EOF__`，prompt 内容直接粘贴进去，不转义
- **模型选择**：默认用快速模型即可。仅当用户明确提到 `pro`（或要求用更强/专业模型处理复杂任务）时，在 `ds-cli run` 后加 `--pro`，即 `ds-cli run --pro - <<'__DS_EOF__'`。
- **后端选择**：默认使用 `opencode-proxy`。以下后端可用：

| backend | default | base URL | description |
| --- | --- | --- | --- |
| `opencode-proxy` | yes | http://127.0.0.1:4000 | Local OpenCode proxy |

- **不要**外部生成时间戳或拼文件名；**不要**用 `> RESULT 2> OUT` 重定向——ds-cli 自己管命名和落盘

**启动命令后**（`run_in_background: true` 返回后），**从 stdout 捕获 ds-cli 打印的唯一有用的一行 `RESULT=<绝对路径>`**，并在面向用户的 assistant 消息里回显这一条路径（完成后默认只读它）：

- `RESULT=<绝对路径>`（最终结论文件，例如 `/Users/sam/.ds-cli/tasks/ds-01-0604.result.md`）

其余无需你读取：
- ds-cli 把克制的进度信息打在 **stderr**，Claude Code 的 shell view 会自动实时显示——你不用、也不要把它读进上下文。
- 进度日志同时落在与 `RESULT=` **同名的 `.out.txt`**（把 `.result.md` 换成 `.out.txt`），仅在诊断（无结果/超时）时才 `tail -f` 或 `Read`。
- 输入文件 `.prompt.txt`（同名）已是你刚发的内容，无需回显。

等待完成通知后，用 `Read` 读取该 `.result.md` 并汇报；**不要**再读后台输出（结果已在文件里，重复读只会把进度噪音吃进上下文）。若 `.result.md` 为空或异常，再读 `.out.txt` 诊断。
</interaction_contract>

## 运行任务

所有任务统一使用**后台模式**（`run_in_background: true`），不阻塞主会话。

### 单任务

按命令模板执行，启动后从 stdout 捕获 `RESULT=` 一行并回显，等通知后读该 `.result.md` 文件汇报。

### 并行多任务

在**同一条消息**里发出多个独立的 `run_in_background: true` Bash 调用，各自用 heredoc 传入不同的 prompt 内容。每个任务启动后分别从各自 stdout 捕获 `RESULT=` 路径（ds-cli 自动递增 seq）。每个任务完成时分别通知，分别读取对应的 `.result.md` 汇报。

### 串行多任务

等上一个任务的完成通知到达，读取并汇报结果后，再启动下一个任务。

## 完成后

收到后台完成通知后：
1. 用 `Read` 读取对应的 `RESULT=` 路径（`.result.md` 结果文件）
2. 汇总结果返回给用户
3. 若 `.result.md` 为空或异常，再读 `.out.txt`（进度日志）诊断
4. 如有后续任务（串行场景），此时启动下一个
