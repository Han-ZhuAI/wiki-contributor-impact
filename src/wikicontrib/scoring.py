"""Transparent composite impact scores built from contributor profiles.

The composite is a policy layer over the four normalised profile axes.  Its
weights are explicit, validated, and normalised before use.  Every result keeps
the original feature vector and each dimension's weighted contribution so a
ranking can be audited instead of treated as a black box.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import isfinite

from .api import RawRevision
from .profile import ContributorProfile, ProfileReport, build_profiles

DIMENSIONS = ("volume", "additive", "persistence", "discussion")


@dataclass(frozen=True)
class ScoreWeights:
    """Non-negative weights for the four impact dimensions.

    Equal weights are the deliberately neutral default.  Callers may provide
    any non-negative scale; values are normalised to sum to one before scoring.
    """

    volume: float = 0.25
    additive: float = 0.25
    persistence: float = 0.25
    discussion: float = 0.25

    def __post_init__(self) -> None:
        values = self.as_dict
        for dimension, value in values.items():
            if not isfinite(value):
                raise ValueError(f"{dimension} weight must be finite")
            if value < 0:
                raise ValueError(f"{dimension} weight must be non-negative")
        if not any(values.values()):
            raise ValueError("at least one score weight must be positive")

    @property
    def as_dict(self) -> dict[str, float]:
        """Return weights in the canonical dimension order."""
        return {dimension: float(getattr(self, dimension)) for dimension in DIMENSIONS}

    @property
    def normalised(self) -> dict[str, float]:
        """Return weights scaled to sum to one."""
        values = self.as_dict
        total = sum(values.values())
        return {dimension: value / total for dimension, value in values.items()}


@dataclass(frozen=True)
class DimensionContribution:
    """One auditable term in a contributor's composite score."""

    axis_score: float
    weight: float
    weighted_value: float


@dataclass(frozen=True)
class ContributorImpact:
    """Ranked composite score with its complete explanation data."""

    user: str
    score: float
    feature_vector: dict[str, float]
    contributions: dict[str, DimensionContribution]
    participation_scope: str
    rank: int = 0

    @property
    def dominant_dimension(self) -> str | None:
        """Dimension contributing most to the total, or none for a zero score."""
        if self.score == 0:
            return None
        return max(
            DIMENSIONS,
            key=lambda dimension: self.contributions[dimension].weighted_value,
        )

    @property
    def explanation(self) -> str:
        """Human-readable calculation rationale without hiding the vector."""
        terms = ", ".join(
            f"{dimension} {term.axis_score:.3f} × {term.weight:.3f}"
            f" = {term.weighted_value:.3f}"
            for dimension in DIMENSIONS
            for term in (self.contributions[dimension],)
        )
        if self.dominant_dimension is None:
            rationale = "no positive signal on the four profile axes"
        else:
            rationale = f"strongest contribution: {self.dominant_dimension}"
        return (
            f"Rank {self.rank}; composite {self.score:.3f}; {rationale}. "
            f"Breakdown: {terms}."
        )


@dataclass
class ImpactReport:
    """Deterministically ranked composite results and scoring policy."""

    weights: ScoreWeights = field(default_factory=ScoreWeights)
    contributors: dict[str, ContributorImpact] = field(default_factory=dict)

    @property
    def ranked(self) -> list[ContributorImpact]:
        """Return results in assigned rank order."""
        return sorted(self.contributors.values(), key=lambda result: result.rank)

    def explain(self, user: str) -> str:
        """Return the calculation rationale for one contributor."""
        return self.contributors[user].explanation

    @property
    def rows(self) -> list[dict[str, str | int | float]]:
        """Flat deterministic output suitable for later CSV/JSON export."""
        return [
            {
                "rank": result.rank,
                "user": result.user,
                "score": result.score,
                "scope": result.participation_scope,
                **result.feature_vector,
            }
            for result in self.ranked
        ]


def build_impact_report(
    article_revisions: list[RawRevision],
    talk_revisions: list[RawRevision] | None = None,
    weights: ScoreWeights | None = None,
) -> ImpactReport:
    """Build profiles from revision histories and calculate composite scores."""
    return score_profiles(build_profiles(article_revisions, talk_revisions), weights)


def score_profiles(
    profiles: ProfileReport,
    weights: ScoreWeights | None = None,
) -> ImpactReport:
    """Apply a visible weighted sum to normalised contributor profiles."""
    selected_weights = weights or ScoreWeights()
    normalised_weights = selected_weights.normalised
    unranked = [
        _score_profile(profile, normalised_weights)
        for profile in profiles.contributors.values()
    ]
    ordered = sorted(unranked, key=lambda result: (-result.score, result.user))
    ranked = {
        result.user: replace(result, rank=rank)
        for rank, result in enumerate(ordered, start=1)
    }
    return ImpactReport(weights=selected_weights, contributors=ranked)


def _score_profile(
    profile: ContributorProfile,
    weights: dict[str, float],
) -> ContributorImpact:
    vector = profile.feature_vector
    for dimension, value in vector.items():
        if not isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError(
                f"{profile.user!r} has invalid {dimension} axis score {value!r}"
            )

    contributions = {
        dimension: DimensionContribution(
            axis_score=vector[dimension],
            weight=weights[dimension],
            weighted_value=vector[dimension] * weights[dimension],
        )
        for dimension in DIMENSIONS
    }
    score = sum(term.weighted_value for term in contributions.values())
    return ContributorImpact(
        user=profile.user,
        score=score,
        feature_vector=dict(vector),
        contributions=contributions,
        participation_scope=profile.participation_scope,
    )
