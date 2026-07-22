"""Tests for per-contributor volume aggregation."""

import pytest

from wikicontrib.diff import RevisionDiff
from wikicontrib.metrics import (
    HIDDEN_AUTHOR,
    aggregate_volume,
    ContributorVolume,
)


def _diff(user, added, removed, *, revid=1, timestamp="2020-01-01T00:00:00Z",
          minor=False, anon=False, comment=""):
    return RevisionDiff(
        revid=revid,
        parentid=revid - 1,
        user=user,
        timestamp=timestamp,
        minor=minor,
        anon=anon,
        comment=comment,
        added=["w"] * added,       # word tokens
        removed=["w"] * removed,
    )


def test_single_contributor_totals():
    report = aggregate_volume([_diff("Alice", 10, 0), _diff("Alice", 5, 3)])
    alice = report.contributors["Alice"]
    assert alice.edits == 2
    assert alice.words_added == 15
    assert alice.words_removed == 3
    assert alice.net_words == 12
    assert alice.gross_words == 18


def test_separates_contributors():
    report = aggregate_volume([
        _diff("Alice", 10, 0),
        _diff("Bob", 4, 1),
        _diff("Alice", 2, 0),
    ])
    assert report.contributors["Alice"].words_added == 12
    assert report.contributors["Bob"].words_added == 4
    assert set(report.contributors) == {"Alice", "Bob"}


def test_hidden_author_grouped_under_sentinel():
    report = aggregate_volume([_diff(None, 3, 0)])
    assert HIDDEN_AUTHOR in report.contributors
    assert report.contributors[HIDDEN_AUTHOR].words_added == 3


def test_minor_edits_counted():
    report = aggregate_volume([
        _diff("Alice", 1, 0, minor=True),
        _diff("Alice", 1, 0, minor=False),
    ])
    assert report.contributors["Alice"].minor_edits == 1
    assert report.contributors["Alice"].edits == 2


def test_empty_edit_counts_but_adds_no_words():
    report = aggregate_volume([_diff("Alice", 0, 0)])
    alice = report.contributors["Alice"]
    assert alice.edits == 1
    assert alice.gross_words == 0


def test_first_and_last_edit_track_time_span():
    report = aggregate_volume([
        _diff("Alice", 1, 0, timestamp="2020-06-01T00:00:00Z"),
        _diff("Alice", 1, 0, timestamp="2020-01-01T00:00:00Z"),
        _diff("Alice", 1, 0, timestamp="2020-03-01T00:00:00Z"),
    ])
    alice = report.contributors["Alice"]
    assert alice.first_edit == "2020-01-01T00:00:00Z"
    assert alice.last_edit == "2020-06-01T00:00:00Z"


def test_avg_words_per_edit():
    report = aggregate_volume([_diff("Alice", 6, 0), _diff("Alice", 0, 2)])
    assert report.contributors["Alice"].avg_words_per_edit == pytest.approx(4.0)


def test_avg_words_per_edit_zero_when_no_edits():
    assert ContributorVolume(user="Ghost").avg_words_per_edit == 0.0


# -- ranking and shares -----------------------------------------------------


def test_ranked_by_net_words_default():
    report = aggregate_volume([
        _diff("Alice", 10, 0),
        _diff("Bob", 30, 0),
        _diff("Carol", 20, 0),
    ])
    assert [c.user for c in report.ranked()] == ["Bob", "Carol", "Alice"]


def test_ranked_by_other_metric():
    report = aggregate_volume([
        _diff("Alice", 5, 0, revid=1),
        _diff("Alice", 5, 0, revid=2),
        _diff("Bob", 100, 0, revid=3),
    ])
    # Alice has more edits, Bob more words.
    assert report.ranked(by="edits")[0].user == "Alice"
    assert report.ranked(by="words_added")[0].user == "Bob"


def test_ranking_ties_break_alphabetically():
    report = aggregate_volume([_diff("Zoe", 5, 0), _diff("Amy", 5, 0)])
    assert [c.user for c in report.ranked()] == ["Amy", "Zoe"]


def test_share_of_added():
    report = aggregate_volume([_diff("Alice", 75, 0), _diff("Bob", 25, 0)])
    assert report.total_words_added == 100
    assert report.share_of_added("Alice") == pytest.approx(0.75)
    assert report.share_of_added("Bob") == pytest.approx(0.25)


def test_share_of_added_handles_empty():
    report = aggregate_volume([])
    assert report.total_words_added == 0
    assert report.share_of_added("Nobody") == 0.0


def test_share_is_zero_for_unknown_user():
    report = aggregate_volume([_diff("Alice", 10, 0)])
    assert report.share_of_added("Stranger") == 0.0


# -- additive vs maintenance split ------------------------------------------


def test_additive_and_maintenance_edits_are_counted():
    report = aggregate_volume([
        _diff("Alice", 100, 0),                       # expansion -> additive
        _diff("Alice", 0, 0, comment="fix typo"),     # -> maintenance
        _diff("Alice", 8, 8),                          # rewrite -> maintenance
    ])
    alice = report.contributors["Alice"]
    assert alice.edits == 3
    assert alice.additive_edits == 1
    assert alice.maintenance_edits == 2
    assert alice.maintenance_ratio == pytest.approx(2 / 3)


def test_additive_words_track_only_additive_edits():
    report = aggregate_volume([
        _diff("Alice", 100, 0),                    # additive: +100 words
        _diff("Alice", 5, 40),                      # trim -> maintenance
    ])
    alice = report.contributors["Alice"]
    assert alice.additive_words == 100  # the trim's 5 added words don't count


def test_content_author_vs_gnome_are_distinguished():
    author = aggregate_volume([_diff("Author", 200, 0)]).contributors["Author"]
    gnome = aggregate_volume([
        _diff("Gnome", 0, 0, comment="ce"),
        _diff("Gnome", 0, 0, comment="fmt"),
    ]).contributors["Gnome"]
    assert author.maintenance_ratio == 0.0
    assert gnome.maintenance_ratio == 1.0


def test_maintenance_ratio_zero_without_edits():
    assert ContributorVolume(user="Ghost").maintenance_ratio == 0.0


# -- identity reverts in aggregation ----------------------------------------


def test_identity_reverts_classify_as_maintenance():
    report = aggregate_volume(
        [_diff("Patroller", 300, 5, revid=9)],   # would read as expansion...
        identity_reverts={9},                     # ...but hashing proved revert
    )
    patroller = report.contributors["Patroller"]
    assert patroller.maintenance_edits == 1
    assert patroller.additive_edits == 0


def test_aggregate_history_pipeline_detects_reverts():
    from wikicontrib.api import RawRevision
    from wikicontrib.metrics import aggregate_history

    def rev(revid, content, user):
        return RawRevision(
            revid=revid, parentid=revid - 1,
            timestamp=f"2020-01-{revid:02d}T00:00:00Z",
            user=user, userid=1, comment="", size=len(content),
            minor=False, anon=False, content=content,
        )

    history = [
        rev(1, "good article text", "Author"),
        rev(2, "good article text JUNK JUNK JUNK", "Vandal"),
        rev(3, "good article text", "Patroller"),  # unlabelled revert
    ]
    report = aggregate_history(history)
    # The patroller's restore adds words vs. its parent, but must be
    # classified maintenance via the hash proof, with no additive credit.
    patroller = report.contributors["Patroller"]
    assert patroller.maintenance_edits == 1
    assert patroller.additive_edits == 0
    assert patroller.additive_words == 0
