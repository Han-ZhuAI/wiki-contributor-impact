"""Tests for deterministic, headless contributor-impact visualisations."""

from datetime import datetime, timezone

import pytest

from wikicontrib.api import RawRevision
from wikicontrib.profile import ContributorProfile, ProfileReport
from wikicontrib.scoring import ScoreWeights, score_profiles
from wikicontrib.visualize import (
    _month_range,
    _safe_stem,
    generate_visualizations,
    plot_edit_timeline,
)


def _revision(
    revid: int,
    user: str,
    timestamp: str,
    content: str,
    *,
    comment: str = "",
) -> RawRevision:
    return RawRevision(
        revid=revid,
        parentid=revid - 1,
        timestamp=timestamp,
        user=user,
        userid=1,
        comment=comment,
        size=len(content),
        minor=False,
        anon=False,
        content=content,
    )


def _reports():
    profiles = ProfileReport(
        {
            "Alice": ContributorProfile(
                user="Alice",
                article_edits=3,
                gross_words=50,
                additive_edits=2,
                maintenance_edits=1,
                maintenance_ratio=1 / 3,
                volume_score=1.0,
                additive_score=2 / 3,
                persistence_score=0.8,
                discussion_score=0.2,
            ),
            "../Bob / blue": ContributorProfile(
                user="../Bob / blue",
                article_edits=2,
                talk_posts=1,
                gross_words=20,
                additive_edits=1,
                maintenance_edits=1,
                maintenance_ratio=0.5,
                volume_score=0.6,
                additive_score=0.5,
                persistence_score=0.4,
                discussion_score=1.0,
            ),
        }
    )
    impact = score_profiles(
        profiles,
        ScoreWeights(volume=1, additive=1, persistence=2, discussion=1),
    )
    return profiles, impact


def _revisions():
    return [
        _revision(1, "Alice", "2020-01-01T00:00:00Z", "alpha beta gamma"),
        _revision(
            2,
            "Bob",
            "2020-01-15T00:00:00Z",
            "alpha beta gamma delta epsilon",
        ),
        _revision(
            3,
            "Alice",
            "2020-02-01T00:00:00Z",
            "alpha beta gamma delta epsilon fixed",
            comment="copyedit",
        ),
    ]


def test_generate_visualizations_writes_complete_png_manifest(tmp_path):
    profiles, impact = _reports()
    manifest = generate_visualizations(
        "Example",
        _revisions(),
        profiles,
        impact,
        tmp_path,
        top_n=2,
        radar_count=2,
    )

    assert len(manifest.all_paths) == 5
    assert len(manifest.contributor_radars) == 2
    for path in manifest.all_paths:
        assert path.is_file()
        assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert path.stat().st_size > 1_000


def test_untrusted_username_cannot_escape_radar_directory(tmp_path):
    profiles, impact = _reports()
    manifest = generate_visualizations(
        "Example",
        _revisions(),
        profiles,
        impact,
        tmp_path,
        radar_count=2,
    )
    radar_root = (tmp_path / "radars").resolve()
    assert all(
        path.resolve().parent == radar_root for path in manifest.contributor_radars
    )
    assert _safe_stem("../Bob / 蓝") == "Bob"


@pytest.mark.parametrize("top_n, radar_count", [(0, 1), (1, 0), (-1, 1)])
def test_generate_visualizations_rejects_non_positive_limits(
    tmp_path, top_n, radar_count
):
    profiles, impact = _reports()
    with pytest.raises(ValueError, match="must be positive"):
        generate_visualizations(
            "Example",
            _revisions(),
            profiles,
            impact,
            tmp_path,
            top_n=top_n,
            radar_count=radar_count,
        )


def test_generate_visualizations_rejects_empty_impact_report(tmp_path):
    with pytest.raises(ValueError, match="empty impact report"):
        generate_visualizations(
            "Example",
            _revisions(),
            ProfileReport(),
            score_profiles(ProfileReport()),
            tmp_path,
        )


def test_timeline_rejects_empty_revision_history(tmp_path):
    with pytest.raises(ValueError, match="empty revision history"):
        plot_edit_timeline([], tmp_path / "timeline.png", "Example")


def test_timeline_handles_identity_reverts_and_multiple_months(tmp_path):
    revisions = _revisions()
    revisions.append(
        _revision(
            4,
            "Bob",
            "2020-03-01T00:00:00Z",
            revisions[0].content,
            comment="",
        )
    )
    path = plot_edit_timeline(revisions, tmp_path / "timeline.png", "Example")
    assert path.read_bytes().startswith(b"\x89PNG")
    assert path.stat().st_size > 1_000


def test_month_range_keeps_zero_activity_months_visible():
    months = _month_range(
        datetime(2020, 11, 1, tzinfo=timezone.utc),
        datetime(2021, 2, 1, tzinfo=timezone.utc),
    )
    assert [month.strftime("%Y-%m") for month in months] == [
        "2020-11",
        "2020-12",
        "2021-01",
        "2021-02",
    ]
