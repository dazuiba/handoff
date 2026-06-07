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

# Detect Homebrew installation — don't symlink ~/bin/ds-cli if managed by brew
IS_HOMEBREW=false
case "$(realpath "$0" 2>/dev/null || readlink -f "$0" 2>/dev/null || echo "$0")" in
  /usr/local/Cellar/*|/opt/homebrew/Cellar/*)
    IS_HOMEBREW=true
    ;;
esac

# Also check HOMEBREW_CELLAR env var
if [ -n "${HOMEBREW_CELLAR:-}" ]; then
  case "$SRC" in
    $HOMEBREW_CELLAR/*) IS_HOMEBREW=true ;;
  esac
fi

printf 'install.sh: refreshing links from %s\n' "$SRC"

if $IS_HOMEBREW; then
  printf 'Homebrew installation detected — skipping ~/bin/ds-cli symlink.\n'
else
  link_soft "$SRC/ds-cli" "$HOME/bin/ds-cli"
fi

link_hard "$SRC/ds-agent.toml" "$HOME/.codex/agents/ds-agent.toml"
link_soft "$SRC/SKILL.md" "$HOME/.claude/skills/ds-cli/SKILL.md"
