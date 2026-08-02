"""Tests for unified contributor feature profiles and normalisation."""

import pytest

from wikicontrib.api import RawRevision
from wikicontrib.discussion import ContributorDiscussion, DiscussionReport
from wikicontrib.metrics import ContributorVolume, VolumeReport
from wikicontrib.persistence import ContributorPersistence, PersistenceReport
from wikicontrib.profile import (
    _log_max_normalise,
    assemble_profiles,
    build_profiles,
)


def _volume(
    user: str,
    *,
    words_added: int,
    words_removed: int = 0,
    additive_edits: int = 1,
    maintenance_edits: int = 0,
) -> ContributorVolume:
    return ContributorVolume(
        user=user,
        edits=additive_edits + maintenance_edits,
        words_added=words_added,
        words_removed=words_removed,
        additive_edits=additive_edits,
        maintenance_edits=maintenance_edits,
        additive_words=words_added if additive_edits else 0,
    )


def _revision(
    revid: int,
    user: str,
    content: str,
    timestamp: str,
) -> RawRevision:
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


def test_empty_reports_produce_empty_profile_report():
    report = assemble_profiles(VolumeReport(), PersistenceReport(), DiscussionReport())
    assert report.contributors == {}
    assert report.feature_matrix == []


def test_profiles_join_article_only_talk_only_and_shared_users():
    volume = VolumeReport(
        contributors={
            "Alice": _volume("Alice", words_added=20),
            "Bob": _volume("Bob", words_added=5),
        }
    )
    persistence = PersistenceReport(
        contributors={
            "Alice": ContributorPersistence("Alice", 20, 15),
            "Bob": ContributorPersistence("Bob", 5, 2),
        },
        final_word_count=17,
    )
    discussion = DiscussionReport(
        contributors={
            "Alice": ContributorDiscussion("Alice", posts=2, pagerank=0.7),
            "Carol": ContributorDiscussion("Carol", posts=4, pagerank=0.3),
        }
    )

    report = assemble_profiles(volume, persistence, discussion)

    assert set(report.contributors) == {"Alice", "Bob", "Carol"}
    assert report.contributors["Alice"].participation_scope == "article+talk"
    assert report.contributors["Bob"].participation_scope == "article"
    assert report.contributors["Carol"].participation_scope == "talk"


def test_raw_evidence_is_preserved_in_profile():
    volume_metrics = _volume(
        "Alice",
        words_added=30,
        words_removed=10,
        additive_edits=3,
        maintenance_edits=1,
    )
    persistence_metrics = ContributorPersistence("Alice", 30, 21)
    discussion_metrics = ContributorDiscussion(
        "Alice",
        posts=4,
        threads_started=1,
        replies_made=2,
        replies_received=3,
        follow_up_edits=5,
        pagerank=0.4,
    )
    profile = assemble_profiles(
        VolumeReport({"Alice": volume_metrics}),
        PersistenceReport({"Alice": persistence_metrics}, final_word_count=21),
        DiscussionReport(contributors={"Alice": discussion_metrics}),
    ).contributors["Alice"]

    assert profile.article_edits == 4
    assert profile.words_added == 30
    assert profile.words_removed == 10
    assert profile.gross_words == 40
    assert profile.net_words == 20
    assert profile.maintenance_ratio == pytest.approx(0.25)
    assert profile.words_introduced == 30
    assert profile.words_surviving == 21
    assert profile.survival_rate == pytest.approx(0.7)
    assert profile.talk_posts == 4
    assert profile.replies_received == 3
    assert profile.follow_up_edits == 5


