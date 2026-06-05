#!/bin/bash
# reset-state.sh — Clean ds-cli runtime state and rebuild directories.
#
# Deletes runtime data only: ~/.ds-cli/runs/, ~/.ds-cli/tasks/, /tmp/dscli/
# Does NOT touch the repo source (~/dev/github/ds-cli/).
# Run after schema changes to start with a clean slate.

set -euo pipefail

STATE_DIR="$HOME/.ds-cli"
TMP_DIR="/tmp/dscli"

echo "=== ds-cli state reset ==="

# ── Runtime state dirs under ~/.ds-cli ──
for dir in "$STATE_DIR/runs" "$STATE_DIR/tasks"; do
    if [ -d "$dir" ]; then
        rm -rf "$dir"
        echo "  removed: $dir/"
    else
        echo "  absent:  $dir/"
    fi
done

# ── Legacy /tmp/dscli ──
if [ -d "$TMP_DIR" ]; then
    rm -rf "$TMP_DIR"
    echo "  removed: $TMP_DIR/"
else
    echo "  absent:  $TMP_DIR/"
fi

# ── Recreate essential directories ──
mkdir -p "$STATE_DIR/runs" "$STATE_DIR/tasks"
echo "  created: $STATE_DIR/runs/"
echo "  created: $STATE_DIR/tasks/"

echo "=== done ==="
echo "Run 'ds-cli run-demo <prompt>' to verify new state."
