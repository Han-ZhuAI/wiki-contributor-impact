"""Cross-article evaluation and composite-weight sensitivity analysis.

The composite impact score is intentionally configurable, so a ranking is not
credible until its sensitivity to reasonable weight choices is visible.  This
module compares the neutral equal-weight ranking with four one-axis-emphasis
policies and reports winner changes, top-k overlap, Spearman rank correlation,
and absolute rank movement.

These diagnostics measure *stability*, not ground-truth correctness.  They are
kept separate from the score itself so evaluation cannot silently tune the
model to a preferred result.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from .api import RawRevision
from .automation import AutomationReport, detect_automation_candidates
from .profile import ProfileReport, build_profiles
from .scoring import ScoreWeights, score_profiles

DEFAULT_POLICIES: tuple[tuple[str, ScoreWeights], ...] = (
    ("balanced", ScoreWeights(1, 1, 1, 1)),
    ("volume_emphasis", ScoreWeights(2, 1, 1, 1)),
    ("additive_emphasis", ScoreWeights(1, 2, 1, 1)),
    ("persistence_emphasis", ScoreWeights(1, 1, 2, 1)),
    ("discussion_emphasis", ScoreWeights(1, 1, 1, 2)),
)


@dataclass(frozen=True)
class PolicyEvaluation:
    """One alternative policy compared with the balanced baseline."""

    policy: str
    weights: dict[str, float]
    winner: str
    winner_score: float
    automation_filtered_winner: str | None
    automation_filtered_winner_score: float | None
    top_contributors: tuple[str, ...]
    top_k_overlap: float
    spearman_rho: float
    mean_absolute_rank_shift: float
    maximum_rank_shift: int

    def as_dict(self) -> dict:
        return {
            "policy": self.policy,
            "weights": self.weights,
            "winner": self.winner,
            "winner_score": self.winner_score,
            "automation_filtered_winner": self.automation_filtered_winner,
            "automation_filtered_winner_score": self.automation_filtered_winner_score,
            "winner_changes_after_automation_filter": (
                self.automation_filtered_winner is not None
                and self.winner != self.automation_filtered_winner
            ),
            "top_contributors": list(self.top_contributors),
            "top_k_overlap": self.top_k_overlap,
            "spearman_rho": self.spearman_rho,
            "mean_absolute_rank_shift": self.mean_absolute_rank_shift,
            "maximum_rank_shift": self.maximum_rank_shift,
        }


@dataclass(frozen=True)
class ArticleEvaluation:
    """Sensitivity results for one article history."""

    title: str
    revision_count: int
    talk_revision_count: int
    contributor_count: int
    top_k: int
    baseline_winner: str
    automation: AutomationReport
    policies: tuple[PolicyEvaluation, ...]

    @property
    def automated_account_candidates(self) -> tuple[str, ...]:
        """All high-confidence and review-only candidates, for compatibility."""
        return self.automation.candidate_users

    @property
    def excluded_automated_candidates(self) -> tuple[str, ...]:
        return self.automation.exclusion_candidates

    @property
    def baseline_automation_filtered_winner(self) -> str | None:
        return self.policies[0].automation_filtered_winner if self.policies else None

    @property
    def distinct_winners(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(policy.winner for policy in self.policies))

    @property
    def minimum_top_k_overlap(self) -> float:
        return min((policy.top_k_overlap for policy in self.policies), default=1.0)

    @property
    def minimum_spearman_rho(self) -> float:
        return min((policy.spearman_rho for policy in self.policies), default=1.0)

    @property
    def baseline_winner_is_automated_candidate(self) -> bool:
        return self.baseline_winner in self.excluded_automated_candidates

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "revision_count": self.revision_count,
            "talk_revision_count": self.talk_revision_count,
            "contributor_count": self.contributor_count,
            "top_k": self.top_k,
            "baseline_winner": self.baseline_winner,
            "baseline_automation_filtered_winner": (
                self.baseline_automation_filtered_winner
            ),
            "automation": self.automation.as_dict(),
            "automated_account_candidates": list(self.automated_account_candidates),
            "excluded_automated_candidates": list(self.excluded_automated_candidates),
            "baseline_winner_is_automated_candidate": (
                self.baseline_winner_is_automated_candidate
            ),
            "distinct_winners": list(self.distinct_winners),
            "minimum_top_k_overlap": self.minimum_top_k_overlap,
            "minimum_spearman_rho": self.minimum_spearman_rho,
            "policies": [policy.as_dict() for policy in self.policies],
        }


@dataclass(frozen=True)
class EvaluationReport:
    """Reproducible sensitivity evaluation across multiple articles."""

    articles: tuple[ArticleEvaluation, ...]
    revision_limit: int | None

    def as_dict(self) -> dict:
        return {
            "schema_version": 2,
            "method": {
                "baseline": "equal weights across all four axes",
                "alternatives": "double one axis while holding the others at one",
                "metrics": [
                    "top-k overlap",
                    "Spearman rank correlation",
                    "mean absolute rank shift",
                    "maximum rank shift",
                ],
                "revision_limit": self.revision_limit,
                "historical_slice": self.revision_limit is not None,
                "automation_handling": (
                    "compare the full ranking with an opt-in ranking that omits "
                    "high-confidence username candidates; keep all revisions in "
                    "diff and provenance calculations"
                ),
            },
            "articles": [article.as_dict() for article in self.articles],
        }

    def to_markdown(self) -> str:
        scope = (
            "complete histories"
            if self.revision_limit is None
            else f"the earliest {self.revision_limit} revisions per article"
        )
        lines = [
            "# Composite-score sensitivity evaluation",
            "",
            (
                f"Scope: {scope}. The balanced baseline uses equal weights; each "
                "alternative doubles one axis, producing normalised weights of "
                "0.4/0.2/0.2/0.2."
            ),
            "",
        ]
        for article in self.articles:
            lines.extend(
                [
                    f"## {article.title}",
                    "",
                    (
                        f"Revisions: {article.revision_count}; Talk revisions: "
                        f"{article.talk_revision_count}; contributors: "
                        f"{article.contributor_count}; balanced winner: "
                        f"**{article.baseline_winner}**."
                    ),
                    "",
                    "| Policy | All-account winner | Filtered winner | Top-k overlap | Spearman ρ | Mean shift | Max shift |",
                    "|---|---|---|---:|---:|---:|---:|",
                ]
            )
            for policy in article.policies:
                lines.append(
                    f"| {policy.policy} | {policy.winner} | "
                    f"{policy.automation_filtered_winner or 'none'} | "
                    f"{policy.top_k_overlap:.3f} | {policy.spearman_rho:.3f} | "
                    f"{policy.mean_absolute_rank_shift:.2f} | "
                    f"{policy.maximum_rank_shift} |"
                )
            lines.extend(
                [
                    "",
                    (
                        f"Distinct winners: {', '.join(article.distinct_winners)}. "
                        f"Worst top-{article.top_k} overlap: "
                        f"{article.minimum_top_k_overlap:.3f}; lowest Spearman ρ: "
                        f"{article.minimum_spearman_rho:.3f}."
                    ),
                    "",
                ]
            )
            candidates = ", ".join(article.automated_account_candidates) or "none"
            excluded = ", ".join(article.excluded_automated_candidates) or "none"
            lines.append(f"Automated-account review candidates: {candidates}.")
            lines.append(f"High-confidence ranking exclusions: {excluded}.")
            for candidate in article.automation.candidates:
                lines.append(
                    f"- {candidate.user}: confidence={candidate.confidence}; "
                    f"signals={', '.join(candidate.reasons)}; evidence revisions="
                    f"{', '.join(str(value) for value in candidate.evidence_revision_ids)}"
                )
            if article.baseline_winner_is_automated_candidate:
                lines.append(
                    "**Ranking comparison:** the balanced all-account winner is a "
                    "high-confidence automation candidate; the filtered winner is "
                    f"**{article.baseline_automation_filtered_winner}**."
                )
            lines.append("")
        lines.extend(
            [
                "## Interpretation limits",
                "",
                "- Weight sensitivity measures ranking stability, not whether a ranking is objectively correct.",
                "- Capped runs describe historical slices and must not be presented as current-article results.",
                "- Talk signatures and temporal post-to-edit links are incomplete proxies, not causal evidence.",
                "- Face-validity findings should be checked against editor histories before drawing conclusions.",
                "- Automation filtering changes only ranking eligibility; it never deletes revisions or rewrites provenance.",
                "",
            ]
        )
        return "\n".join(lines)


def evaluate_article(
    title: str,
    article_revisions: list[RawRevision],
    talk_revisions: list[RawRevision] | None = None,
    *,
    top_k: int = 10,
    policies: tuple[tuple[str, ScoreWeights], ...] = DEFAULT_POLICIES,
) -> ArticleEvaluation:
    """Build contributor profiles and evaluate reasonable weight policies."""
    profiles = build_profiles(article_revisions, talk_revisions)
    automation = detect_automation_candidates(article_revisions, talk_revisions)
    return evaluate_profiles(
        title,
        profiles,
        revision_count=len(article_revisions),
        talk_revision_count=len(talk_revisions or []),
        top_k=top_k,
        policies=policies,
        automation=automation,
    )


def evaluate_profiles(
    title: str,
    profiles: ProfileReport,
    *,
    revision_count: int = 0,
    talk_revision_count: int = 0,
    top_k: int = 10,
    policies: tuple[tuple[str, ScoreWeights], ...] = DEFAULT_POLICIES,
    automation: AutomationReport | None = None,
) -> ArticleEvaluation:
    """Evaluate already-built profiles; useful for tests and notebooks."""
    if not profiles.contributors:
        raise ValueError("cannot evaluate an empty contributor profile")
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if not policies or policies[0][0] != "balanced":
        raise ValueError("the first policy must be the balanced baseline")

    automation = automation or AutomationReport()
    reports = [(name, score_profiles(profiles, weights)) for name, weights in policies]
    filtered_reports = [
        (
            name,
            score_profiles(
                profiles,
                weights,
                excluded_users=automation.exclusion_candidates,
            ),
        )
        for name, weights in policies
    ]
    baseline = reports[0][1]
    baseline_ranks = {result.user: result.rank for result in baseline.ranked}
    effective_top_k = min(top_k, len(baseline_ranks))
    baseline_top = tuple(result.user for result in baseline.ranked[:effective_top_k])

    results: list[PolicyEvaluation] = []
    for (name, report), (_, filtered_report) in zip(
        reports, filtered_reports, strict=True
    ):
        ranked = report.ranked
        filtered_ranked = filtered_report.ranked
        ranks = {result.user: result.rank for result in ranked}
        top = tuple(result.user for result in ranked[:effective_top_k])
        shifts = [abs(baseline_ranks[user] - ranks[user]) for user in baseline_ranks]
        results.append(
            PolicyEvaluation(
                policy=name,
                weights=report.weights.normalised,
                winner=ranked[0].user,
                winner_score=ranked[0].score,
                automation_filtered_winner=(
                    filtered_ranked[0].user if filtered_ranked else None
                ),
                automation_filtered_winner_score=(
                    filtered_ranked[0].score if filtered_ranked else None
                ),
                top_contributors=top,
                top_k_overlap=(
                    len(set(baseline_top) & set(top)) / effective_top_k
                    if effective_top_k
                    else 1.0
                ),
                spearman_rho=_spearman_from_ranks(baseline_ranks, ranks),
                mean_absolute_rank_shift=sum(shifts) / len(shifts),
                maximum_rank_shift=max(shifts, default=0),
            )
        )

    return ArticleEvaluation(
        title=title,
        revision_count=revision_count,
        talk_revision_count=talk_revision_count,
        contributor_count=len(profiles.contributors),
        top_k=effective_top_k,
        baseline_winner=baseline.ranked[0].user,
        automation=automation,
        policies=tuple(results),
    )


def write_evaluation_json(report: EvaluationReport, path: Path | str) -> Path:
    """Write the versioned machine-readable report atomically."""
    return _atomic_write(
        Path(path), json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n"
    )


def write_evaluation_markdown(report: EvaluationReport, path: Path | str) -> Path:
    """Write a concise report-ready sensitivity table atomically."""
    return _atomic_write(Path(path), report.to_markdown())


def _spearman_from_ranks(
    baseline: dict[str, int], alternative: dict[str, int]
) -> float:
    if baseline.keys() != alternative.keys():
        raise ValueError("rankings must contain the same contributors")
    count = len(baseline)
    if count < 2:
        return 1.0
    squared_difference = sum(
        (baseline[user] - alternative[user]) ** 2 for user in baseline
    )
    return 1.0 - (6.0 * squared_difference) / (count * (count**2 - 1))


def _atomic_write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise
    return path
