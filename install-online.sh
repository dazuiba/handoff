#!/usr/bin/env bash
# ds-cli installer — works both locally and via `curl | bash`.
#
# If run from within a ds-cli checkout (the usual dev path), installs directly.
# If run from curl on a machine with no checkout, clones first.
#
# curl -fsSL https://raw.githubusercontent.com/dazuiba/ds-cli/main/install-online.sh | bash
#
# Overridable via env:
#   DS_CLI_REPO      git URL to clone           (default: https://github.com/dazuiba/ds-cli.git)
#   DS_CLI_HOME      where to keep the checkout  (default: $XDG_DATA_HOME/ds-cli)
set -euo pipefail

command -v python3 >/dev/null 2>&1 || { echo "ds-cli: python3 is required" >&2; exit 1; }
command -v git     >/dev/null 2>&1 || { echo "ds-cli: git is required"     >&2; exit 1; }
command -v curl    >/dev/null 2>&1 || { echo "ds-cli: curl is required"    >&2; exit 1; }

# ----- ensure uv is available ------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
    echo "ds-cli: uv not found, installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# ----- detect whether we're already inside the repo --------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd || echo "")"
IN_REPO=false
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/ds-cli" ] && [ -d "$SCRIPT_DIR/.git" ]; then
    IN_REPO=true
fi

if $IN_REPO; then
    echo "ds-cli: installing from local checkout ($SCRIPT_DIR)"
    DEST="$SCRIPT_DIR"
else
    DEST="${DS_CLI_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/ds-cli}"

    if [ -d "$DEST/.git" ]; then
        echo "ds-cli: updating existing checkout at $DEST"
        git -C "$DEST" pull --ff-only
    else
        REPO="${DS_CLI_REPO:-https://github.com/dazuiba/ds-cli.git}"
        echo "ds-cli: cloning $REPO into $DEST"
        mkdir -p "$(dirname "$DEST")"
        git clone --depth 1 "$REPO" "$DEST"
    fi
fi

# ----- run ds-cli installer --------------------------------------------------
"$DEST/ds-cli" install --yes

echo
echo "ds-cli: installed."
echo "ds-cli: Make sure ~/bin is on your PATH, then run: ds-cli --help"
echo "ds-cli: Update any time with: ds-cli update"
