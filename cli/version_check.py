"""Asynchronous PyPI version check — non-blocking, once per 24h."""

import json
import os
import re
import sys
import threading
import time
import urllib.request

from . import __version__

_STATE_FILE = os.path.join(
    os.path.expanduser("~"), ".handoff", "version_check_state.json"
)
_PYPI_URL = "https://pypi.org/pypi/handoff-cli/json"
# Minimum interval between checks (seconds).  Avoids hammering PyPI on
# rapid-fire invocations (e.g. during a CI loop or batch dispatch).
_CHECK_INTERVAL = 86400  # 24 hours


def _load_state():
    try:
        with open(_STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_check": 0}


def _save_state(ts):
    try:
        os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
        with open(_STATE_FILE, "w") as f:
            json.dump({"last_check": ts}, f)
    except OSError:
        pass


def _fetch_latest_version():
    req = urllib.request.Request(_PYPI_URL, method="GET")
    with urllib.request.urlopen(req, timeout=3) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["info"]["version"]


def _parse_version(v: str):
    """Extract major.minor.patch from a semver string.

    Handles pre-release suffixes (0.3.8a1 → (0, 3, 8)) and partial
    versions gracefully.
    """
    m = re.match(r"(\d+)\.(\d+)\.(\d+)", v)
    if not m:
        return (0, 0, 0)
    return tuple(int(g) for g in m.groups())


def _check():
    """Background thread entry — fetch latest version, print if newer."""
    try:
        latest = _fetch_latest_version()
        current = __version__
        if _parse_version(latest) > _parse_version(current):
            print(
                f"→ New version available: {latest} (you have {current}). "
                f"Run `uv tool upgrade handoff-cli`",
                file=sys.stderr,
            )
    except Exception:
        pass  # network error, PyPI unreachable — stay quiet


def maybe_check():
    """Non-blocking version check, at most once per 24h.

    Lightweight — spawns a daemon thread and returns immediately.
    Call once early in main() before subcommand dispatch.
    """
    now = time.time()
    state = _load_state()
    if now - state.get("last_check", 0) < _CHECK_INTERVAL:
        return
    _save_state(now)

    t = threading.Thread(target=_check, daemon=True)
    t.start()
