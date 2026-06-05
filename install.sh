#!/bin/bash
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"

link_soft() {
  local src="$1"
  local dest="$2"
  mkdir -p "$(dirname "$dest")"
  rm -f "$dest"
  ln -s "$src" "$dest"
  LINKS+=("soft $src $dest")
}

link_hard() {
  local src="$1"
  local dest="$2"
  mkdir -p "$(dirname "$dest")"
  rm -f "$dest"
  ln "$src" "$dest"
  LINKS+=("hard $src $dest")
}

LINKS=()

chmod +x "$SRC/ds-cli"

# First, run sync-agents to generate up-to-date files
echo "=== syncing agent files ==="
if python3 -c "import yaml" 2>/dev/null; then
    "$SRC/ds-cli" sync-agents || echo "warning: sync-agents failed, continuing"
else
    echo "warning: PyYAML not found, skipping sync-agents"
fi

echo "=== installing links ==="

link_soft "$SRC/ds-cli" "$HOME/bin/ds-cli"
link_hard "$SRC/ds-agent.toml" "$HOME/.codex/agents/ds-agent.toml"

link_soft "$SRC/SKILL.md" "$HOME/.claude/skills/ds-cli/SKILL.md"

printf 'installed ds-cli links from %s\n' "$SRC"
printf '\nlinks:\n'
for item in "${LINKS[@]}"; do
  read -r kind src dest <<< "$item"
  printf '%s: %s -> %s\n' "$kind" "$src" "$dest"
  ls -l "$src" "$dest"
done
