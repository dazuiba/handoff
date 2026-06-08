# ds-cli

[English](README.EN.md) · **中文**

> **Delegate tasks to DeepSeek right inside your Claude Code / Codex sessions.**

让 **SOTA 旗舰模型**只做架构与决策，其余一切脏活累活全自动派发给 DeepSeek V4。

`ds-cli` 是一个伪装成 `claude` 客户端的 DeepSeek 异步执行器。它把复杂任务派发到后台独立上下文运行


## 为什么要用它 / Why

一个被低估的事实:在写代码、跑测试这类**事务性工作**上,DeepSeek V4 已经比 Sonnet、GPT-5.4 更聪明,还更便宜。真正稀缺、值得为之付费的,只有那一两个站在顶端的模型(Opus / GPT-5.5)。

所以分工应该是:

- **最聪明的旗舰模型只做三件事**:和你沟通、拆解任务、验收结果。
- **其余一切"干活"**——写代码、跑测试、调试、改文件——全部交给 DeepSeek V4。

干同样的活,要花多少钱:

| 方案 | 相对单价(干同样的活) |
| --- | --- |
| Claude Sonnet | 1×(基准) |
| DeepSeek 官方 API | **1/3** |
| [OpenCode Go](https://opencode.ai/go?ref=D5926WCTD8)(含 DeepSeek V4) | **1/18** |

> OpenCode Go **$5/月** 相当于约 **$60** 的用量,即官方 DeepSeek 价格的 **1/6**;官方 DeepSeek 又是 Sonnet 的 1/3,所以 OpenCode 折合 Sonnet 基准 = 1/3 × 1/6 = **1/18**。

👉 旗舰模型用 **$20 的 Codex 套餐**指挥,干活挂 **$5 的 OpenCode Go**——一共 **$25/月,干出价值约 $200 的活(≈10×)**。

还有第二层好处:一个真实任务会产出几千行进度输出。直接在主会话里跑,这些噪音要么阻塞会话、要么被读进上下文,白白烧掉旗舰模型的 token。ds-cli 把执行整包外包,**主 session 只回灌一行 `RESULT=` 结果路径**;进度实时打在后台 shell view 里(见下方"查看与接管运行中的任务"),**不进**主上下文。

## 怎么用

让你的 agent 先制定计划,再把执行交给 ds-cli。

| | Claude Code | Codex |
| --- | --- | --- |
| 提示词 | "让 `/ds-cli` 执行上述任务" | "让 `ds-agent` 执行上述任务" |
| 机制 | 直接触发 `ds-cli` 命令(后台 shell) | 拉起 subagent 后台执行 |
| 看进度 | 展开后台 shell view 或 ds-cli tail | ds-cli tail |

<details>
<summary>为何codex/claude 机制不统一?</summary>

<br>

- **Claude Code 对后台 shell 支持极好**:能以**通知**方式感知任务"完成",还能实时看进度(stderr)。所以直接把 `ds-cli` 跑在后台 shell 即可,主 session 全程不阻塞、也几乎不耗 token。
- **Codex 不支持通知,只能轮询**:每轮询一次就消耗一次主 session 的 cache read,对动辄 5~10 分钟的任务会烧掉大量 token。但 Codex 能感知 **subagent 的完成事件**——所以改用一个廉价模型(`gpt-5.4-low`)做 subagent,**阻塞式**调用 `ds-cli run --from codex`,直到结束才把一行 `RESULT=` 路径带回主 session。
  - 为什么不用更便宜的 `gpt-5.4-mini`?它指令遵循太差,会自己动手干活,而不是老老实实把任务派给 ds-cli。

</details>


### Claude Code — `/ds-cli` skill

> 制定计划,并让 `/ds-cli` 执行上述任务。

每个任务会作为**后台 shell 命令**派发,点开即可实时查看 ds-cli 的执行进度;主 session 只拿到一行 `RESULT=` 结果路径。

<!-- 替换为: assets/claude-code.jpg — 建议 621 宽 — 换成一个"真实编码任务"(不要 print hi):展示后台派发 + 主 session 只回显 RESULT= + 完成后读 .result.md 汇报。 -->
<img src="assets/claude-code.jpg" width="621" alt="Claude Code 后台派发 ds-cli">

### Codex — `ds-agent` subagent

> 制定计划,并让 `ds-agent` 执行上述任务。

Codex 会拉起 subagent 在后台阻塞执行;为避免把大段结果读进 subagent 上下文,`ds-agent` 只在结束时带回一行 `RESULT=`。需要看进度时用 `ds-cli tail`。

<!-- 替换为: assets/codex.jpg — 建议 621 宽 — 重拍一张文字不被右侧截断的完整图。 -->
<img src="assets/codex.jpg" width="621" alt="Codex 唤起 ds-agent subagent">

这就是全部思路:旗舰模型负责拆解与验收,DeepSeek V4 负责廉价地执行。

## 查看与接管运行中的任务

任务派发出去后,有两条途径看进度、甚至把它捞回来接着聊。

**1. 在 Claude Code **:展开那条后台 shell,就能看到 `cclean` 压缩过的实时进度流——它走 shell view,**不进**主 session 上下文。

<!-- 替换为: assets/shell.jpg — 建议 621 宽 — 后台 shell 展开后的紧凑实时进度流,体现"看得见但不烧 context"。 -->
<img src="assets/shell.jpg" width="621" alt="后台 shell 的实时进度">

**2. 用命令行**:

<table>
<tr>
<td width="50%" valign="top">

`ds-cli list` — 可滚动的历史任务 TUI,看 prompt 全文 / 结果,按 `G` 可用你配置的backend(deepseek claude) 打开这个会话

</td>
<td width="50%" valign="top">

`ds-cli tail <run-id>` — 实时跟踪某条 run 的输出流。

</td>
</tr>
<tr>
<td valign="top">

<!-- 替换为: assets/list-tui.jpg — 建议 ~480 宽 — curses 列表 + 详情视图,圈出 G/C 快捷键。 -->
<img src="assets/list-tui.jpg" width="100%" alt="ds-cli list 交互式 TUI">
<br>
`ds-cli list` 里选中某条按 `G`,或直接 `ds-cli resume <seq>`,用 backend 把那次会话用 claude 重新加载,接着聊。也可以用 `ds-cli resume <seq> - <<'EOF' ... EOF` 把后续任务非交互派发到同一会话。
</td>
<td valign="top">

<!-- 替换为: assets/tail.jpg — 建议 ~480 宽 — ds-cli tail 实时输出流。 -->
<img src="assets/tail.jpg" width="100%" alt="ds-cli tail 实时跟踪">

</td>
</tr>
</table>

<details>
<summary><b>并行派发多个任务</b></summary>

<br>

在同一条消息里发出多个后台任务,各自独立完成、独立通知。ds-cli 自动递增 run 的 seq,互不干扰。

<!-- 替换为: assets/parallel.jpg — 建议 621 宽 — 同一条消息派发 2~3 个后台任务,各自拿到不同 RESULT= 路径。 -->
<img src="assets/parallel.jpg" width="621" alt="并行派发多任务">

</details>

---

## 安装

### Homebrew（推荐）

```bash
brew install dazuiba/tap/ds-cli
```

装好后运行 `ds-cli install` 初始化配置,再编辑 `~/.ds-cli/config.yaml` 填入你的 token:

```yaml
default_backend: default
fast_backend: default
backends:
  default:
    env:
      ANTHROPIC_AUTH_TOKEN: "sk-your-token"   # 默认走 https://api.deepseek.com/anthropic
```

### 在线安装

```bash
curl -fsSL https://raw.githubusercontent.com/dazuiba/ds-cli/main/install-online.sh | bash
```

需要 Python 3.10+ 和 git。安装脚本会把 ds-cli 链接到 Claude Code、Codex 和 shell 各自查找的位置:

```text
~/bin/ds-cli                       -> <checkout>/ds-cli            # 命令入口
~/.codex/agents/ds-agent.toml      -> <checkout>/ds-agent.toml     # Codex subagent
~/.claude/skills/ds-cli/SKILL.md   -> <checkout>/SKILL.md          # Claude Code skill
```

装好后编辑 `~/.ds-cli/config.yaml` 填入你的 token,最小配置:

```yaml
default_backend: default
fast_backend: default
backends:
  default:
    env:
      ANTHROPIC_AUTH_TOKEN: "sk-your-token"   # 默认走 https://api.deepseek.com/anthropic
```

完整配置(本地 OpenCode proxy、模型/system prompt 覆盖、全部可覆盖字段)见 **[配置文档 →](docs/configuration.zh-CN.md)**。

> 想自己 clone?`git clone` 仓库后执行 `./ds-cli install`,前提是系统有 `uv`。

## 更新

- **Homebrew 安装**: `brew upgrade dazuiba/tap/ds-cli`
- **源码安装**: `ds-cli update`（拉取最新源码到 checkout,并刷新链接）

## 更多

- **[命令参考 →](docs/cli-reference.zh-CN.md)** — `run` / `list` / `resume` / `tail` / `install` / `update` 全部用法,run id 编码与落盘文件布局。
- **[配置文档 →](docs/configuration.zh-CN.md)** — backend 合并机制、OpenCode proxy、可覆盖字段全表。
