.PHONY: render skills

render:  ## Preview PyPI long description rendering
	pip install -q "readme_renderer[md]" 2>/dev/null
	python -m readme_renderer README.md > /tmp/handoff-pypi-preview.html
	@echo "✅  /tmp/handoff-pypi-preview.html  ($(shell wc -c < /tmp/handoff-pypi-preview.html | tr -d ' ') bytes)"
	open /tmp/handoff-pypi-preview.html

# ── skill 文档同步 ──────────────────────────────────────────────────
# handoff-ds/SKILL.md 是主文档（master），只改它。
# 它的 frontmatter（顶部的 `---...---` 块）不同步；其下的正文会被复制到
# 其它 backend 的 SKILL.md，并把 backend 名/缩写替换成对应值。占位符在
# 「构建时」由 sed 替换，落盘的都是具体值——LLM 永远读不到占位符。
SKILLS := cli/skills
MASTER := $(SKILLS)/handoff-ds/SKILL.md

skills:  ## 把 handoff-ds/SKILL.md 正文同步到其它 backend 的 SKILL.md
	@$(call sync_skill,handoff-codex,codex,cx)
	@$(call sync_skill,handoff-opus,opus,op)
	@echo "done."

# $(1)=目标目录  $(2)=backend 名  $(3)=run_id 缩写
define sync_skill
target="$(SKILLS)/$(1)/SKILL.md"; \
tmp=$$(mktemp); \
awk '{print} /^---[[:space:]]*$$/{n++; if(n==2) exit}' "$$target" > "$$tmp"; \
awk 'body{print} /^---[[:space:]]*$$/{n++; if(n==2) body=1}' "$(MASTER)" \
  | sed -e 's/deepseek/$(2)/g' \
        -e 's/handoff-ds/handoff-$(2)/g' \
        -e 's/0613-ds-/0613-$(3)-/g' >> "$$tmp"; \
mv "$$tmp" "$$target"; \
echo "synced $$target (backend=$(2))";
endef
