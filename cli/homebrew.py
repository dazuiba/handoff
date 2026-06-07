"""Homebrew installation detection for ds-cli."""

import os
import sys


def is_homebrew_install() -> bool:
    """Detect if ds-cli is installed via Homebrew.

    Checks whether the real path of the current script or any parent
    directory is under Homebrew's Cellar, indicating a 'brew install'
    rather than a manual git checkout.
    """
    # Resolve symlinks to find the real physical path
    script_path = os.path.realpath(sys.argv[0])

    # Known Homebrew Cellar prefixes
    homebrew_prefixes = (
        os.path.join(os.sep, "usr", "local", "Cellar"),
        os.path.join(os.sep, "opt", "homebrew", "Cellar"),
    )

    # Also check HOMEBREW_CELLAR env var if set
    env_cellar = os.environ.get("HOMEBREW_CELLAR")
    if env_cellar:
        homebrew_prefixes = homebrew_prefixes + (env_cellar,)

    return script_path.startswith(homebrew_prefixes)
