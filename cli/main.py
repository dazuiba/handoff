"""ds-cli main dispatch — import this from the thin entry point."""

import os
import sys

from . import __version__


def usage(config=None):
    print(
        """usage:
  ds-cli --help
  ds-cli install    [-y|--yes]
  ds-cli update
  ds-cli list       [--uuid] [--cwd]
  ds-cli run        [--cwd <dir>] [--fast] [--pro] [--from codex] (<input-file|-> | --text <prompt...>)
  ds-cli resume     [<run-id|seq>] [--fast] [--pro] [--from codex] [--cwd <dir>] [(<input-file|-> | --text <prompt...>)]
  ds-cli tail [<run-id|seq>]

  ds-cli list             — browse and inspect your past sessions
  ds-cli run --text hi    — quick smoke-test / debug your config.yml
  ds-cli resume <seq>     — reopen a past conversation in claude (interactive)
  ds-cli resume <seq> -   — dispatch a follow-up task to that conversation (heredoc/--text)
  ds-cli tail             — live-tail a run's stream

Run ids: ds-<MMDD>-<SEQ_CODE>  (seq_code: daily counter, 01..99, A0..ZZ)
--cwd defaults to the current directory of the calling process.
--fast uses fast_backend from ~/.ds-cli/config.yaml.
--pro uses the pro model profile on the selected backend.
--from codex prints only RESULT=<path> after completion, for Codex subagents."""
    )


def main():
    if len(sys.argv) < 2:
        config_path = os.path.join(os.path.expanduser("~"), ".ds-cli", "config.yaml")
        if not os.path.isfile(config_path):
            from .commands.install import run_install

            run_install()
            return
        usage()
        sys.exit(2)

    subcmd = sys.argv[1]
    rest = sys.argv[2:]

    if subcmd in ("-h", "--help"):
        usage()
        return

    if subcmd == "--version":
        print(f"ds-cli {__version__}")
        return

    if subcmd == "install":
        from .commands.install import cmd_install

        cmd_install(rest)
        return

    if subcmd == "update":
        from .commands.update import cmd_update

        cmd_update(rest)
        return

    known = {"run", "list", "resume", "tail"}
    if subcmd not in known:
        print(
            f"ds-cli: unknown subcommand '{subcmd}' — expected: "
            f"install, update, list, run, resume, tail",
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
