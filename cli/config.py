"""YAML configuration loading and merging for handoff.

Configuration flow:
  1. If ~/.handoff/config.yaml is missing, run the interactive installer
  2. Load ~/.handoff/config.yaml as the single source of truth
  3. If the user config includes the bundled default_config.yaml (via `include:`),
     the defaults are deep-merged first, then the user config overrides them.

Backend resolution:
  - Resolved backend = type_defaults[<type>] + the backend's own fields
  - type_defaults carry the type-level launch contract (command, flags, env, PTY);
    each backend supplies its instance fields (endpoint, token, model)
  - The bundled defaults ship usable backends; the user config only adds a token
"""

from __future__ import annotations

import os
import re
import sys
import copy
from typing import Optional

try:
    import yaml
except ImportError:
    print(
        "handoff: PyYAML is required. Install it with: pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(1)

_DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "default_config.yaml")
_DEFAULT_USER_CONFIG = """# handoff user configuration — overrides only.
#
# Bundled defaults (three backends: deepseek / opus / codex, plus the
# type-level launch contract) are layered underneath this file automatically.
# To see everything you can override, read cli/default_config.yaml in the
# handoff repo.
#
# The bundled `opus` (local claude login) and `codex` (local codex login)
# backends are zero-config. Only `deepseek` needs a token. Two ways to supply it:
#
#   1. Set it here:
#        backends:
#          deepseek:
#            env:
#              ANTHROPIC_AUTH_TOKEN: "sk-..."
#
#   2. Or export DEEPSEEK_API_KEY in your shell and leave this file empty —
#      the bundled config reads ANTHROPIC_AUTH_TOKEN from ${DEEPSEEK_API_KEY}.

# Uncomment and fill in to set the deepseek token in this file:
# backends:
#   deepseek:
#     env:
#       ANTHROPIC_AUTH_TOKEN: "<YOUR_DEEPSEEK_TOKEN>"
"""


def user_config_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".handoff")


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
            print(f"handoff: config {path} must be a mapping", file=sys.stderr)
            sys.exit(1)
        return data
    except yaml.YAMLError as e:
        print(f"handoff: error parsing {path}: {e}", file=sys.stderr)
        sys.exit(1)


def write_default_user_config() -> bool:
    """Create the default user config if missing. Return True when written."""
    path = user_config_path()
    if os.path.isfile(path):
        return False

    try:
        content = _DEFAULT_USER_CONFIG
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return True
    except OSError as e:
        print(f"handoff: failed to create default user config at {path}: {e}", file=sys.stderr)
        sys.exit(1)


def _ensure_user_config_exists():
    if os.path.isfile(user_config_path()):
        return

    from .commands.init import run_init

    run_init()
    if not os.path.isfile(user_config_path()):
        print(f"handoff: initialization did not create {user_config_path()}", file=sys.stderr)
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


_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_env_vars(value):
    """Recursively expand ${ENV_VAR} references in config string values.

    Unset variables expand to the empty string (later caught by
    ensure_backend_token_ready when a real token is required).
    """
    if isinstance(value, str):
        return _ENV_VAR_RE.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_vars(v) for v in value]
    return value


# Top-level config keys removed in the multi-backend refactor. Reading them from
# an old user config is harmless — warn once and ignore rather than crash.
# default_model / pro_model are additionally kept as a fallback for legacy
# backends that don't carry their own model field.
_DEPRECATED_KEYS = ("fast_backend", "backend_template", "default_model", "pro_model")


def _resolve_include_path(include_val: str, including_file_dir: str) -> str:
    """Resolve an include path.

    Absolute paths are used as-is.
    Relative paths: first try relative to the including file's directory,
    then fall back to the package directory.
    """
    if os.path.isabs(include_val):
        return include_val

    # Try relative to the including file's directory first
    candidate = os.path.join(including_file_dir, include_val)
    if os.path.isfile(candidate):
        return candidate

    # Fall back to the package directory
    candidate = os.path.join(os.path.dirname(__file__), include_val)
    if os.path.isfile(candidate):
        return candidate

    return candidate


def _load_with_includes(path: str, _seen: Optional[set] = None) -> dict:
    """Load a YAML file, recursively resolving `include:` directives.

    `include` can be a string (single path) or list of paths.
    Included files are deep-merged first (in order), then the current
    file's own keys are deep-merged on top so they override includes.

    Absolute include paths are used as-is.  Relative paths are resolved
    against the including file's directory first, then the package dir.

    _seen tracks already-visited paths to guard against cycles.
    """
    if _seen is None:
        _seen = set()

    real = os.path.realpath(path)
    if real in _seen:
        return {}
    _seen.add(real)

    data = _load_yaml(path)
    includes = data.pop("include", None)
    if isinstance(includes, str):
        includes = [includes]
    elif includes is None:
        includes = []

    including_dir = os.path.dirname(path)

    # Deep-merge all includes first
    merged = {}
    for inc in includes:
        inc_path = _resolve_include_path(inc, including_dir)
        if os.path.isfile(inc_path):
            inc_data = _load_with_includes(inc_path, _seen)
            merged = _deep_merge(merged, inc_data)

    # Then deep-merge current file's own keys on top
    merged = _deep_merge(merged, data)

    return merged


