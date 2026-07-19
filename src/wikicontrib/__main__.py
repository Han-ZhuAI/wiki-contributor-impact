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
    analyze.add_argument(
        "--refresh",
        action="store_true",
        help="ignore cached data and re-fetch from the API",
    )
    analyze.add_argument(
        "--with-diff",
        action="store_true",
        help=(
            "fetch full revision text and diff each edit "
            "(slower: downloads every revision's wikitext)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "analyze":
        return _run_analyze(
            args.article,
            args.max_revisions,
            refresh=args.refresh,
            with_diff=args.with_diff,
        )

    return 0


def _run_analyze(
    article: str,
    max_revisions: int,
    refresh: bool = False,
    with_diff: bool = False,
) -> int:
    """Fetch the article + talk history and report a summary.

    Metric computation is layered on top of this in later stages of the
    schedule; for now this proves the data pipeline works end-to-end.
    """
    from .api import WikiAPIError
    from .store import RevisionStore

    store = RevisionStore()
    try:
        history = store.get_page_history(
            article,
            max_revisions=max_revisions,
            refresh=refresh,
            include_content=with_diff,
        )
    except WikiAPIError as exc:
        print(f"error: {exc}")
        return 1

    if not history.revisions:
        print(f"no revisions found for {article!r}")
        return 1

    revisions = history.revisions
    print(f"[wikicontrib {__version__}] {history.title}")
    print(f"  revisions fetched : {len(revisions)}")
    print(f"  distinct editors  : {len(history.editors)}")
    print(f"  first edit        : {revisions[0].timestamp}")
    print(f"  latest edit       : {revisions[-1].timestamp}")
    if history.has_talk:
        print(f"  talk page         : {history.talk_title}")
        print(f"  talk revisions    : {len(history.talk_revisions)}")
        print(f"  talk participants : {len(history.talk_participants)}")
    else:
        print("  talk page         : (none found)")

    if with_diff:
        _print_diff_summary(revisions)
    return 0


def _print_diff_summary(revisions, limit: int = 15) -> None:
    """Print per-edit diff statistics.

    Aggregation into per-contributor metrics arrives with the volume metrics;
    this listing exists to show the diff engine running on real history.
    """
    from .diff import diff_history

    diffs = [d for d in diff_history(revisions) if not d.is_empty]
    if not diffs:
        print("\n  no textual changes detected")
        return

    print(f"\n  per-edit diff (first {min(limit, len(diffs))} of {len(diffs)}):")
    header = f"    {'date':<11}{'editor':<20}{'+words':>7}{'-words':>7}{'net':>7}{'churn':>7}"
    print(header)
    print("    " + "-" * (len(header) - 4))
    for d in diffs[:limit]:
        editor = (d.user or "(hidden)")[:19]
        print(
            f"    {d.timestamp[:10]:<11}{editor:<20}"
            f"{d.words_added:>7}{d.words_removed:>7}"
            f"{d.net_words:>+7}{d.churn:>7.2f}"
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
