#!/bin/bash
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"

link_soft() {
  local src="$1"
  local dest="$2"
  mkdir -p "$(dirname "$dest")"
  rm -f "$dest"
  ln -s "$src" "$dest"
  printf 'soft link: %s -> %s\n' "$dest" "$src"
}

link_hard() {
  local src="$1"
  local dest="$2"
  mkdir -p "$(dirname "$dest")"
  rm -f "$dest"
  ln "$src" "$dest"
  printf 'hard link: %s <=> %s\n' "$dest" "$src"
}

chmod +x "$SRC/ds-cli"

printf 'install.sh: refreshing links from %s\n' "$SRC"
link_soft "$SRC/ds-cli" "$HOME/bin/ds-cli"
link_hard "$SRC/ds-agent.toml" "$HOME/.codex/agents/ds-agent.toml"
link_soft "$SRC/SKILL.md" "$HOME/.claude/skills/ds-cli/SKILL.md"
