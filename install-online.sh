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
#   DS_CLI_CCLEAN    override cclean binary path
#   CCLEAN_VERSION   pin a specific release tag  (default: latest)
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

# ----- install cclean (claude-clean) -----------------------------------------
_install_cclean() {
    local dest="${DS_CLI_CCLEAN:-$HOME/.local/bin/cclean}"

    if [ -x "$dest" ]; then
        echo "ds-cli: cclean already installed at $dest"
        return 0
    fi

    echo "ds-cli: installing cclean..."

    local os_name arch_name
    case "$(uname -s)" in
        Darwin) os_name="Darwin" ;;
        Linux)  os_name="Linux"  ;;
        *) echo "ds-cli: unsupported OS for cclean auto-install" >&2
           echo "ds-cli: install manually: https://github.com/ariel-frischer/claude-clean/releases" >&2
           return 1 ;;
    esac
    case "$(uname -m)" in
        arm64|aarch64) arch_name="arm64"  ;;
        x86_64)        arch_name="x86_64" ;;
        *) echo "ds-cli: unsupported arch for cclean auto-install" >&2
           echo "ds-cli: install manually: https://github.com/ariel-frischer/claude-clean/releases" >&2
           return 1 ;;
    esac

    local api_url="https://api.github.com/repos/ariel-frischer/claude-clean/releases/latest"
    if [ -n "${CCLEAN_VERSION:-}" ]; then
        api_url="https://api.github.com/repos/ariel-frischer/claude-clean/releases/tags/${CCLEAN_VERSION}"
    fi

    local asset_url
    asset_url="$(curl -fsSL "$api_url" | python3 -c "
import sys, json
os_name, arch_name = sys.argv[1], sys.argv[2]
data = json.load(sys.stdin)
for a in data.get('assets', []):
    n = a['name']
    if os_name in n and arch_name in n and (n.endswith('.tar.gz') or n.endswith('.zip')):
        print(a['browser_download_url'])
        break
" "$os_name" "$arch_name" 2>/dev/null || true)"

    if [ -z "$asset_url" ]; then
        echo "ds-cli: could not find cclean release for $os_name/$arch_name" >&2
        echo "ds-cli: install manually: https://github.com/ariel-frischer/claude-clean/releases" >&2
        return 1
    fi

    local tmp
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' RETURN

    echo "ds-cli: downloading $asset_url"
    curl -fsSL "$asset_url" | tar -xz -C "$tmp"

    local bin
    bin="$(find "$tmp" -name "cclean" -type f | head -1)"
    if [ -z "$bin" ]; then
        echo "ds-cli: could not find cclean binary in archive" >&2
        return 1
    fi

    mkdir -p "$(dirname "$dest")"
    chmod +x "$bin"
    mv "$bin" "$dest"
    echo "ds-cli: cclean installed at $dest"
}

_install_cclean || true

# ----- run ds-cli installer --------------------------------------------------
"$DEST/ds-cli" install --yes

echo
echo "ds-cli: installed."
echo "ds-cli: Make sure ~/bin is on your PATH, then run: ds-cli --help"
echo "ds-cli: Update any time with: ds-cli update"
