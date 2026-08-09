"""Tests for cross-article ranking sensitivity evaluation."""

import json

import pytest

from wikicontrib.api import RawRevision
from wikicontrib.evaluation import (
    EvaluationReport,
    evaluate_article,
    evaluate_profiles,
    write_evaluation_json,
    write_evaluation_markdown,
)
from wikicontrib.profile import ContributorProfile, ProfileReport


def _profile(user, *, volume=0.0, additive=0.0, persistence=0.0, discussion=0.0):
    return ContributorProfile(
        user=user,
        article_edits=1,
        volume_score=volume,
        additive_score=additive,
        persistence_score=persistence,
        discussion_score=discussion,
    )


def _profiles():
    return ProfileReport(
        {
            "Alice": _profile("Alice", volume=1.0, additive=0.2),
            "Bob": _profile("Bob", persistence=1.0, discussion=0.2),
            "Carol": _profile(
                "Carol", volume=0.4, additive=0.4, persistence=0.4, discussion=0.4
            ),
        }
    )


def test_evaluation_detects_policy_dependent_winners():
    result = evaluate_profiles("Example", _profiles(), top_k=2)
    assert result.baseline_winner == "Carol"
    assert result.distinct_winners == ("Carol", "Alice", "Bob")
    assert result.policies[0].spearman_rho == 1.0
    assert result.policies[0].mean_absolute_rank_shift == 0.0
    assert all(0.0 <= policy.top_k_overlap <= 1.0 for policy in result.policies)
    assert all(-1.0 <= policy.spearman_rho <= 1.0 for policy in result.policies)


def test_top_k_is_capped_at_contributor_count():
    result = evaluate_profiles("Example", _profiles(), top_k=10)
    assert result.top_k == 3
    assert all(policy.top_k_overlap == 1.0 for policy in result.policies)


def test_evaluation_rejects_empty_profiles_and_invalid_top_k():
    with pytest.raises(ValueError, match="empty"):
        evaluate_profiles("Empty", ProfileReport())
    with pytest.raises(ValueError, match="positive"):
        evaluate_profiles("Example", _profiles(), top_k=0)


def test_json_and_markdown_outputs_are_self_explaining(tmp_path):
    article = evaluate_profiles(
        "Example",
        _profiles(),
        revision_count=50,
        talk_revision_count=12,
        top_k=2,
    )
    report = EvaluationReport((article,), revision_limit=50)
    json_path = write_evaluation_json(report, tmp_path / "nested" / "evaluation.json")
    markdown_path = write_evaluation_markdown(report, tmp_path / "evaluation.md")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["method"]["historical_slice"] is True
    assert payload["articles"][0]["revision_count"] == 50
    assert len(payload["articles"][0]["policies"]) == 5

    markdown = markdown_path.read_text(encoding="utf-8")
    assert "Composite-score sensitivity evaluation" in markdown
    assert "Spearman" in markdown
    assert "historical slices" in markdown
    assert "not whether a ranking is objectively correct" in markdown


def test_real_revision_evaluation_flags_automated_winner():
    revision = RawRevision(
        revid=1,
        parentid=0,
        timestamp="2002-01-01T00:00:00Z",
        user="Conversion script",
        userid=1,
        comment="Automated conversion",
        size=20,
        minor=False,
        anon=False,
        content="initial article text",
    )
    result = evaluate_article("Example", [revision])
    assert result.automated_account_candidates == ("Conversion script",)
    assert result.baseline_winner_is_automated_candidate is True
