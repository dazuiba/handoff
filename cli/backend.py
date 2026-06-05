"""Backend resolution and command building for ds-cli.

Given a resolved backend configuration (merged from backend_template + specific
backend overrides in YAML), this module provides:

  - set_backend_env(backend, ...): Set environment variables for Claude
  - build_claude_args(backend, ...): Build claude CLI argument list
  - build_resume_args(backend, ...): Build claude resume argument list

Placeholder substitution:
  {prompt}         — the prompt text
  {session_id}     — session UUID
  {system_prompt}  — configured system prompt
  {model}          — resolved model name (default_model or pro_model)
  {default_model}  — configured default_model
  {pro_model}      — configured pro_model
  {home}           — $HOME
"""

from __future__ import annotations

import os


def _substitute(text: str, ctx: dict) -> str:
    """Replace {placeholders} in a string using ctx dict."""
    return text.format(**ctx)


def _resolve_env_val(val, ctx: dict):
    """Resolve a config value, handling strings with placeholders."""
    if isinstance(val, str):
        resolved = _substitute(val, ctx)
        return os.path.expanduser(resolved)
    return val


def set_backend_env(backend: dict, default_model: str, pro_model: str, model: str):
    """Set environment variables for the Claude backend.

    Sets ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN, CLAUDE_CONFIG_DIR,
    and model-related env vars from the resolved backend dict.
    """
    ctx = {
        "default_model": default_model,
        "pro_model": pro_model,
        "model": model,
        "home": os.path.expanduser("~"),
    }

    env_keys = [
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_MODEL",
        "CLAUDE_CONFIG_DIR",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "CLAUDE_CODE_SUBAGENT_MODEL",
    ]

    for key in env_keys:
        val = backend.get(key)
        if val is not None:
            resolved = _resolve_env_val(val, ctx)
            os.environ[key] = resolved

    # Handle CLAUDE_CONFIG_DIR defaults
    if "CLAUDE_CONFIG_DIR" not in os.environ or not os.environ["CLAUDE_CONFIG_DIR"]:
        os.environ["CLAUDE_CONFIG_DIR"] = os.environ.get(
            "CLAUDE_CONFIG_DIR",
            os.path.expanduser("~/.claude2"),
        )


def build_claude_args(
    backend: dict,
    prompt: str,
    session_id: str | None = None,
    model: str | None = None,
    default_model: str | None = None,
    pro_model: str | None = None,
) -> list[str]:
    """Build the claude CLI argument list from a resolved backend config.

    Returns a list like ["claude", "-p", prompt, "--dangerously-skip-permissions", ...]
    """
    ctx = {
        "prompt": prompt,
        "session_id": session_id or "",
        "system_prompt": backend.get("_system_prompt", ""),
        "model": model or backend.get("_resolved_model", ""),
        "default_model": default_model or "",
        "pro_model": pro_model or "",
        "home": os.path.expanduser("~"),
    }

    claude_cmd = _resolve_env_val(backend.get("claude_command", "claude"), ctx)
    args = [claude_cmd]

    flags = backend.get("session_flags", [])
    for flag in flags:
        resolved = _resolve_env_val(flag, ctx)
        if resolved:
            args.append(resolved)

    if session_id:
        session_id_flags = backend.get("session_id_flags", [])
        for flag in session_id_flags:
            resolved = _resolve_env_val(flag, ctx)
            if resolved:
                args.append(resolved)

    return args


def wrap_with_pty(backend: dict, args: list[str]) -> list[str]:
    """Prefix args with the configured PTY wrapper, if any."""
    pty = backend.get("pty", [])
    if not pty:
        return args
    ctx = {
        "home": os.path.expanduser("~"),
        "prompt": "",
        "session_id": "",
        "system_prompt": backend.get("_system_prompt", ""),
        "model": backend.get("_resolved_model", ""),
        "default_model": "",
        "pro_model": "",
    }
    return [_resolve_env_val(part, ctx) for part in pty] + args


def build_resume_args(
    backend: dict,
    session_id: str,
    default_model: str | None = None,
    pro_model: str | None = None,
) -> list[str]:
    """Build claude resume argument list (for 'go' command)."""
    ctx = {
        "prompt": "",
        "session_id": session_id or "",
        "system_prompt": backend.get("_system_prompt", ""),
        "model": backend.get("_resolved_model", ""),
        "default_model": default_model or "",
        "pro_model": pro_model or "",
        "home": os.path.expanduser("~"),
    }

    claude_cmd = _resolve_env_val(backend.get("claude_command", "claude"), ctx)
    args = [claude_cmd]

    flags = backend.get("resume_flags", [])
    for flag in flags:
        resolved = _resolve_env_val(flag, ctx)
        if resolved:
            args.append(resolved)

    return args


def resolve_backend_model(backend: dict, default_model: str, pro_model: str, is_pro: bool = False) -> str:
    """Return the model name for this backend.

    If the backend specifies its own model fields, use those;
    otherwise fall back to the configured default/pro model.
    """
    model_key = "pro_model" if is_pro else "default_model"
    model = backend.get(model_key)
    if not model:
        model = pro_model if is_pro else default_model

    # Substitution
    ctx = {"default_model": default_model, "pro_model": pro_model, "home": os.path.expanduser("~")}
    resolved = _resolve_env_val(model, ctx)
    return resolved
