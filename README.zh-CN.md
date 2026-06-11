<div align="center">

# handoff

**你的 coding agent 们，该互相派活了。**

在 Claude Code / Codex 里把活儿 handoff 给 DeepSeek，省下旗舰额度；
在 DeepSeek 会话里把难题 handoff 给 Codex / Opus，借个脑子。
不用切来切去，也不丢上下文。

[![PyPI](https://img.shields.io/pypi/v/handoff-cli)](https://pypi.org/project/handoff-cli/)
[![Python](https://img.shields.io/pypi/pyversions/handoff-cli)](https://pypi.org/project/handoff-cli/)

[English](README.md) · **简体中文**

</div>

<!-- assets/claude-code.jpg — 建议 720 宽 — 主演示图：Claude Code 里一句话派发，主会话只回显 RESULT=，完成后读 .result.md 汇报 -->
<img src="assets/claude-code.jpg" width="720" alt="在 Claude Code 里把任务 handoff 给 DeepSeek">

## 为什么需要 handoff

如果你同时用着几家 coding agent，这些场景你一定眼熟：

- 💸 **「Claude / Codex 订阅额度不经用」** — 你说：*「把上面 3 个任务，开 3 个 `/handoff-ds` 并行做」*。执行性工作 DeepSeek 干得又快又便宜，旗舰额度留给决策。
- 🤔 **「DeepSeek 干活时卡住了，想听听 Codex 的意见」** — 你说：*「问问 `/handoff-codex` 的意见」*。不用开新终端、复述半天背景，答案带回当前会话。
- 🔁 **「想接着上次派出去的活儿继续」** — 你说：*「接着刚才那个 `/handoff-ds` 的会话，继续做第 2 项」*。之前改过的文件、读过的代码、得出的结论全都还在。
- 🔄 **「想换个模型干活，就得重开会话、重述一遍背景」** — 不用换。你始终留在熟悉的会话里，handoff 在中间转交任务、拿回结果。

这就是全部用户界面：**在你的 agent 会话里说一句话**。

## 快速开始

```bash
uv tool install handoff-cli
handoff init        # 初始化配置，链接 skill / agent 文件
```

填上 DeepSeek 的 token（二选一）：设置环境变量 `DEEPSEEK_API_KEY`，或写进 `~/.handoff/config.yaml`。

然后回到 Claude Code，对它说：

> 制定计划，让 `/handoff-ds` 执行上述任务。

任务进入后台执行，不阻塞你的会话；完成后 agent 自动读取结果、向你汇报。

更新：`uv tool upgrade handoff-cli`。

<details>
<summary>没有 uv / 想从源码装？</summary>

<br>

`pipx install handoff-cli` 或 `pip install handoff-cli` 同样可用。源码安装：

```bash
git clone https://github.com/dazuiba/handoff && cd handoff
uv tool install -e .
handoff init
```

</details>

## 可以把活儿派给谁

| 提示词 / agent | 派给谁 | 底层 | 适合 |
| --- | --- | --- | --- |
| `/handoff-ds` | DeepSeek V4 | `claude -p`（DeepSeek Anthropic 端点） | 写代码、跑测试、重构、批量修改等执行性工作 |
| `/handoff-codex` | Codex (GPT-5.5) | `codex exec` | 复杂推理、第二意见、疑难调试 |
| `/handoff-opus` | Claude Opus | `claude -p` | 需要顶级模型出马的关键决策 |

> Codex 里没有 slash 命令，对应的是同名 subagent：说「让 `handoff-ds` 执行上述任务」即可。

三个目标开箱即用：opus / codex 走你本机的登录态，零配置；deepseek 只需 token。

## 任务派出去之后

派发和续接是 AI 的事（背后是 `handoff run` / `handoff resume`）；下面这些给你——看列表、盯进度：

<table>
<tr>
<td width="50%" valign="top">

**`handoff list`** — 交互式 TUI，浏览全部历史任务。看 prompt 全文、实时状态、最终结果；选中按 `G` 直接把那次会话重新加载进来接着聊。

</td>
<td width="50%" valign="top">

**`handoff tail <run-id>`** — 实时跟踪某条任务的输出流，相当于盯着它干活。

</td>
</tr>
<tr>
<td valign="top">

<!-- assets/list-tui.jpg — 建议 ~480 宽 — TUI 列表 + 详情视图，圈出 G/C 快捷键 -->
<img src="assets/list-tui.jpg" width="100%" alt="handoff list 交互式 TUI">

</td>
<td valign="top">

<!-- assets/tail.jpg — 建议 ~480 宽 — handoff tail 实时输出流 -->
<img src="assets/tail.jpg" width="100%" alt="handoff tail 实时跟踪">

</td>
</tr>
</table>

在 Claude Code 里还有个零成本选项：展开那条后台 shell，实时进度流就在那里——走 shell view，不烧主会话上下文。

<details>
<summary><b>并行派发多个任务</b></summary>

<br>

在同一条消息里让 agent 派出多个任务，各自独立执行、独立完成通知。handoff 自动递增 run 序号，互不干扰。

<!-- assets/parallel.jpg — 建议 621 宽 — 同一条消息派发 2~3 个后台任务，各自拿到不同 RESULT= 路径 -->
<img src="assets/parallel.jpg" width="621" alt="并行派发多任务">

</details>

## 它是怎么工作的

1. 你的 agent 把任务整包交给 handoff，**后台执行**，会话不阻塞。
2. handoff 在独立上下文里拉起对应的 CLI（`claude -p` / `codex exec`），完整输出流式落盘。
3. 主会话只拿到一行 `RESULT=<结果文件路径>`；执行进度打在后台 shell view 和 `.out.txt`，**不进**主会话上下文。
4. 完成后 agent 收到通知，读取 `.result.md`，向你汇报。
5. `RESULT=` 路径里编码着 run_id（如 `hd-0611-03`）——它是续接的稳定句柄，多轮续接始终指向同一个会话。

<details>
<summary><b>为什么值得：一笔账</b></summary>

<br>

在写代码、跑测试这类**事务性工作**上，DeepSeek V4 不输 Sonnet 级模型，价格只有零头。真正稀缺、值得为之付订阅费的，是顶端那一两个模型（Opus / GPT-5.5）的判断力。

| 方案 | 相对单价（干同样的活） |
| --- | --- |
| Claude Sonnet | 1×（基准） |
| DeepSeek 官方 API | **1/3** |
| [OpenCode Go](https://opencode.ai/go?ref=D5926WCTD8)（含 DeepSeek V4） | **1/18** |

旗舰模型负责沟通、拆解、验收；执行全部 handoff 出去。$20 的订阅指挥 $5 的算力，干出 ~$200 的活。

</details>

## 配置

内置三个目标开箱即用，最小配置只需 DeepSeek token：

```yaml
# ~/.handoff/config.yaml —— 也可以用环境变量 DEEPSEEK_API_KEY 代替，文件留空
backends:
  deepseek:
    env:
      ANTHROPIC_AUTH_TOKEN: "sk-..."
```

想接入其他 anthropic 兼容端点？加一段自定义目标即可：

```yaml
backends:
  kimi:
    type: claude
    model: kimi-k3
    env:
      ANTHROPIC_BASE_URL: https://api.moonshot.cn/anthropic
      ANTHROPIC_AUTH_TOKEN: "${MOONSHOT_API_KEY}"
```

合并机制、全部可覆盖字段见 **[配置文档 →](docs/configuration.zh-CN.md)**。

## 更多

- **[命令参考 →](docs/cli-reference.zh-CN.md)** — `run` / `resume` / `list` / `tail` / `init` 全部用法，run id 编码与落盘文件布局。
- **[配置文档 →](docs/configuration.zh-CN.md)** — type_defaults 合并机制、自定义目标、`${ENV}` 插值。
- **[设计说明 →](docs/design.zh-CN.md)** — 为什么 Claude Code 用后台 shell、Codex 用 subagent；RESULT= 协议细节。
