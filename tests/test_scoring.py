"""Tests for configurable, explainable composite impact scoring."""

import math

import pytest

from wikicontrib.api import RawRevision
from wikicontrib.profile import ContributorProfile, ProfileReport
from wikicontrib.scoring import (
    DIMENSIONS,
    ScoreWeights,
    build_impact_report,
    score_profiles,
)


def _profile(
    user: str,
    *,
    volume: float = 0.0,
    additive: float = 0.0,
    persistence: float = 0.0,
    discussion: float = 0.0,
    article_edits: int = 1,
    talk_posts: int = 0,
) -> ContributorProfile:
    return ContributorProfile(
        user=user,
        article_edits=article_edits,
        talk_posts=talk_posts,
        volume_score=volume,
        additive_score=additive,
        persistence_score=persistence,
        discussion_score=discussion,
    )


def _revision(revid: int, user: str, content: str, timestamp: str) -> RawRevision:
    return RawRevision(
        revid=revid,
        parentid=revid - 1,
        timestamp=timestamp,
        user=user,
        userid=1,
        comment="",
        size=len(content),
        minor=False,
        anon=False,
        content=content,
    )


def test_default_weights_are_equal_and_sum_to_one():
    weights = ScoreWeights()
    assert weights.as_dict == {dimension: 0.25 for dimension in DIMENSIONS}
    assert sum(weights.normalised.values()) == pytest.approx(1.0)


def test_arbitrary_weight_scale_is_normalised():
    weights = ScoreWeights(volume=2, additive=1, persistence=1, discussion=0)
    assert weights.normalised == {
        "volume": 0.5,
        "additive": 0.25,
        "persistence": 0.25,
        "discussion": 0.0,
    }


@pytest.mark.parametrize(
    "weights, message",
    [
        ({"volume": -1}, "volume weight must be non-negative"),
        ({"additive": math.nan}, "additive weight must be finite"),
        ({"persistence": math.inf}, "persistence weight must be finite"),
        (
            {"volume": 0, "additive": 0, "persistence": 0, "discussion": 0},
            "at least one score weight must be positive",
        ),
    ],
)
def test_invalid_weights_are_rejected(weights, message):
    with pytest.raises(ValueError, match=message):
        ScoreWeights(**weights)


def test_composite_is_weighted_sum_and_keeps_every_term():
    profiles = ProfileReport(
        {"Alice": _profile("Alice", volume=1.0, additive=0.5, persistence=0.25)}
    )
    weights = ScoreWeights(volume=2, additive=1, persistence=1, discussion=0)

    result = score_profiles(profiles, weights).contributors["Alice"]

    assert result.score == pytest.approx(0.6875)
    assert result.feature_vector == {
        "volume": 1.0,
        "additive": 0.5,
        "persistence": 0.25,
        "discussion": 0.0,
    }
    assert result.contributions["volume"].weighted_value == pytest.approx(0.5)
    assert sum(
        contribution.weighted_value for contribution in result.contributions.values()
    ) == pytest.approx(result.score)


def test_custom_weights_can_change_the_ranking():
    profiles = ProfileReport(
        {
            "Writer": _profile("Writer", volume=1.0, persistence=0.1),
            "Survivor": _profile("Survivor", volume=0.1, persistence=1.0),
        }
    )

    volume_first = score_profiles(
        profiles, ScoreWeights(volume=3, additive=0, persistence=1, discussion=0)
    )
    persistence_first = score_profiles(
        profiles, ScoreWeights(volume=1, additive=0, persistence=3, discussion=0)
    )

    assert volume_first.ranked[0].user == "Writer"
    assert persistence_first.ranked[0].user == "Survivor"


def test_ties_are_resolved_by_username_for_deterministic_ranks():
    profiles = ProfileReport(
        {
            "Bob": _profile("Bob", volume=0.5),
            "Alice": _profile("Alice", volume=0.5),
        }
    )
    report = score_profiles(profiles)
    assert [(result.rank, result.user) for result in report.ranked] == [
        (1, "Alice"),
        (2, "Bob"),
    ]


def test_explanation_names_dominant_dimension_and_shows_calculation():
    profiles = ProfileReport({"Alice": _profile("Alice", volume=0.2, persistence=1.0)})
    result = score_profiles(profiles).contributors["Alice"]

    assert result.dominant_dimension == "persistence"
    assert "Rank 1; composite 0.300" in result.explanation
    assert "strongest contribution: persistence" in result.explanation
    assert "persistence 1.000 × 0.250 = 0.250" in result.explanation


def test_zero_signal_explanation_does_not_invent_a_dominant_axis():
    result = score_profiles(
        ProfileReport({"Observer": _profile("Observer", article_edits=0, talk_posts=1)})
    ).contributors["Observer"]
    assert result.dominant_dimension is None
    assert "no positive signal on the four profile axes" in result.explanation


@pytest.mark.parametrize("bad_value", [-0.01, 1.01, math.nan, math.inf])
def test_invalid_profile_axes_are_rejected(bad_value):
    profiles = ProfileReport({"Alice": _profile("Alice", volume=bad_value)})
    with pytest.raises(ValueError, match="invalid volume axis score"):
        score_profiles(profiles)


def test_empty_profiles_produce_empty_rank_and_rows():
    report = score_profiles(ProfileReport())
    assert report.contributors == {}
    assert report.ranked == []
    assert report.rows == []


def test_rows_keep_rank_total_scope_and_full_vector():
    report = score_profiles(
        ProfileReport(
            {
                "Alice": _profile(
                    "Alice",
                    volume=1.0,
                    additive=0.5,
                    persistence=0.25,
                    discussion=0.75,
                    talk_posts=2,
                )
            }
        )
    )
    assert report.rows == [
        {
            "rank": 1,
            "user": "Alice",
            "score": pytest.approx(0.625),
            "scope": "article+talk",
            "volume": 1.0,
            "additive": 0.5,
            "persistence": 0.25,
            "discussion": 0.75,
        }
    ]


def test_build_impact_report_runs_profile_and_score_pipeline_end_to_end():
    article_revisions = [
        _revision(1, "Alice", "alpha beta", "2020-01-01T09:00:00Z"),
        _revision(2, "Bob", "alpha beta gamma", "2020-01-02T09:00:00Z"),
    ]
    talk_content = (
        "== Topic ==\n"
        "Proposal. [[User:Alice]] 10:00, 1 January 2020 (UTC)\n"
        ":Reply. [[User:Carol]] 11:00, 1 January 2020 (UTC)"
    )
    talk_revisions = [_revision(10, "Carol", talk_content, "2020-01-02T11:00:00Z")]

    report = build_impact_report(article_revisions, talk_revisions)

    assert set(report.contributors) == {"Alice", "Bob", "Carol"}
    assert [result.rank for result in report.ranked] == [1, 2, 3]
    assert all(0.0 <= result.score <= 1.0 for result in report.ranked)
    assert report.explain(report.ranked[0].user).startswith("Rank 1;")
