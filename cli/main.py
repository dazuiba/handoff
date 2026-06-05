"""ds-cli main dispatch — import this from the thin entry point.

Handles subcommand routing, auto-sync, and usage output.
"""

import sys

from .config import Config
from .commands.run import cmd_run, cmd_run_demo
from .commands.start import cmd_start
from .commands.result import cmd_result
from .commands.list import cmd_list
from .commands.tail import cmd_tail
from .commands.recall import cmd_recall
from .commands.go import cmd_go
from .commands.sync_agents import cmd_sync_agents, check_auto_sync


def usage():
    print(
        """usage:
  ds-cli run        [--cwd <dir>] <input-file|-> [--backend <name>] [--pro]
  ds-cli run-demo   [--backend <name>] [--pro] <prompt...>
  ds-cli start      [--cwd <dir>] <input-file> [--backend <name>] [--pro] [--fg] [-o <jsonl-file>]
  ds-cli result     <run-id|seq|jsonl>
  ds-cli list       [--uuid] [--cwd]
  ds-cli tail       [<run-id|seq>]
  ds-cli go         [<run-id|seq>] [--backend <name>]
  ds-cli recall     [<run-id|seq>] --cmd <command>
  ds-cli sync-agents [--force]

Run ids: ds-<SEQ_CODE>-<MMDD>  (seq_code: daily counter, 01..99, A0..ZZ)
--cwd defaults to the current directory of the calling process.
--backend selects the backend; default: opencode-proxy.
--pro uses the pro model profile on the selected backend."""
    )


_COMMANDS = {
    "run": cmd_run,
    "run-demo": cmd_run_demo,
    "start": cmd_start,
    "result": cmd_result,
    "list": cmd_list,
    "tail": cmd_tail,
    "go": cmd_go,
    "recall": cmd_recall,
    "sync-agents": cmd_sync_agents,
}


def main():
    config = Config()

    if len(sys.argv) < 2:
        usage()
        sys.exit(2)

    subcmd = sys.argv[1]
    rest = sys.argv[2:]

    # Prevent auto-sync during sync-agents itself
    if subcmd != "sync-agents":
        try:
            check_auto_sync(config)
        except Exception as e:
            print(f"ds-cli: auto-sync warning: {e}", file=sys.stderr)

    if subcmd == "run-demo":
        cmd_run_demo(rest, config)
    elif subcmd == "run":
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
    elif subcmd == "sync-agents":
        cmd_sync_agents(rest, config)
    elif subcmd in ("-h", "--help"):
        usage()
    else:
        print(
            f"ds-cli: unknown subcommand '{subcmd}' — expected: "
            f"run, run-demo, start, result, list, tail, go, recall, sync-agents",
            file=sys.stderr,
        )
        usage()
        sys.exit(2)
