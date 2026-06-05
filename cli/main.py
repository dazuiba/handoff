"""ds-cli main dispatch — import this from the thin entry point."""

import os
import sys

from . import __version__


def usage(config=None):
    print(
        """usage:
  ds-cli --help
  ds-cli --version
  ds-cli version
  ds-cli install
  ds-cli run        [--cwd <dir>] [--fast] [--pro] (<input-file|-> | --text <prompt...>)
  ds-cli start      [--cwd <dir>] <input-file> [--fast] [--pro] [--fg] [-o <jsonl-file>]
  ds-cli result     <run-id|seq|jsonl>
  ds-cli list       [--uuid] [--cwd]
  ds-cli tail       [<run-id|seq>]
  ds-cli go         [<run-id|seq>]
  ds-cli recall     [<run-id|seq>] --cmd <command>

Run ids: ds-<SEQ_CODE>-<MMDD>  (seq_code: daily counter, 01..99, A0..ZZ)
--cwd defaults to the current directory of the calling process.
--fast uses fast_backend from ~/.ds-cli/config.yaml.
--pro uses the pro model profile on the selected backend."""
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

    if subcmd in ("--version", "version"):
        print(f"ds-cli {__version__}")
        return

    if subcmd in ("-h", "--help"):
        usage()
        return

    if subcmd == "install":
        from .commands.install import cmd_install

        cmd_install(rest)
        return

    known = {"run", "start", "result", "list", "tail", "go", "recall"}
    if subcmd not in known:
        print(
            f"ds-cli: unknown subcommand '{subcmd}' — expected: "
            f"install, run, start, result, list, tail, go, recall, version",
            file=sys.stderr,
        )
        usage()
        sys.exit(2)

    from .config import Config
    from .commands.run import cmd_run
    from .commands.start import cmd_start
    from .commands.result import cmd_result
    from .commands.list import cmd_list
    from .commands.tail import cmd_tail
    from .commands.recall import cmd_recall
    from .commands.go import cmd_go

    config = Config()

    if subcmd == "run":
        cmd_run(rest, config)
    elif subcmd == "start":
        cmd_start(rest, config)
    elif subcmd == "result":
        cmd_result(rest, config)
    elif subcmd == "list":
        cmd_list(rest, config)
    elif subcmd == "tail":
        cmd_tail(rest, config)
    elif subcmd == "go":
        cmd_go(rest, config)
    elif subcmd == "recall":
        cmd_recall(rest, config)
