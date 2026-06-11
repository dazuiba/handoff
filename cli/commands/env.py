"""handoff env command — print configuration paths for humans and scripts."""

from __future__ import annotations

import os
import sys


def cmd_env(_args):
    """handoff env — print key configuration paths (no Config init needed)."""
    if _args and _args[0] in ("-h", "--help"):
        print("usage: handoff env")
        print("  Print key configuration paths for use by humans and scripts.")
        return

    from ..config import user_config_dir, user_config_path

    # backend_types.yaml lives alongside this file in the package
    backend_types_path = os.path.join(os.path.dirname(__file__), "..", "backend_types.yaml")
    backend_types_path = os.path.abspath(backend_types_path)

    config = user_config_path()
    tasks = os.path.join(user_config_dir(), "tasks")
    runs = os.path.join(user_config_dir(), "runs")

    # Print paths unconditionally — env must work even with a broken config.
    print(f"config={config}")
    print(f"backend_types={backend_types_path}")
    print(f"tasks={tasks}          # prompt / .out / .result files")
    print(f"runs={runs}            # raw jsonl streams")
