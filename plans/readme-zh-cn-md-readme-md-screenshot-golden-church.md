# Plan: 压缩截图 + 优化 README 介绍语

## Context

README 中已有两处图片引用指向 `assets/` 目录（尚未创建）。`screenshot/` 中有 3 张截图。用户要求：转 JPG 压缩、插入 README 合适位置、优化中文 README 的介绍语。

## 一、截图处理

### 源 → 目标

| 源文件 | 尺寸 | 原始大小 | → JPG 目标 |
|---|---|---|---|
| `screenshot/claude-run.png` | 1530×1072 | 139K | `assets/claude-code.jpg` |
| `screenshot/claude-shell.png` | 1698×2462 | 668K | `assets/claude-shell.jpg` |
| `screenshot/codex-run.png` | 1242×744 | 163K | `assets/codex.jpg` |

### 步骤

1. `mkdir -p assets`
2. 用 `sips -s format jpeg` 转 PNG → JPG（macOS 内置，无需安装依赖）
3. 更新 README.md / README.zh-CN.md 中的图片引用：`.png` → `.jpg`
4. 在两张 README 的 Claude Code 节，`claude-code.jpg` 后插入 `claude-shell.jpg`（展示点开后台任务后的 shell 输出）

### 命名说明

图片名沿用 README 现有引用名（`claude-code` / `codex`），只改扩展名。`claude-shell` 为新增。

## 二、中文介绍语（slogan）

当前（`README.zh-CN.md#L5-6`）：

> 让旗舰模型（Claude Opus / GPT-5.5）做计划与验收，让 DeepSeek V4 做实际的编码。

问题：太啰嗦，像文档不像 slogan。

### 候选方案

1. **GPT-5.5 / Opus 指挥，DeepSeek V4 干活。**
   - 简洁直白，口语化，"干活"接地气

2. **让最贵的模型思考，最省的模型编码。**
   - 突出经济价值，一句话说清 why

3. **旗舰模型做架构师，DeepSeek V4 写代码。**
   - 角色比喻生动，任何人都能秒懂

4. **Opus 动脑，DeepSeek 动手。**
   - 四字对仗，最精炼

推荐 **方案 1**（最贴合你说的），英文 README 对应改为：

> GPT-5.5 / Opus plans; DeepSeek V4 codes.

## 三、修改的文件

1. **新建** `assets/claude-code.jpg`
2. **新建** `assets/claude-shell.jpg`
3. **新建** `assets/codex.jpg`
4. **编辑** `README.md` — `.png` → `.jpg`，插入 claude-shell 图，英文介绍语同步优化
5. **编辑** `README.zh-CN.md` — `.png` → `.jpg`，插入 claude-shell 图，替换 slogan

## 四、执行

用户要求用 **Sonnet** 执行。

## 五、验证

- `assets/` 下 3 个 jpg 存在，体积合理
- Markdown 预览图片正常渲染
- 中英文 README 的 alt text 各自正确
