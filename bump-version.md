# 发布版本流程

1. **先更新 `pyproject.toml` 中的版本号**
   ```bash
   # 编辑 pyproject.toml, 将 version = "X.Y.Z" 改到目标版本
   ```

2. **提交版本变更**
   ```bash
   git add pyproject.toml
   git commit -m "release: vX.Y.Z"
   ```

3. **打 tag（必须指向最新 commit）**
   ```bash
   git tag vX.Y.Z
   ```

   ⚠️ 如果 tag 打错位置（例如先打了 tag 忘了改 pyproject.toml）:
   ```bash
   git tag -d vX.Y.Z              # 删除本地错误 tag
   git tag vX.Y.Z HEAD            # 重新打到 HEAD
   git push origin vX.Y.Z --force # 强制更新远端 tag
   ```

4. **推送 commits + tags**
   ```bash
   git push && git push --tags
   ```

   **关键顺序**: 先改 `pyproject.toml` → commit → tag → push。
   tag 必须指向包含版本号变更的 commit，否则 PyPI 发布会带上错误的版本号。

5. 推送 `v*` tag 会自动触发 CI (`.github/workflows/publish.yml`)，执行:
   - `uv build` 构建
   - 发布到 PyPI
   - 创建 GitHub Release
