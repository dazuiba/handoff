"""ds-cli sync-agents command.

Generates ds-agent.toml and SKILL.md from templates and backend configuration.
"""

import os
import sys
from ..config import Config

_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

_AGENT_TEMPLATE = os.path.join(_TEMPLATES_DIR, "ds-agent.toml.in")
_SKILL_TEMPLATE = os.path.join(_TEMPLATES_DIR, "SKILL.md.in")
_AGENT_OUTPUT = os.path.join(_PROJECT_DIR, "ds-agent.toml")
_SKILL_OUTPUT = os.path.join(_PROJECT_DIR, "SKILL.md")


def _read_template(path: str) -> str:
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        print(f"ds-cli: template not found: {path}", file=sys.stderr)
        sys.exit(1)


def _build_backends_section(config: Config) -> str:
    """Build a human-readable backends listing for embedding in generated files."""
    backends = config.backends
    if not backends:
        return "  （无可用后端；请检查配置）"

    lines = ["| backend | default | base URL | description |", "| --- | --- | --- | --- |"]
    for name in sorted(backends.keys()):
        cfg = backends[name]
        url = cfg.get("ANTHROPIC_BASE_URL", "")
        default = "yes" if name == config.default_backend else ""
        description = cfg.get("description", "")
        lines.append(f"| `{name}` | {default} | {url} | {description} |")
    return "\n".join(lines)


def _build_backend_flags(config: Config, backends_section: str) -> tuple:
    """Return (default_backend_name, backend_flag_str, other_names_str)."""
    default = config.default_backend
    other_backends = [n for n in sorted(config.backends.keys()) if n != default]
    other_str = "、".join(other_backends) if other_backends else "无"
    return default, other_str


def _source_paths(config: Config) -> list[str]:
    paths = list(config.get_config_paths())
    for tpl in [_AGENT_TEMPLATE, _SKILL_TEMPLATE]:
        if os.path.isfile(tpl):
            paths.append(tpl)
    return paths


def _targets_up_to_date(config: Config) -> bool:
    target_paths = [_AGENT_OUTPUT, _SKILL_OUTPUT]
    if any(not os.path.isfile(p) for p in target_paths):
        return False
    source_paths = [p for p in _source_paths(config) if os.path.isfile(p)]
    if not source_paths:
        return True
    try:
        source_mtime = max(os.path.getmtime(p) for p in source_paths)
        target_mtime = min(os.path.getmtime(p) for p in target_paths)
    except OSError:
        return False
    return source_mtime <= target_mtime


def sync_agents(config: Config, force: bool = False, quiet: bool = False):
    """Generate ds-agent.toml and SKILL.md from templates.

    Returns True if files were generated, False if skipped (up-to-date).
    Returns None on error.
    """
    if not force and _targets_up_to_date(config):
        return False

    agent_tpl = _read_template(_AGENT_TEMPLATE)
    skill_tpl = _read_template(_SKILL_TEMPLATE)

    # Build backends section
    backends_section = _build_backends_section(config)
    default_backend, other_backends = _build_backend_flags(config, backends_section)

    # Determine backend flag for the command template
    if default_backend and default_backend != "opencode-proxy":
        backend_flag = f"--backend {default_backend} "
    else:
        backend_flag = ""

    # Agent variables
    agent_vars = {
        "BACKENDS_SECTION": backends_section,
        "BACKEND_FLAG": backend_flag,
        "DEFAULT_BACKEND": default_backend,
    }

    skill_vars = {
        "BACKENDS_SECTION": backends_section,
        "BACKEND_FLAG": backend_flag,
        "DEFAULT_BACKEND_NAME": default_backend,
        "OTHER_BACKEND_NAMES": other_backends,
    }

    # Substitute
    agent_content = _substitute(agent_tpl, agent_vars)
    skill_content = _substitute(skill_tpl, skill_vars)

    # Write files
    wrote_any = False
    try:
        with open(_AGENT_OUTPUT, "w") as f:
            f.write(agent_content)
        if not quiet:
            print(f"  generated: {_AGENT_OUTPUT}")
        wrote_any = True
    except OSError as e:
        print(f"ds-cli: error writing {_AGENT_OUTPUT}: {e}", file=sys.stderr)
        return None

    try:
        with open(_SKILL_OUTPUT, "w") as f:
            f.write(skill_content)
        if not quiet:
            print(f"  generated: {_SKILL_OUTPUT}")
        wrote_any = True
    except OSError as e:
        print(f"ds-cli: error writing {_SKILL_OUTPUT}: {e}", file=sys.stderr)
        return None

    return wrote_any


def _substitute(template: str, vars: dict) -> str:
    """Simple placeholder substitution: {KEY} → value."""
    result = template
    for key, val in vars.items():
        result = result.replace("{" + key + "}", val)
    # Leave any remaining {PLACEHOLDERS} as-is
    return result


def cmd_sync_agents(argv: list[str], config: Config):
    """ds-cli sync-agents [--force]"""
    force = False
    for a in argv:
        if a == "--force":
            force = True
        elif a in ("-h", "--help"):
            print("usage: ds-cli sync-agents [--force]")
            sys.exit(0)
        else:
            print(f"ds-cli sync-agents: unknown option {a}", file=sys.stderr)
            sys.exit(2)

    result = sync_agents(config, force=force)
    if result is None:
        sys.exit(1)
    elif result:
        print("ds-cli: agent files synced")
    else:
        print("ds-cli: agent files up to date")


def check_auto_sync(config: Config) -> bool:
    """Check if source files are newer than generated files, and auto-sync if needed.

    Returns True if sync was performed, False if not needed.
    Calls sys.exit(1) on sync failure.
    """
    if not _targets_up_to_date(config):
        result = sync_agents(config, quiet=True)
        if result is None:
            print("ds-cli: auto-sync failed", file=sys.stderr)
            sys.exit(1)
        return True

    return False
