# 配置

[← 返回 README](../README.zh-CN.md)

> **本文要讲什么(提纲,待扩充)**
> - 配置文件的查找与合并机制(`cli/default_config.yaml` 默认值 → `~/.ds-cli/config.yaml` 覆盖)
> - 最小可用配置 / 填 token
> - `default_backend` / `fast_backend` 的语义,以及为什么没有 `--backend`
> - backend template 与 backend 的 deep-merge:每个 backend 继承哪些默认(claude flags、PTY、env)
> - 模型选择:`default_model` / `pro_model`,`--pro` 的作用
> - `system_prompt` 覆盖
> - `include:` 指令与 cycle 检测
> - 各类 endpoint 接法:DeepSeek 官方 / 本地 OpenCode proxy / 其他 anthropic 兼容端点
> - 可覆盖字段全表
>
> *(以下为已有内容,后续 session 继续补全上述提纲)*

---

`~/.ds-cli/config.yaml` **只写你的覆盖项**——仓库自带的默认值(模型、backend template、system prompt)会自动叠加在它之下,所以这个文件永远不需要引用源码路径。

## 最小可用配置

```yaml
default_backend: default   # 普通模式用哪个 backend
fast_backend: default      # --fast 时用哪个 backend

backends:
  default:
    description: "DeepSeek API"
    env:
      ANTHROPIC_AUTH_TOKEN: "sk-your-token"
```

默认 endpoint 为 `https://api.deepseek.com/anthropic`。当 token 仍是占位符 `<YOUR_TOKEN>` 时,`ds-cli run` 会在调用前直接报错。

## 改走本地 OpenCode proxy

加一个 backend 并切换指向即可:

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
      ANTHROPIC_BASE_URL: "http://127.0.0.1:4000"   # 见 github.com/iTzFaisal/oc-cc-proxy
      ANTHROPIC_AUTH_TOKEN: "unused"
```

## 可覆盖字段

可覆盖的全部字段(`default_model` / `pro_model` / `backend_template` / `system_prompt` 等)见 `cli/default_config.yaml`。命令行不提供 `--backend`——普通 / 快速模式分别用哪个 backend,由 `default_backend` / `fast_backend` 决定。
