"""Backend resolution and command building for ds-cli.

Given a resolved backend configuration (merged from backend_template + specific
backend overrides in YAML), this module provides:

  - set_backend_env(backend, ...): Set environment variables for Claude
  - build_claude_args(backend, ...): Build claude CLI argument list

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
import sys
from typing import Optional


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

    Iterates the backend's 'env' mapping, substitutes placeholders,
    and sets each key=value in os.environ.
    """
    ctx = {
        "default_model": default_model,
        "pro_model": pro_model,
        "model": model,
        "home": os.path.expanduser("~"),
    }

    env_map = backend.get("env", {})
    for key, val in env_map.items():
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
    session_id: Optional[str] = None,
    model: Optional[str] = None,
    default_model: Optional[str] = None,
    pro_model: Optional[str] = None,
    resume: bool = False,
) -> list[str]:
    """Build the claude CLI argument list from a resolved backend config.

    Returns a list like ["claude", "-p", prompt, "--dangerously-skip-permissions", ...]

    When `resume` is True, the session identity flags come from
    `continue_id_flags` (`--resume {session_id}`) instead of `session_id_flags`
    (`--session-id {session_id}`), so the new turn is appended to an existing
    claude conversation in print mode rather than opening a fresh session.
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
        id_flags_key = "continue_id_flags" if resume else "session_id_flags"
        for flag in backend.get(id_flags_key, []):
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
    default_model: Optional[str] = None,
    pro_model: Optional[str] = None,
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


def ensure_backend_token_ready(backend_name: str, backend: dict, user_config_path: str):
    """Fail fast when the selected backend still uses a placeholder token."""
    token = backend.get("env", {}).get("ANTHROPIC_AUTH_TOKEN")
    if isinstance(token, str) and token.startswith("<"):
        print(
            f"ds-cli: backend '{backend_name}' still uses placeholder token {token}. "
            f"Edit {user_config_path} and set a real ANTHROPIC_AUTH_TOKEN.",
            file=sys.stderr,
        )
        sys.exit(2)
