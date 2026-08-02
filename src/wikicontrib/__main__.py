"""Command-line entry point for article-history analysis."""

from __future__ import annotations

import argparse

from . import __version__


def _positive_int(value: str) -> int:
    """Parse a strictly positive integer for revision-limit arguments."""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wikicontrib",
        description="Assess contributor impact on a Wikipedia article.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command")
    analyze = sub.add_parser("analyze", help="analyze a single article's edit history")
    analyze.add_argument("article", help="article title, e.g. \"Alan Turing\"")
    history_scope = analyze.add_mutually_exclusive_group()
    history_scope.add_argument(
        "--max-revisions",
        type=_positive_int,
        default=500,
        help=(
            "analyze only the earliest N revisions (default: 500); capped "
            "results are labelled as a historical slice"
        ),
    )
    history_scope.add_argument(
        "--all-revisions",
        action="store_true",
        help=(
            "fetch the complete history so persistence is measured against "
            "the current page (can be slow for heavily edited articles)"
        ),
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
            None if args.all_revisions else args.max_revisions,
            refresh=args.refresh,
            with_diff=args.with_diff,
        )

    return 0


def _run_analyze(
    article: str,
    max_revisions: int | None,
    refresh: bool = False,
    with_diff: bool = False,
) -> int:
    """Fetch the article + talk history and report available impact metrics."""
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
    print(f"  latest fetched edit: {revisions[-1].timestamp}")
    if max_revisions is None:
        print("  history scope      : complete")
    else:
        print(f"  history scope      : earliest {len(revisions)} revisions")
        if len(revisions) >= max_revisions:
            print(
                "  warning            : revision cap reached; persistence and "
                "rankings describe this historical slice, not the current article"
            )
    if history.has_talk:
        print(f"  talk page         : {history.talk_title}")
        print(f"  talk revisions    : {len(history.talk_revisions)}")
        print(f"  talk participants : {len(history.talk_participants)}")
    else:
        print("  talk page         : (none found)")

    if with_diff:
        _print_volume_leaderboard(revisions)
        _print_persistence_leaderboard(revisions)
        if history.has_talk:
            _print_discussion_leaderboard(history.talk_revisions, revisions)
    return 0


def _print_volume_leaderboard(revisions, limit: int = 15) -> None:
    """Print the per-contributor volume leaderboard for the article."""
    from .metrics import aggregate_history

    report = aggregate_history(revisions)
    if not report.contributors:
        print("\n  no textual changes detected")
        return

    ranked = report.ranked(by="net_words")
    shown = ranked[:limit]
    print(
        f"\n  contributor volume — top {len(shown)} of "
        f"{len(ranked)} by net words:"
    )
    header = (
        f"    {'contributor':<22}{'edits':>6}{'+words':>8}"
        f"{'net':>8}{'share':>7}{'maint%':>8}"
    )
    print(header)
    print("    " + "-" * (len(header) - 4))
    for c in shown:
        print(
            f"    {c.user[:21]:<22}{c.edits:>6}{c.words_added:>8}"
            f"{c.net_words:>+8}"
            f"{report.share_of_added(c.user) * 100:>6.1f}%"
            f"{c.maintenance_ratio * 100:>7.0f}%"
        )


def _print_persistence_leaderboard(revisions, limit: int = 15) -> None:
    """Print the per-contributor text-survival leaderboard."""
    from .persistence import track_persistence

    report = track_persistence(revisions)
    if not report.final_word_count:
        return

    ranked = [c for c in report.ranked() if c.words_introduced][:limit]
    print(
        f"\n  content persistence — top {len(ranked)} by surviving words "
        f"(final article: {report.final_word_count} words):"
    )
    header = (
        f"    {'contributor':<22}{'introduced':>11}{'surviving':>10}"
        f"{'survival':>9}{'share':>7}"
    )
    print(header)
    print("    " + "-" * (len(header) - 4))
    for c in ranked:
        print(
            f"    {c.user[:21]:<22}{c.words_introduced:>11}{c.words_surviving:>10}"
            f"{c.survival_rate * 100:>8.0f}%"
            f"{report.share_of_surviving(c.user) * 100:>6.1f}%"
        )


def _print_discussion_leaderboard(
    talk_revisions, article_revisions, limit: int = 15
) -> None:
    """Print Talk-page participation and reply-graph centrality."""
    from .discussion import analyze_discussion

    report = analyze_discussion(talk_revisions, article_revisions)
    if not report.contributors:
        print("\n  discussion impact  : no signed Talk-page posts parsed")
        return

    ranked = report.ranked()[:limit]
    print(
        f"\n  discussion impact — top {len(ranked)} of "
        f"{len(report.contributors)} by reply centrality "
        f"({len(report.threads)} threads, {report.total_posts} posts):"
    )
    header = (
        f"    {'contributor':<22}{'posts':>6}{'starts':>7}"
        f"{'sent':>6}{'recv':>6}{'rank':>8}{'linked':>8}"
    )
    print(header)
    print("    " + "-" * (len(header) - 4))
    for contributor in ranked:
        print(
            f"    {contributor.user[:21]:<22}{contributor.posts:>6}"
            f"{contributor.threads_started:>7}{contributor.replies_made:>6}"
            f"{contributor.replies_received:>6}"
            f"{contributor.pagerank * 100:>7.1f}%"
            f"{contributor.follow_up_edits:>8}"
        )
    if report.parse_rate < 1.0:
        print(
            f"    signature coverage: {report.total_posts}/{report.signatures_seen} "
            "timestamp-shaped signatures attributed"
        )
    print(
        "    linked = same-user article edits within 14 days after a post "
        "(temporal proxy, not proof of causation)"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
