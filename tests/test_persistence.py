"""Tests for content-persistence (token-survival) tracking."""

import pytest

from wikicontrib.api import RawRevision
from wikicontrib.persistence import (
    ContributorPersistence,
    track_persistence,
)


def _rev(revid, content, user):
    return RawRevision(
        revid=revid,
        parentid=revid - 1,
        timestamp=f"2020-01-{revid:02d}T00:00:00Z",
        user=user,
        userid=1,
        comment="",
        size=len(content),
        minor=False,
        anon=False,
        content=content,
    )


def test_single_author_all_survives():
    report = track_persistence([_rev(1, "alan turing was a mathematician", "Alice")])
    alice = report.contributors["Alice"]
    assert alice.words_introduced == 5
    assert alice.words_surviving == 5
    assert alice.survival_rate == 1.0
    assert report.final_word_count == 5


def test_surviving_words_keep_original_author():
    # Bob appends to Alice's text; Alice's words persist under Alice.
    report = track_persistence([
        _rev(1, "alan turing", "Alice"),
        _rev(2, "alan turing was british", "Bob"),
    ])
    assert report.contributors["Alice"].words_surviving == 2
    assert report.contributors["Bob"].words_introduced == 2
    assert report.contributors["Bob"].words_surviving == 2


def test_reverted_text_does_not_survive():
    # Vandal inserts words that the next revision removes entirely.
    report = track_persistence([
        _rev(1, "good encyclopedic text", "Alice"),
        _rev(2, "good encyclopedic text BUY CHEAP PILLS NOW", "Vandal"),
        _rev(3, "good encyclopedic text", "Patroller"),
    ])
    vandal = report.contributors["Vandal"]
    assert vandal.words_introduced == 4      # BUY CHEAP PILLS NOW
    assert vandal.words_surviving == 0
    assert vandal.survival_rate == 0.0
    # Alice's original text is untouched throughout.
    assert report.contributors["Alice"].words_surviving == 3


def test_partial_survival_rate():
    # Alice writes four words; a later edit deletes two of them.
    report = track_persistence([
        _rev(1, "one two three four", "Alice"),
        _rev(2, "one three", "Bob"),
    ])
    alice = report.contributors["Alice"]
    assert alice.words_introduced == 4
    assert alice.words_surviving == 2
    assert alice.survival_rate == pytest.approx(0.5)


def test_overwriting_author_gets_credit_not_the_original():
    # Bob replaces Alice's word; the surviving word is Bob's.
    report = track_persistence([
        _rev(1, "colour", "Alice"),
        _rev(2, "color", "Bob"),
    ])
    assert report.contributors["Alice"].words_surviving == 0
    assert report.contributors["Bob"].words_surviving == 1


def test_hidden_author_bucketed():
    report = track_persistence([_rev(1, "some text here", None)])
    assert "(hidden)" in report.contributors
    assert report.contributors["(hidden)"].words_surviving == 3


def test_share_of_surviving():
    report = track_persistence([
        _rev(1, "aaa bbb ccc", "Alice"),   # 3 words
        _rev(2, "aaa bbb ccc ddd", "Bob"),  # +1 word
    ])
    assert report.final_word_count == 4
    assert report.share_of_surviving("Alice") == pytest.approx(0.75)
    assert report.share_of_surviving("Bob") == pytest.approx(0.25)


def test_ranked_by_surviving_words():
    report = track_persistence([
        _rev(1, "a b c d e", "Big"),
        _rev(2, "a b c d e f", "Small"),
    ])
    ranked = report.ranked()
    assert ranked[0].user == "Big"
    assert ranked[1].user == "Small"


def test_survival_rate_zero_without_contribution():
    assert ContributorPersistence(user="Ghost").survival_rate == 0.0


def test_empty_history():
    report = track_persistence([])
    assert report.contributors == {}
    assert report.final_word_count == 0


def test_volume_and_persistence_diverge_for_vandalism():
    # The whole point: a high-volume vandal has near-zero persistence.
    report = track_persistence([
        _rev(1, "the article body", "Author"),
        _rev(2, "the article body " + "spam " * 100, "Vandal"),
        _rev(3, "the article body", "Patroller"),
    ])
    vandal = report.contributors["Vandal"]
    assert vandal.words_introduced == 100     # high volume
    assert vandal.words_surviving == 0        # zero persistence
