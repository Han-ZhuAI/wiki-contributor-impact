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
        return _run_analyze(args.article, args.max_revisions)

    return 0


def _run_analyze(article: str, max_revisions: int) -> int:
    """Day-2 capability: fetch the revision history and report a summary.

    Metric computation is layered on top of this in later stages of the
    schedule; for now this proves the data pipeline works end-to-end.
    """
    from .api import MediaWikiClient, WikiAPIError

    client = MediaWikiClient()
    try:
        revisions = client.fetch_revisions(article, max_revisions=max_revisions)
    except WikiAPIError as exc:
        print(f"error: {exc}")
        return 1

    if not revisions:
        print(f"no revisions found for {article!r}")
        return 1

    editors = {r.user for r in revisions if r.user}
    print(f"[wikicontrib {__version__}] {article}")
    print(f"  revisions fetched : {len(revisions)}")
    print(f"  distinct editors  : {len(editors)}")
    print(f"  first edit        : {revisions[0].timestamp}")
    print(f"  latest edit       : {revisions[-1].timestamp}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