def test_each_nonempty_dimension_has_a_one_point_zero_anchor():
    report = assemble_profiles(
        VolumeReport(
            {
                "Alice": _volume("Alice", words_added=99),
                "Bob": _volume("Bob", words_added=9),
            }
        ),
        PersistenceReport(
            {
                "Alice": ContributorPersistence("Alice", 99, 99),
                "Bob": ContributorPersistence("Bob", 9, 9),
            }
        ),
        DiscussionReport(
            contributors={
                "Alice": ContributorDiscussion("Alice", posts=1, pagerank=0.8),
                "Bob": ContributorDiscussion("Bob", posts=1, pagerank=0.2),
            }
        ),
    )
    alice = report.contributors["Alice"]
    assert alice.volume_score == pytest.approx(1.0)
    assert alice.persistence_score == pytest.approx(1.0)
    assert alice.discussion_score == pytest.approx(1.0)


def test_log_scaling_reduces_outlier_compression():
    assert _log_max_normalise(9, 99) == pytest.approx(0.5)
    assert _log_max_normalise(0, 99) == 0.0
    assert _log_max_normalise(9, 0) == 0.0


def test_additive_axis_is_edit_orientation_not_another_volume_count():
    report = assemble_profiles(
        VolumeReport(
            {
                "Author": _volume(
                    "Author", words_added=10, additive_edits=4, maintenance_edits=0
                ),
                "Maintainer": _volume(
                    "Maintainer",
                    words_added=100,
                    additive_edits=1,
                    maintenance_edits=3,
                ),
            }
        ),
        PersistenceReport(),
        DiscussionReport(),
    )
    assert report.contributors["Author"].additive_score == 1.0
    assert report.contributors["Maintainer"].additive_score == pytest.approx(0.25)


def test_talk_only_contributor_has_zero_article_axes():
    report = assemble_profiles(
        VolumeReport(),
        PersistenceReport(),
        DiscussionReport(
            contributors={
                "Carol": ContributorDiscussion("Carol", posts=2, pagerank=1.0)
            }
        ),
    )
    profile = report.contributors["Carol"]
    assert profile.volume_score == 0.0
    assert profile.additive_score == 0.0
    assert profile.persistence_score == 0.0
    assert profile.discussion_score == 1.0


def test_feature_vector_is_named_and_bounded():
    report = assemble_profiles(
        VolumeReport({"Alice": _volume("Alice", words_added=10)}),
        PersistenceReport(
            {"Alice": ContributorPersistence("Alice", 10, 7)}
        ),
        DiscussionReport(
            contributors={
                "Alice": ContributorDiscussion("Alice", posts=1, pagerank=1.0)
            }
        ),
    )
    vector = report.contributors["Alice"].feature_vector
    assert list(vector) == ["volume", "additive", "persistence", "discussion"]
    assert all(0.0 <= value <= 1.0 for value in vector.values())


def test_feature_matrix_and_ranking_are_deterministic():
    report = assemble_profiles(
        VolumeReport(
            {
                "Bob": _volume("Bob", words_added=10),
                "Alice": _volume("Alice", words_added=10),
            }
        ),
        PersistenceReport(),
        DiscussionReport(),
    )
    assert [row["user"] for row in report.feature_matrix] == ["Alice", "Bob"]
    assert [profile.user for profile in report.ranked()] == ["Alice", "Bob"]


def test_build_profiles_runs_all_metric_pipelines_end_to_end():
    article_revisions = [
        _revision(1, "Alice", "alpha beta", "2020-01-01T09:00:00Z"),
        _revision(2, "Bob", "alpha beta gamma", "2020-01-02T09:00:00Z"),
    ]
    talk_content = (
        "== Topic ==\n"
        "Proposal. [[User:Alice]] 10:00, 1 January 2020 (UTC)\n"
        ":Reply. [[User:Carol]] 11:00, 1 January 2020 (UTC)"
    )
    talk_revisions = [
        _revision(10, "Carol", talk_content, "2020-01-02T11:00:00Z")
    ]

    report = build_profiles(article_revisions, talk_revisions)

    assert set(report.contributors) == {"Alice", "Bob", "Carol"}
    assert report.contributors["Alice"].words_surviving == 2
    assert report.contributors["Bob"].words_surviving == 1
    assert report.contributors["Carol"].talk_posts == 1
    assert report.contributors["Carol"].participation_scope == "talk"
