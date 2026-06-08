# 命令参考

[← 返回 README](../README.zh-CN.md)

> **本文要讲什么(提纲,待扩充)**
> - 你通常通过 skill / subagent 调用它,但底层是普通 CLI
> - `run` 的全部用法:`--cwd` / 从文件 / 从 stdin / `--text` / `--pro` / `--fast` / `--from codex` 及其组合
> - `list` / `resume` / `tail` 的交互细节(TUI 快捷键、run-id 与 seq 的解析)
> - `install` / `update` 做了什么
> - run id 编码规则(`ds-<SEQ>-<MMDD>`,`01..99` / `A0..ZZ`,每日上限 1035)
> - 落盘文件布局与各文件含义(`.prompt.txt` / `.out.txt` / `.result.md`)
> - 运行状态:`running` / `success` / `error` / `interrupted`
>
> *(以下为已有内容,后续 session 继续补全上述提纲)*

---

你通常通过 skill / subagent 调用它,但底层就是一个普通 CLI:

```bash
ds-cli run --cwd /path/to/project prompt.txt   # 从文件派发任务
ds-cli run - <<'EOF'                            # 或从 stdin
重构 X 模块并补测试
EOF
ds-cli run --text "hi"                          # 冒烟测试,验证配置

ds-cli run --pro  prompt.txt                    # 用 pro_model 跑更复杂的任务
ds-cli run --fast prompt.txt                    # 用 fast_backend(可与 --pro 同用)
ds-cli run --from codex -                       # Codex subagent 专用:结束时仅输出 RESULT= 路径

ds-cli list                                     # 列出历史任务,看 prompt 全文 / 结果
ds-cli resume [<run-id|seq>]                    # 交互续接某次会话（等同旧 go）
ds-cli resume [<run-id|seq>] -                  # 非交互：把后续任务派发到同一会话
ds-cli resume [<run-id|seq>] --text "..."       # 非交互：同上，直接传文本
ds-cli tail [<run-id|seq>]                      # 实时跟踪某条 run 的输出流
```

run id 形如 `ds-<SEQ>-<MMDD>`(SEQ 为当日计数器 `01..99` / `A0..ZZ`)。每次运行都会落盘 `.prompt.txt`、`.out.txt`(进度)、`.result.md`(结果):

```text
~/.ds-cli/runs/     # 每次运行的元数据 / 流
~/.ds-cli/tasks/    # .prompt.txt / .out.txt / .result.md
```
