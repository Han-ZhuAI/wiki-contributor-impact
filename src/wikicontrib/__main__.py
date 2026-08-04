"""Command-line entry point for article-history analysis."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from math import isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile

from . import __version__


def _positive_int(value: str) -> int:
    """Parse a strictly positive integer for revision-limit arguments."""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _non_negative_float(value: str) -> float:
    """Parse a finite non-negative score weight."""
    parsed = float(value)
    if not isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("must be a finite non-negative number")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wikicontrib",
        description="Assess contributor impact on a Wikipedia article.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    sub = parser.add_subparsers(dest="command")
    analyze = sub.add_parser("analyze", help="analyze a single article's edit history")
    analyze.add_argument("article", help='article title, e.g. "Alan Turing"')
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
    analyze.add_argument(
        "--output-json",
        "--json",
        type=Path,
        metavar="PATH",
        help=(
            "write the complete ranked analysis to PATH; this automatically "
            "enables revision-text analysis"
        ),
    )
    analyze.add_argument(
        "--top",
        type=_positive_int,
        default=15,
        help="number of contributors to show in each terminal leaderboard",
    )
    for dimension in ("volume", "additive", "persistence", "discussion"):
        analyze.add_argument(
            f"--weight-{dimension}",
            type=_non_negative_float,
            default=0.25,
            metavar="N",
            help=f"non-negative {dimension} weight (default: 0.25)",
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "analyze":
        from .scoring import ScoreWeights

        try:
            weights = ScoreWeights(
                volume=args.weight_volume,
                additive=args.weight_additive,
                persistence=args.weight_persistence,
                discussion=args.weight_discussion,
            )
        except ValueError as exc:
            parser.error(str(exc))
        return _run_analyze(
            args.article,
            None if args.all_revisions else args.max_revisions,
            refresh=args.refresh,
            with_diff=args.with_diff,
            weights=weights,
            output_json=args.output_json,
            limit=args.top,
        )

    return 0


def _run_analyze(
    article: str,
    max_revisions: int | None,
    refresh: bool = False,
    with_diff: bool = False,
    weights=None,
    output_json: Path | None = None,
    limit: int = 15,
) -> int:
    """Fetch the article + talk history and report available impact metrics."""
    from .api import WikiAPIError
    from .store import RevisionStore

    include_content = with_diff or output_json is not None
    store = RevisionStore()
    try:
        history = store.get_page_history(
            article,
            max_revisions=max_revisions,
            refresh=refresh,
            include_content=include_content,
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

    if include_content:
        from .discussion import analyze_discussion
        from .metrics import aggregate_history
        from .persistence import track_persistence
        from .profile import assemble_profiles
        from .scoring import ScoreWeights, score_profiles

        volume = aggregate_history(revisions)
        persistence = track_persistence(revisions)
        discussion = analyze_discussion(
            history.talk_revisions if history.has_talk else [], revisions
        )
        profiles = assemble_profiles(volume, persistence, discussion)
        impact = score_profiles(profiles, weights or ScoreWeights())

        _print_volume_report(volume, limit)
        _print_persistence_report(persistence, limit)
        if history.has_talk:
            _print_discussion_report(discussion, limit)
        _print_impact_leaderboard(impact, limit)

        if output_json is not None:
            try:
                _write_json_report(
                    output_json,
                    history,
                    max_revisions,
                    profiles,
                    impact,
                )
            except OSError as exc:
                print(f"error: could not write JSON report: {exc}")
                return 1
            print(f"\n  JSON report       : {output_json}")
    return 0


def _print_volume_leaderboard(revisions, limit: int = 15) -> None:
    """Print the per-contributor volume leaderboard for the article."""
    from .metrics import aggregate_history

    _print_volume_report(aggregate_history(revisions), limit)


def _print_volume_report(report, limit: int = 15) -> None:
    """Print a precomputed per-contributor volume report."""
    if not report.contributors:
        print("\n  no textual changes detected")
        return

    ranked = report.ranked(by="net_words")
    shown = ranked[:limit]
    print(f"\n  contributor volume — top {len(shown)} of {len(ranked)} by net words:")
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

    _print_persistence_report(track_persistence(revisions), limit)


def _print_persistence_report(report, limit: int = 15) -> None:
    """Print a precomputed token-survival report."""
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

    _print_discussion_report(
        analyze_discussion(talk_revisions, article_revisions), limit
    )


def _print_discussion_report(report, limit: int = 15) -> None:
    """Print a precomputed Talk-page discussion report."""
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


def _print_impact_leaderboard(report, limit: int = 15) -> None:
    """Print composite score and all four component axes."""
    ranked = report.ranked[:limit]
    if not ranked:
        print("\n  composite impact   : no contributors scored")
        return

    weights = report.weights.normalised
    weight_text = ", ".join(
        f"{dimension}={weight:.2f}" for dimension, weight in weights.items()
    )
    print(
        f"\n  composite impact — top {len(ranked)} of "
        f"{len(report.contributors)} ({weight_text}):"
    )
    header = (
        f"    {'#':>3} {'contributor':<22}{'score':>8}{'volume':>9}"
        f"{'additive':>10}{'persist':>9}{'discuss':>9}{'scope':>14}"
    )
    print(header)
    print("    " + "-" * (len(header) - 4))
    for result in ranked:
        vector = result.feature_vector
        print(
            f"    {result.rank:>3} {result.user[:21]:<22}"
            f"{result.score:>8.3f}{vector['volume']:>9.3f}"
            f"{vector['additive']:>10.3f}{vector['persistence']:>9.3f}"
            f"{vector['discussion']:>9.3f}{result.participation_scope:>14}"
        )
    print("    score = weighted sum of the four displayed normalised axes")


def _write_json_report(path, history, max_revisions, profiles, impact) -> None:
    """Atomically write a reproducible, self-explaining JSON analysis report."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    capped = max_revisions is not None and len(history.revisions) >= max_revisions
    payload = {
        "schema_version": 1,
        "article": {
            "title": history.title,
            "talk_title": getattr(history, "talk_title", None),
            "revision_count": len(history.revisions),
            "talk_revision_count": len(getattr(history, "talk_revisions", [])),
            "first_edit": history.revisions[0].timestamp,
            "latest_fetched_edit": history.revisions[-1].timestamp,
            "history_scope": (
                "complete"
                if max_revisions is None
                else f"earliest {len(history.revisions)}"
            ),
            "historical_slice": capped,
        },
        "weights": impact.weights.normalised,
        "contributors": [],
    }
    for result in impact.ranked:
        profile = profiles.contributors[result.user]
        payload["contributors"].append(
            {
                "rank": result.rank,
                "user": result.user,
                "composite_score": result.score,
                "participation_scope": result.participation_scope,
                "dominant_dimension": result.dominant_dimension,
                "explanation": result.explanation,
                "features": result.feature_vector,
                "contributions": {
                    dimension: asdict(contribution)
                    for dimension, contribution in result.contributions.items()
                },
                "raw_metrics": {
                    key: value
                    for key, value in asdict(profile).items()
                    if key != "user" and not key.endswith("_score")
                },
            }
        )

    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        json.dump(payload, temporary, ensure_ascii=False, indent=2, sort_keys=True)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
