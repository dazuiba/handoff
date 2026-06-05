"""Interactive installer for ds-cli."""

from __future__ import annotations

import os
import subprocess
import sys

from ..config import user_config_path, write_default_user_config


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _home_path(*parts: str) -> str:
    return os.path.join(os.path.expanduser("~"), *parts)


def _color(code: str, text: str) -> str:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    return f"\033[{code}m{text}\033[0m"


def _planned_writes() -> list[tuple[str, str, str]]:
    root = _repo_root()
    return [
        ("config", "write if missing", user_config_path()),
        ("soft link", os.path.join(root, "ds-cli"), _home_path("bin", "ds-cli")),
        ("hard link", os.path.join(root, "ds-agent.toml"), _home_path(".codex", "agents", "ds-agent.toml")),
        ("soft link", os.path.join(root, "SKILL.md"), _home_path(".claude", "skills", "ds-cli", "SKILL.md")),
    ]


def _print_plan():
    print(_color("1", "ds-cli initialization"))
    print("")
    print("The following files and links will be written:")
    for kind, src, dest in _planned_writes():
        if kind == "config":
            if os.path.isfile(dest):
                print(f"  config: keep existing {dest}")
            else:
                print(f"  config: write {dest}")
        else:
            print(f"  {kind}: {dest} -> {src}")
    print("")


def _confirm() -> bool:
    _print_plan()
    try:
        answer = input("Type Y to continue, anything else to exit: ").strip()
    except EOFError:
        answer = ""
    return answer.lower() == "y"


def _run_install_sh():
    script = os.path.join(_repo_root(), "install.sh")
    try:
        result = subprocess.run([script], text=True, capture_output=True, check=False)
    except OSError as e:
        print(f"ds-cli: failed to run {script}: {e}", file=sys.stderr)
        sys.exit(1)

    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    if result.returncode != 0:
        print(f"ds-cli: install.sh exited with status {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)


def run_install():
    if not _confirm():
        print("ds-cli: initialization cancelled")
        sys.exit(1)

    print("")
    wrote_config = write_default_user_config()
    if wrote_config:
        print(f"config: wrote {user_config_path()}")
    else:
        print(f"config: kept existing {user_config_path()}")

    _run_install_sh()

    readme = os.path.join(_repo_root(), "README.md")
    print("")
    print("Next:")
    print(f"  1. Edit {user_config_path()} and replace <YOUR_TOKEN> with your auth token.")
    print(f"  2. Read {readme} for Codex and Claude Code usage.")


def cmd_install(args):
    if args and args[0] in ("-h", "--help"):
        print("usage: ds-cli install")
        return
    if args:
        print("ds-cli: install does not accept arguments", file=sys.stderr)
        sys.exit(2)
    run_install()
