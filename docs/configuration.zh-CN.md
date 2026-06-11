# 配置

[← 返回 README](../README.zh-CN.md)

handoff 的配置分两层：**机制**（程序承诺，不可覆盖）和**数据**（用户资产，所见即所得）。

## 两层模型

```
cli/backend_types.yaml（机制：每种 type 怎么被拉起——flags、PTY）
        ↓  不可覆盖；同名键在用户 config 中出现会被警告并忽略
        ↓
~/.handoff/config.yaml（数据：backends 定义。handoff init 生成完整文件，
                        没有隐藏的合并层——你看到的就是实际运行的）
```

机制层随包分发（`cli/backend_types.yaml`），定义了 `claude` / `codex` 两种 type 的 CLI 命令、PTY 包装和 flag 模板。这些是程序行为的一部分，用户不能覆盖——改了也没用。

数据层就是你的 `~/.handoff/config.yaml`。`handoff init` 会生成一份含三个后端（deepseek / opus / codex）的完整配置；你只需填 deepseek 的 token。没有隐藏的默认值覆盖你的设置——文件里写的就是全部。

运行 `handoff env` 可以随时找到这两个文件的路径。

## 最小配置

opus / codex 走你本机的登录态，零配置。deepseek 只需一个 token——二选一：

**方式一：环境变量**（推荐）

```bash
export DEEPSEEK_API_KEY="sk-..."
```

**方式二：写在配置文件里**

```yaml
# ~/.handoff/config.yaml
backends:
  deepseek:
    env:
      ANTHROPIC_AUTH_TOKEN: "sk-..."
```

## 三个内置后端

| backend | type | 模型 | 底层 | 需要配置 |
| --- | --- | --- | --- | --- |
| `deepseek` | claude | `deepseek-v4-flash`（pro: `deepseek-v4-pro[1m]`） | `claude -p` → DeepSeek Anthropic 端点 | token |
| `opus` | claude | `claude-opus-4-8` | `claude -p` → 本机 Claude 登录态 | 无 |
| `codex` | codex | `gpt-5.5` | `codex exec` → 本机 Codex 登录态 | 无 |

默认后端是 `backends` 下的**第一个条目**。

## 后端解析

每个 backend 在运行时经历两步：

1. **机制合并**：`backend_types.yaml` 里该 `type` 的字段（command、pty、session_flags 等）作为基底
2. **用户数据覆盖**：你的 backend 字段（model、pro_model、env 等）深合并上去

合并语义：**映射递归合并，列表整体替换**（不会拼接）。`env` 是你全权书写的——机制层不带任何 `env` 映射，所有环境变量都由你设置。

字符串值里的 `${ENV_VAR}` 在合并后统一展开。未设置的环境变量展开为空字符串。

`type: claude` 的 backend 是**环境密闭**的：启动前会先清除继承自外层 shell 的
`ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_MODEL` 等已知变量，再应用你
`env` 块里声明的值——只有写在配置里的才生效。这保证了从一个连着别家端点的会话里
派发任务（比如在 DeepSeek 会话里咨询 opus）不会被外层环境劫持。

## 自定义 backend

### Anthropic 兼容端点

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

`type: claude` 的 backend 必须带有 `model` 字段（否则启动时报错）。`env` 块里的 `{model}` 占位符会在运行时替换为该 backend 解析出的模型名（`--pro` 时取 `pro_model`）。

### 本地 OpenCode proxy

```yaml
backends:
  opencode:
    type: claude
    model: deepseek-v4-flash
    pro_model: "deepseek-v4-pro[1m]"
    env:
      ANTHROPIC_BASE_URL: http://127.0.0.1:4000
      ANTHROPIC_AUTH_TOKEN: unused
      ANTHROPIC_MODEL: "{model}"
      ANTHROPIC_DEFAULT_OPUS_MODEL: "{pro_model}"
      ANTHROPIC_DEFAULT_SONNET_MODEL: "{model}"
      ANTHROPIC_DEFAULT_HAIKU_MODEL: "{model}"
      CLAUDE_CODE_SUBAGENT_MODEL: "{model}"
```

OpenCode 的本地 proxy 需要完整的 Anthropic 模型映射。你可以在 `env` 块里自由设置任意变量——没有限制。

## include 机制

```yaml
# ~/.handoff/config.yaml
include: ~/.handoff/private-tokens.yaml

backends:
  deepseek:
    model: deepseek-v4-flash  # 覆盖 include 进来的值
```

`include` 可以是字符串（单文件）或列表（多文件，按顺序合并）。路径解析：先相对于**当前文件所在目录**，再 fallback 到包目录。有循环检测（按 realpath 去重）。

## system_prompt 覆盖

`backend_types.yaml` 内置了一段 system_prompt（让模型直接执行、不反问）。你可以用自己的文本覆盖它：

```yaml
# ~/.handoff/config.yaml
system_prompt: |
  你是一个精于代码实现的助手。收到任务后直接开始写代码，不要...
```

这是唯一可以覆盖的内置值。其他机制层字段（`type_defaults`、flag 模板等）无法在用户 config 中覆盖——即使写了也会被警告并忽略。

## 可覆盖字段全表

`backends.<name>` 下可写的字段：

| 字段 | 说明 |
| --- | --- |
| `type` | `claude` 或 `codex` |
| `description` | 显示用描述（可选） |
| `model` | 默认模型名（claude 型必填） |
| `pro_model` | `--pro` 时使用的模型名 |
| `env` | 该 backend 专属的环境变量。支持 `{model}`、`{pro_model}`、`{home}` 占位符，以及 `${ENV_VAR}` shell 展开 |

顶层可写字段：

| 字段 | 说明 |
| --- | --- |
| `system_prompt` | 覆盖内置 system_prompt |
| `include` | 引用其他 YAML 文件 |

机制层（`cli/backend_types.yaml`）定义了 claude/codex 两种 type 的 `command`、`pty`、`session_flags`、`session_id_flags`、`continue_id_flags`、`resume_flags`。这些是程序行为，不可覆盖——想了解完整启动逻辑请直接读那个文件。
