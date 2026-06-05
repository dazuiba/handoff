"""YAML configuration loading and merging for ds-cli.

Configuration flow:
  1. Load cli/default_config.yaml (system defaults, shipped with repo)
  2. Load ~/.ds-cli/config.yaml (user overrides, optional)
  3. Deep-merge user config on top of default

Backend resolution:
  - Resolved backend = backend_template + specific backend overrides
  - Template fields are defaults; backends can override any field
  - Placeholders like {default_model}, {pro_model}, {prompt}, etc.
    are substituted at env/args build time (see cli/backend.py)
"""

from __future__ import annotations

import os
import sys
import copy

try:
    import yaml
except ImportError:
    print(
        "ds-cli: PyYAML is required. Install it with: pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(1)

_DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "default_config.yaml")
_USER_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".ds-cli", "config.yaml")


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
        self.defaults = _load_yaml(_DEFAULT_CONFIG_PATH)
        self.user = _load_yaml(_USER_CONFIG_PATH)
        self._merged = _deep_merge(self.defaults, self.user)

    @property
    def merged(self) -> dict:
        return self._merged

    @property
    def default_backend(self) -> str:
        return self._required("default_backend")

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
        result = {}
        template = self.backend_template
        for name, overrides in raw.items():
            merged = _deep_merge(template, overrides)
            result[name] = merged
        return result

    def get_backend(self, name: str) -> dict | None:
        """Resolve a named backend (returns deep-copied merged dict or None)."""
        backends = self.backends  # already merged with template
        return copy.deepcopy(backends.get(name))

    def get_config_paths(self) -> list[str]:
        """Return paths of all config source files (for mtime checks)."""
        paths = [_DEFAULT_CONFIG_PATH]
        if os.path.isfile(_USER_CONFIG_PATH):
            paths.append(_USER_CONFIG_PATH)
        return paths

    def _required(self, key: str):
        val = self._merged.get(key)
        if val in (None, ""):
            print(f"ds-cli: missing required config key: {key}", file=sys.stderr)
            sys.exit(1)
        return val
