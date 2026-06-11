"""Interactive initializer for handoff."""

from __future__ import annotations

import os
import sys


def _pkg_root() -> str:
    """Absolute path to the cli/ package directory."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def _repo_root() -> str:
    """Absolute path to the repo root (for README hint only; may not exist in a wheel install)."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _home_path(*parts: str) -> str:
    return os.path.join(os.path.expanduser("~"), *parts)


def _color(code: str, text: str) -> str:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    return f"\033[{code}m{text}\033[0m"


def _planned_writes() -> list[tuple[str, str, str]]:
    skills_dir = os.path.join(_pkg_root(), "skills")
    from ..config import user_config_path

    plans: list[tuple[str, str, str]] = [
        ("config", "write if missing", user_config_path()),
    ]

    plans += [
        ("hard link", os.path.join(skills_dir, "handoff-ds.toml"), _home_path(".codex", "agents", "handoff-ds.toml")),
        ("soft link", os.path.join(skills_dir, "handoff-ds", "SKILL.md"), _home_path(".claude", "skills", "handoff-ds", "SKILL.md")),
        ("soft link", os.path.join(skills_dir, "handoff-codex", "SKILL.md"), _home_path(".claude", "skills", "handoff-codex", "SKILL.md")),
        ("soft link", os.path.join(skills_dir, "handoff-opus", "SKILL.md"), _home_path(".claude", "skills", "handoff-opus", "SKILL.md")),
    ]
    return plans


def _print_plan():
    print(_color("1", "handoff initialization"))
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


def _create_links():
    """Create hard/soft links for agent and skill files from cli/skills/."""
    skills_dir = os.path.join(_pkg_root(), "skills")

    # Hard link for Codex agent
    src_agent = os.path.join(skills_dir, "handoff-ds.toml")
    dest_agent = _home_path(".codex", "agents", "handoff-ds.toml")
    os.makedirs(os.path.dirname(dest_agent), exist_ok=True)
    if os.path.exists(dest_agent):
        os.remove(dest_agent)
    os.link(src_agent, dest_agent)
    print(f"hard link: {dest_agent} <=> {src_agent}")

    # Soft links for Claude Code skills (3 backends)
    for skill_name in ("handoff-ds", "handoff-codex", "handoff-opus"):
        src_skill = os.path.join(skills_dir, skill_name, "SKILL.md")
        dest_skill_dir = _home_path(".claude", "skills", skill_name)
        dest_skill = os.path.join(dest_skill_dir, "SKILL.md")
        os.makedirs(dest_skill_dir, exist_ok=True)
        if os.path.exists(dest_skill):
            os.remove(dest_skill)
        os.symlink(src_skill, dest_skill)
        print(f"soft link: {dest_skill} -> {src_skill}")


def run_init(assume_yes: bool = False):
    if not assume_yes and not _confirm():
        print("handoff: initialization cancelled")
        sys.exit(1)

    print("")
    from ..config import user_config_path, write_default_user_config

    wrote_config = write_default_user_config()
    if wrote_config:
        print(f"config: wrote {user_config_path()}")
    else:
        print(f"config: kept existing {user_config_path()}")

    _create_links()

    readme = os.path.join(_repo_root(), "README.md")

    print("")
    print("Next:")
    print(f"  1. Set DEEPSEEK_API_KEY in your shell, or edit {user_config_path()} and replace ${{DEEPSEEK_API_KEY}} with your token.")
    print(f"  2. Read {readme} for Codex and Claude Code usage.")


def cmd_init(args):
    if args and args[0] in ("-h", "--help"):
        print("usage: handoff init [-y|--yes]")
        return
    assume_yes = False
    for arg in args:
        if arg in ("-y", "--yes"):
            assume_yes = True
        else:
            print(f"handoff: init: unexpected argument '{arg}'", file=sys.stderr)
            sys.exit(2)
    run_init(assume_yes=assume_yes)
