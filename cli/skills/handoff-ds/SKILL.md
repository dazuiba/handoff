---
name: handoff-ds
description: 把执行性编码/调查任务整包交给 DeepSeek 后台执行，省主会话额度。后台运行，完成后自动通知。支持并行多任务，支持续接（resume）上次会话继续派发后续任务。
---

# handoff-ds Skill

<interaction_contract>
This skill is executed by Claude Code (an AI agent). The following rules are BINDING and must be followed exactly — do not deviate, simplify, or reinterpret them.

## 命令模板（每次必须照抄，不得修改结构）

```bash
p=$(handoff new --backend deepseek --slug <三个英文单词以内的任务助记词>)
cat > "$p" <<'__HF_EOF__'
[prompt 内容]
__HF_EOF__
handoff run --backend deepseek "$p"
```

**关键规则（违反任何一条都会导致命令失败或行为异常）：**

- `run_in_background: true` **必须启用**：handoff 耗时 2~20 分钟，前台执行会阻塞整个会话
- `handoff new` 的 `--slug` 参数填写≤3个英文单词、`-`分隔的语义助记词（如 `fix-auth`、`add-tests`）；禁止追加日期、时间戳、随机数、UUID、计数器等唯一化内容，唯一性由 `handoff new` 自动分配的 seq 保证
- heredoc 界定符用 `__HF_EOF__`，prompt 内容直接粘贴进去，不转义
- 用户明确提到 `pro`（或要求用更强/专业模型处理复杂任务）时，在 `handoff run` 后加 `--pro`
- **文件名只能来自 `handoff new` 的输出，不得自己拼**；**不要**用 `> RESULT 2> OUT` 重定向——handoff 自己管命名和落盘
- `p=$(handoff new ...)` 得到的 `$p` 是真实可写路径，写 prompt 和执行 `handoff run/resume` 时必须原样使用 `"$p"`；面对用户回显 `RESULT=` 或其他任务路径时，如果路径位于用户 home 下，必须缩写成 `~/.handoff/...`，不要暴露 `/Users/<name>/...`

**启动命令后**（`run_in_background: true` 返回后），**从 stdout 捕获 handoff 打印的唯一有用的一行 `RESULT=<任务路径>`**，将 home 下路径缩写成 `~/.handoff/...` 后，在面向用户的 assistant 消息里回显这一条路径（完成后默认只读它）：

- `RESULT=<任务路径>`（最终结论文件，例如 `~/.handoff/tasks/0611-ds-03-fix-auth.result.md`）

**这条路径里同时编码了本次任务的 run_id**：去掉目录和 `.result.md` 后缀，文件名主干就是 run_id（上例 → `0611-ds-03-fix-auth`）。**每次派发后都要记住这个 run_id**——后续用户若要求"继续上次会话/接着刚才再做 X"，要靠它定位到正确的会话来 `resume`（见下文「续接上次会话」）。

其余无需你读取：
- handoff 把克制的进度信息打在 **stderr**，Claude Code 的 shell view 会自动实时显示——你不用、也不要把它读进上下文。
- 进度日志同时落在与 `RESULT=` **同名的 `.out.txt`**（把 `.result.md` 换成 `.out.txt`），仅在诊断（无结果/超时）时才 `tail -f` 或 `Read`。
- 输入文件 `.prompt.md`（同名）已是你刚发的内容，无需回显。

等待完成通知后，用 `Read` 读取对应的 `.result.md` 并汇报；**不要**再读后台输出（结果已在文件里，重复读只会把进度噪音吃进上下文）。若 `.result.md` 为空或异常，再读 `.out.txt` 诊断。
</interaction_contract>

## 运行任务

所有任务统一使用**后台模式**（`run_in_background: true`），不阻塞主会话。

### 单任务

按命令模板执行，启动后从 stdout 捕获 `RESULT=` 一行并回显，等通知后读该 `.result.md` 文件汇报。

### 并行多任务

在**同一条消息**里发出多个独立的 `run_in_background: true` Bash 调用，各自用 `handoff new` 分配路径、heredoc 写入不同的 prompt 内容，再各自 `handoff run`。每个任务启动后分别从各自 stdout 捕获 `RESULT=` 路径（handoff 自动递增 seq）。每个任务完成时分别通知，分别读取对应的 `.result.md` 汇报。

### 串行多任务

等上一个任务的完成通知到达，读取并汇报结果后，再启动下一个任务。

## 续接上次会话（resume 续派）

要接着某次任务继续（保留其上下文）而非开新会话时，先用 `handoff new` 分配新的 prompt 路径，再用 `resume` 替代 `run`，其余约定（后台、捕获新 `RESULT=`、读 `.result.md`）完全相同：

```bash
p=$(handoff new --backend deepseek --slug <任务助记词>)
cat > "$p" <<'__HF_EOF__'
[后续任务内容]
__HF_EOF__
handoff resume <run_id> --backend deepseek "$p"
```

- `<run_id>` 用该会话**首次**任务的 run_id（即上文那个文件名主干）；它是稳定句柄，每轮续接都用它，不要追每轮新生成的 run_id。
- **必须带 prompt 文件**。不带 prompt 的 `resume <run_id>` 是交互式重开，后台会卡死。
- 续接默认只继承 backend；原会话用过 `--pro` 的话，续接要再次带上才沿用 pro_model。
- 不确定用户指哪次任务时，报候选 run_id + 摘要让其确认，别猜。

## 完成后

收到后台完成通知后：
1. 用 `Read` 读取对应的 `RESULT=` 路径（`.result.md` 结果文件）
2. 汇总结果返回给用户
3. 若 `.result.md` 为空或异常，再读 `.out.txt`（进度日志）诊断
4. 如有后续任务（串行场景），此时启动下一个
