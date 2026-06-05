"""YAML configuration loading and merging for ds-cli.

Configuration flow:
  1. Load cli/default_config.yaml (system defaults, shipped with repo)
  2. If ~/.ds-cli/config.yaml is missing, run the interactive installer
  3. Load ~/.ds-cli/config.yaml (user-owned runtime config)
  4. Deep-merge user config on top of default

Backend resolution:
  - Resolved backend = backend_template + specific backend overrides
  - Template fields are defaults; backends can override any field
  - Backend instances only come from ~/.ds-cli/config.yaml
"""

from __future__ import annotations

import os
import sys
import copy
from typing import Optional

try:
    import yaml
except ImportError:
    print(
        "ds-cli: PyYAML is required. Install it with: pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(1)

_DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "default_config.yaml")
_DEFAULT_USER_CONFIG = """# ds-cli user configuration
# Created by ds-cli install.
#
# Edit this file and replace <YOUR_TOKEN> before using the default DeepSeek backend.
# backend_template comes from ds-cli's built-in defaults, so backend entries here only
# need to override fields that differ from the system template.

default_backend: default
fast_backend: default

backends:
  default:
    description: "DeepSeek API"
    ANTHROPIC_AUTH_TOKEN: "<YOUR_TOKEN>"

  # opencode:
  #   description: "Local OpenCode proxy"
  #   ANTHROPIC_BASE_URL: "http://127.0.0.1:4000"
  #   ANTHROPIC_AUTH_TOKEN: "unused"
"""


def user_config_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".ds-cli")


def user_config_path() -> str:
    return os.path.join(user_config_dir(), "config.yaml")


def _load_yaml(path: str) -> dict:
    """Load a YAML file, returning an empty dict if not found."""
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            print(f"ds-cli: config {path} must be a mapping", file=sys.stderr)
            sys.exit(1)
        return data
    except yaml.YAMLError as e:
        print(f"ds-cli: error parsing {path}: {e}", file=sys.stderr)
        sys.exit(1)


def write_default_user_config() -> bool:
    """Create the default user config if missing. Return True when written."""
    path = user_config_path()
    if os.path.isfile(path):
        return False

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(_DEFAULT_USER_CONFIG)
        return True
    except OSError as e:
        print(f"ds-cli: failed to create default user config at {path}: {e}", file=sys.stderr)
        sys.exit(1)


def _ensure_user_config_exists():
    if os.path.isfile(user_config_path()):
        return

    from .commands.install import run_install

    run_install()
    if not os.path.isfile(user_config_path()):
        print(f"ds-cli: initialization did not create {user_config_path()}", file=sys.stderr)
        sys.exit(1)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, return new dict."""
    result = copy.deepcopy(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = copy.deepcopy(val)
    return result


class Config:
    """Resolved ds-cli configuration."""

    def __init__(self):
        _ensure_user_config_exists()
        self.defaults = _load_yaml(_DEFAULT_CONFIG_PATH)
        self.user = _load_yaml(user_config_path())
        self._merged = _deep_merge(self.defaults, self.user)
        self._validate()

    @property
    def merged(self) -> dict:
        return self._merged

    @property
    def user_config_path(self) -> str:
        return user_config_path()

    @property
    def default_backend(self) -> str:
        return self._required("default_backend")

    @property
    def fast_backend(self) -> str:
        return self._required("fast_backend")

    @property
    def default_model(self) -> str:
        return self._required("default_model")

    @property
    def pro_model(self) -> str:
        return self._required("pro_model")

    @property
    def system_prompt(self) -> str:
        return self._merged.get("system_prompt", "")

    @property
    def backend_template(self) -> dict:
        return copy.deepcopy(self._merged.get("backend_template", {}))

    @property
    def backends(self) -> dict:
        """Return the resolved backends dict (merged with template)."""
        raw = self._merged.get("backends", {})
        if not isinstance(raw, dict):
            print("ds-cli: config key 'backends' must be a mapping", file=sys.stderr)
            sys.exit(1)
        result = {}
        template = self.backend_template
        for name, overrides in raw.items():
            if not isinstance(overrides, dict):
                print(f"ds-cli: backend '{name}' must be a mapping", file=sys.stderr)
                sys.exit(1)
            merged = _deep_merge(template, overrides)
            result[name] = merged
        return result

    def get_backend(self, name: str) -> Optional[dict]:
        """Resolve a named backend (returns deep-copied merged dict or None)."""
        backends = self.backends  # already merged with template
        return copy.deepcopy(backends.get(name))

    def get_config_paths(self) -> list[str]:
        """Return paths of all config source files (for mtime checks)."""
        paths = [_DEFAULT_CONFIG_PATH]
        user_config = user_config_path()
        if os.path.isfile(user_config):
            paths.append(user_config)
        return paths

    def _required(self, key: str):
        val = self._merged.get(key)
        if val in (None, ""):
            print(f"ds-cli: missing required config key: {key}", file=sys.stderr)
            sys.exit(1)
        return val

    def _validate(self):
        template = self._merged.get("backend_template", {})
        if not isinstance(template, dict) or not template:
            print("ds-cli: missing required config mapping: backend_template", file=sys.stderr)
            sys.exit(1)

        backends = self._merged.get("backends", {})
        if not isinstance(backends, dict) or not backends:
            print(
                "ds-cli: ~/.ds-cli/config.yaml must define at least one backend under 'backends'",
                file=sys.stderr,
            )
            sys.exit(1)

        for key in ("default_backend", "fast_backend"):
            backend_name = self._required(key)
            if backend_name not in backends:
                print(
                    f"ds-cli: config key '{key}' points to unknown backend '{backend_name}'",
                    file=sys.stderr,
                )
                sys.exit(1)
