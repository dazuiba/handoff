# 配置

[← 返回 README](../README.zh-CN.md)

handoff 开箱即用——三个内置后端（deepseek / opus / codex）自带完整的启动契约，`~/.handoff/config.yaml` 只需写你要覆盖的部分。

## 配置层级

```
cli/default_config.yaml（内置默认值，含 type_defaults + 三个 backend）
        ↓  deep-merge（列表替换，字符串值支持 ${ENV_VAR} 插值）
~/.handoff/config.yaml（用户覆盖）
```

用户配置文件支持 `include:` 指令（字符串或列表），被 include 的文件先合并，再被当前文件的键覆盖。有循环检测。

## 最小配置

opus / codex 走你本机的登录态，零配置。deepseek 只需一个 token——二选一：

**方式一：环境变量**（推荐，文件可留空）

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

内置的 deepseek backend 已声明 `ANTHROPIC_AUTH_TOKEN: "${DEEPSEEK_API_KEY}"`——`${}` 语法会在加载时展开为环境变量的值，不设置就是空字符串。

## 三个内置后端

| backend | type | 模型 | 底层 | 需要配置 |
| --- | --- | --- | --- | --- |
| `deepseek` | claude | `deepseek-v4-flash`（pro: `deepseek-v4-pro[1m]`） | `claude -p` → DeepSeek Anthropic 端点 | token |
| `opus` | claude | `claude-opus-4-8` | `claude -p` → 本机 Claude 登录态 | 无 |
| `codex` | codex | `gpt-5.5` | `codex exec` → 本机 Codex 登录态 | 无 |

默认后端是 `deepseek`（由 `default_backend` 键指定）。

## type_defaults 合并机制

每个 backend 有一个 `type`（`claude` 或 `codex`）。解析时：

```
type_defaults[<type>]  →  backends.<name>  →  用户配置
```

三层 deep-merge。**映射递归合并，列表整体替换**（不会拼接）。字符串值里的 `${ENV_VAR}` 在合并后统一展开。

这意味着：
- 所有 `type: claude` 的 backend 自动继承 PTY 包装、stream-json 格式、session flag 模板
- 所有 `type: codex` 的 backend 自动继承 `codex exec --json` 的 flag 模板
- 每个 backend 只需声明自己的 endpoint / token / model

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
```

`type: claude` 的 backend 必须带有 `model` 字段（否则启动时报错），除非有旧版顶层 `default_model` 作 fallback。

### 本地 OpenCode proxy

```yaml
default_backend: opencode

backends:
  opencode:
    type: claude
    model: deepseek-v4-flash
    pro_model: deepseek-v4-pro[1m]
    env:
      ANTHROPIC_BASE_URL: http://127.0.0.1:4000
      ANTHROPIC_AUTH_TOKEN: unused
```

## include 机制

```yaml
# ~/.handoff/config.yaml
include: ~/.handoff/private-tokens.yaml

backends:
  deepseek:
    model: deepseek-v4-flash  # 覆盖 include 进来的值
```

`include` 可以是字符串（单文件）或列表（多文件，按顺序合并）。路径解析：先相对于**当前文件所在目录**，再 fallback 到包目录。有循环检测（按 realpath 去重）。

## 可覆盖字段全表

`type_defaults.<type>` 下可覆盖的字段（影响该类型所有 backend 的启动方式）：

| 字段 | 说明 |
| --- | --- |
| `command` | CLI 命令名（默认 `claude` / `codex`） |
| `pty` | PTY 包装命令列表（claude 型默认 `["script", "-q", "/dev/null"]`；codex 型为 `[]`） |
| `env` | 环境变量映射（支持 `{model}`、`{pro_model}`、`{home}` 占位符） |
| `session_flags` | 新会话的 flag 模板（支持 `{prompt}`、`{model}`、`{cwd}` 等） |
| `session_id_flags` | 指定会话 ID 的 flag 模板（`{session_id}`） |
| `continue_id_flags` | 非交互续接的 flag 模板 |
| `resume_flags` | 交互重开的 flag 模板 |

`backends.<name>` 下可覆盖的字段：

| 字段 | 说明 |
| --- | --- |
| `type` | `claude` 或 `codex` |
| `description` | 显示用描述 |
| `model` | 默认模型名 |
| `pro_model` | `--pro` 时使用的模型名 |
| `env` | 该 backend 专属的环境变量（与 type_defaults 的 env 合并） |

顶层可覆盖字段：

| 字段 | 说明 |
| --- | --- |
| `default_backend` | 默认使用的 backend 名称 |
| `system_prompt` | 追加给 claude 型 backend 的系统提示词 |

完整默认值见仓库内的 `cli/default_config.yaml`。