class Config:
    """Resolved handoff configuration."""

    def __init__(self):
        _ensure_user_config_exists()
        # Bundled defaults are always the base layer; the user config
        # (with any of its own includes) is merged on top. The user config
        # never needs to reference the source tree.
        defaults = _load_yaml(_DEFAULT_CONFIG_PATH)
        user = _load_with_includes(user_config_path())
        self._legacy_default_model = ""
        self._legacy_pro_model = ""
        self._warn_deprecated(user)
        self._merged = _deep_merge(defaults, user)
        self._validate()

    def _warn_deprecated(self, user: dict):
        """Warn about (and drop) top-level keys removed in the multi-backend refactor.

        Legacy default_model / pro_model are remembered and used as a fallback
        for user-defined backends that don't carry their own model field, so an
        old config keeps working with one warning instead of a silent break.
        """
        self._legacy_default_model = user.get("default_model") or ""
        self._legacy_pro_model = user.get("pro_model") or ""
        for key in _DEPRECATED_KEYS:
            if key in user:
                print(
                    f"handoff: config key '{key}' is deprecated and was ignored "
                    f"(backends now carry their own model/pro_model; "
                    f"use --backend to pick a backend)",
                    file=sys.stderr,
                )
                user.pop(key, None)

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
    def system_prompt(self) -> str:
        return self._merged.get("system_prompt", "")

    @property
    def type_defaults(self) -> dict:
        return copy.deepcopy(self._merged.get("type_defaults", {}))

    @property
    def backends(self) -> dict:
        """Return the resolved backends dict.

        Resolution per backend: type_defaults[<type>] -> backend's own fields
        (deep merge; lists replaced wholesale). String values get ${ENV_VAR}
        interpolation. Every resolved backend carries a `type` key
        (defaults to "claude" when omitted).
        """
        raw = self._merged.get("backends", {})
        if not isinstance(raw, dict):
            print("handoff: config key 'backends' must be a mapping", file=sys.stderr)
            sys.exit(1)
        type_defaults = self._merged.get("type_defaults", {}) or {}
        result = {}
        for name, overrides in raw.items():
            if not isinstance(overrides, dict):
                print(f"handoff: backend '{name}' must be a mapping", file=sys.stderr)
                sys.exit(1)
            btype = overrides.get("type", "claude")
            base = type_defaults.get(btype)
            if not isinstance(base, dict):
                base = {}
            merged = _deep_merge(base, overrides)
            merged["type"] = btype
            # legacy fallback: pre-refactor configs carried the model at top level
            if not merged.get("model") and self._legacy_default_model:
                merged["model"] = self._legacy_default_model
            if not merged.get("pro_model") and self._legacy_pro_model:
                merged["pro_model"] = self._legacy_pro_model
            result[name] = _expand_env_vars(merged)
        return result

    def get_backend(self, name: str) -> Optional[dict]:
        """Resolve a named backend (returns deep-copied merged dict or None)."""
        backends = self.backends  # already merged with type defaults
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
            print(f"handoff: missing required config key: {key}", file=sys.stderr)
            sys.exit(1)
        return val

    def _validate(self):
        backends = self._merged.get("backends", {})
        if not isinstance(backends, dict) or not backends:
            print(
                "handoff: no backends configured (bundled defaults missing or overridden away)",
                file=sys.stderr,
            )
            sys.exit(1)

        type_defaults = self._merged.get("type_defaults", {})
        if not isinstance(type_defaults, dict) or not type_defaults:
            print("handoff: missing required config mapping: type_defaults", file=sys.stderr)
            sys.exit(1)

        backend_name = self._required("default_backend")
        if backend_name not in backends:
            print(
                f"handoff: config key 'default_backend' points to unknown backend '{backend_name}'",
                file=sys.stderr,
            )
            sys.exit(1)

        for name, overrides in backends.items():
            if not isinstance(overrides, dict):
                continue  # reported when resolving
            btype = overrides.get("type", "claude")
            if btype not in type_defaults:
                print(
                    f"handoff: backend '{name}' has unknown type '{btype}' "
                    f"(known: {', '.join(sorted(type_defaults.keys()))})",
                    file=sys.stderr,
                )
                sys.exit(1)
