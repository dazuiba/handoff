"""handoff CLI package."""

try:
    from importlib.metadata import version as _ver

    __version__ = _ver("handoff-cli")
except Exception:
    __version__ = "0.0.0"
