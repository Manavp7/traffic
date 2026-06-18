"""Traffic-OS command-line entry point.

Subcommands are added as phases land (seed, simulate, history, train, serve, demo).
"""

from __future__ import annotations

import argparse

from traffic_os import __version__
from traffic_os.common.logging import get_logger

log = get_logger("cli")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="traffic-os", description="National Traffic Intelligence OS"
    )
    parser.add_argument("--version", action="version", version=f"traffic-os {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("info", help="Print environment/storage info")

    args = parser.parse_args(argv)

    if args.command == "info":
        from traffic_os.storage import get_storage

        st = get_storage()
        log.info("Traffic-OS %s | mode=%s", __version__, st.settings.mode)
        log.info("Graph backend: %s | stats=%s", st.graph.__class__.__name__, st.graph.stats())
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
