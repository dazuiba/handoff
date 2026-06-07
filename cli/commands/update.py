"""Update ds-cli to the latest source and refresh links."""

from __future__ import annotations

import os
import subprocess
import sys

from ..homebrew import is_homebrew_install


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def cmd_update(args):
    if args and args[0] in ("-h", "--help"):
        print("usage: ds-cli update")
        return
    if args:
        print("ds-cli: update does not accept arguments", file=sys.stderr)
        sys.exit(2)

    if is_homebrew_install():
        print(
            "ds-cli: this installation is managed by Homebrew.\n"
            "  To update, run:  brew upgrade dazuiba/tap/ds-cli",
            file=sys.stderr,
        )
        sys.exit(0)

    root = _repo_root()
    if not os.path.isdir(os.path.join(root, ".git")):
        print(
            f"ds-cli: {root} is not a git checkout; reinstall with the online installer",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"ds-cli: updating {root}")
    pull = subprocess.run(["git", "-C", root, "pull", "--ff-only"], text=True)
    if pull.returncode != 0:
        print("ds-cli: git pull failed", file=sys.stderr)
        sys.exit(pull.returncode)

    # Re-link: the hard link to ds-agent.toml breaks when git replaces the file.
    script = os.path.join(root, "install.sh")
    relink = subprocess.run([script], text=True)
    if relink.returncode != 0:
        sys.exit(relink.returncode)

    print("ds-cli: up to date")
