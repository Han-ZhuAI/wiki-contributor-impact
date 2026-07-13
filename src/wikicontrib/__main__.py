"""Command-line entry point.

Currently a scaffold: the ``analyze`` sub-command is stubbed and will be
implemented across the schedule (see SCHEDULE.md, Day 12).
"""

from __future__ import annotations

import argparse

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wikicontrib",
        description="Assess contributor impact on a Wikipedia article.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command")
    analyze = sub.add_parser("analyze", help="analyze a single article's edit history")
    analyze.add_argument("article", help="article title, e.g. \"Alan Turing\"")
    analyze.add_argument(
        "--max-revisions",
        type=int,
        default=500,
        help="cap on the number of revisions to fetch (default: 500)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "analyze":
        # Implemented incrementally over the schedule.
        print(f"[wikicontrib {__version__}] analyze '{args.article}' "
              f"(max {args.max_revisions} revisions) — not yet implemented")
        return 0

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
