"""handoff main dispatch — import this from the entry point."""

import os
import sys

from . import __version__


def usage(config=None):
    print(
        """usage:
  handoff --help
  handoff init      [-y|--yes]
  handoff list      [--uuid] [--cwd]
  handoff run       [--backend <name>] [--cwd <dir>] [--pro] (<input-file|-> | --text <prompt...>)
  handoff resume    [<run-id|seq>] [--pro] [--cwd <dir>] [(<input-file|-> | --text <prompt...>)]
  handoff tail [<run-id|seq>]

  handoff list             — browse and inspect your past sessions
  handoff run --text hi    — quick smoke-test / debug your config.yaml
  handoff resume <seq>     — reopen a past conversation (interactive)
  handoff resume <seq> -   — dispatch a follow-up task to that conversation (heredoc/--text)
  handoff tail             — live-tail a run's stream

Run ids: hd-<MMDD>-<SEQ_CODE>  (seq_code: daily counter, 01..99, A0..ZZ)
--cwd defaults to the current directory of the calling process.
--backend picks a backend (bundled: deepseek, opus, codex; default: default_backend).
--pro uses the backend's pro_model. A resume stays on its original backend."""
    )


def main():
    # Run legacy migration early — before any config check — so that an
    # existing legacy dir is renamed to ~/.handoff before we look for config.
    from .core import _migrate_legacy_state
    _migrate_legacy_state()

    if len(sys.argv) < 2:
        config_path = os.path.join(os.path.expanduser("~"), ".handoff", "config.yaml")
        if not os.path.isfile(config_path):
            from .commands.init import run_init

            run_init()
            return
        usage()
        sys.exit(2)

    subcmd = sys.argv[1]
    rest = sys.argv[2:]

    if subcmd in ("-h", "--help"):
        usage()
        return

    if subcmd == "--version":
        print(f"handoff {__version__}")
        return

    if subcmd == "init":
        from .commands.init import cmd_init

        cmd_init(rest)
        return

    known = {"run", "list", "resume", "tail"}
    if subcmd not in known:
        print(
            f"handoff: unknown subcommand '{subcmd}' — expected: "
            f"init, list, run, resume, tail",
            file=sys.stderr,
        )
        usage()
        sys.exit(2)

    from .config import Config
    from .commands.run import cmd_run
    from .commands.list import cmd_list
    from .commands.resume import cmd_resume
    from .commands.tail import cmd_tail

    config = Config()

    if subcmd == "run":
        cmd_run(rest, config)
    elif subcmd == "list":
        cmd_list(rest, config)
    elif subcmd == "resume":
        cmd_resume(rest, config)
    elif subcmd == "tail":
        cmd_tail(rest, config)
