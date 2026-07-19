"""Tests for the word-level diff engine."""

import pytest

from wikicontrib.api import RawRevision
from wikicontrib.diff import diff_history, diff_revision, diff_tokens


def _rev(revid, content, user="Alice", parentid=None, minor=False):
    return RawRevision(
        revid=revid,
        parentid=revid - 1 if parentid is None else parentid,
        timestamp=f"2020-01-{revid:02d}T00:00:00Z",
        user=user,
        userid=1,
        comment="",
        size=len(content or ""),
        minor=minor,
        anon=False,
        content=content,
    )


# -- diff_tokens ------------------------------------------------------------


def test_pure_insertion():
    added, removed = diff_tokens(["a"], ["a", "b"])
    assert added == ["b"] and removed == []


def test_pure_deletion():
    added, removed = diff_tokens(["a", "b"], ["a"])
    assert added == [] and removed == ["b"]


def test_replacement_reports_both_sides():
    added, removed = diff_tokens(["a", "b"], ["a", "c"])
    assert added == ["c"] and removed == ["b"]


def test_identical_sequences_produce_no_change():
    assert diff_tokens(["a", "b"], ["a", "b"]) == ([], [])


def test_common_words_are_not_treated_as_junk():
    # SequenceMatcher's autojunk would ignore frequent tokens in long
    # sequences, silently corrupting counts. Verify it stays disabled.
    before = ["the"] * 200
    after = ["the"] * 200 + ["new"]
    added, removed = diff_tokens(before, after)
    assert added == ["new"] and removed == []


# -- diff_revision ----------------------------------------------------------


def test_first_revision_credits_creator_with_everything():
    diff = diff_revision(_rev(1, "Alan Turing was a mathematician"), None)
    assert diff.words_added == 5
    assert diff.words_removed == 0
    assert diff.net_words == 5


def test_carries_revision_metadata():
    diff = diff_revision(_rev(7, "hello", user="Bob", minor=True), "")
    assert diff.revid == 7 and diff.user == "Bob" and diff.minor is True


def test_null_edit_is_empty():
    diff = diff_revision(_rev(2, "same text"), "same text")
    assert diff.is_empty
    assert diff.gross_words == 0
    assert diff.churn == 0.0


def test_markup_only_change_adds_no_words():
    # Wrapping a word in a link changes markup but adds no prose.
    diff = diff_revision(_rev(2, "[[Turing]] was here"), "Turing was here")
    assert diff.words_added == 0
    assert diff.words_removed == 0
    assert not diff.is_empty  # the symbol tokens did change


def test_reformatting_whitespace_is_not_a_change():
    diff = diff_revision(_rev(2, "one\n\n   two"), "one two")
    assert diff.is_empty


# -- counts and churn -------------------------------------------------------


def test_net_vs_gross_distinguishes_rewrite_from_no_edit():
    rewrite = diff_revision(_rev(2, "completely different words here"),
                            "some original words here")
    assert rewrite.net_words == 0        # byte/word delta would see nothing
    assert rewrite.gross_words > 0       # but real work happened
    assert rewrite.churn > 0.5           # and it reads as maintenance


def test_pure_addition_has_zero_churn():
    diff = diff_revision(_rev(2, "old text plus brand new sentence"), "old text")
    assert diff.churn == 0.0
    assert diff.net_words > 0


def test_pure_deletion_has_no_churn_but_negative_net():
    # churn measures replacement overlap, so a one-directional edit scores 0.
    # Deletion is told apart from addition by net_words, not by churn.
    diff = diff_revision(_rev(2, "old"), "old text to remove")
    assert diff.churn == pytest.approx(0.0)
    assert diff.net_words < 0


def test_churn_alone_cannot_separate_addition_from_deletion():
    addition = diff_revision(_rev(2, "old text plus new words"), "old text")
    deletion = diff_revision(_rev(2, "old"), "old text to remove")
    assert addition.churn == deletion.churn == pytest.approx(0.0)
    # ...which is exactly why the classifier must also read net_words.
    assert addition.net_words > 0 > deletion.net_words


def test_balanced_replacement_approaches_full_churn():
    diff = diff_revision(_rev(2, "aaa bbb ccc"), "xxx yyy zzz")
    assert diff.words_added == 3 and diff.words_removed == 3
    assert diff.churn == pytest.approx(1.0)


# -- diff_history -----------------------------------------------------------


def test_history_diffs_each_revision_against_predecessor():
    history = [
        _rev(1, "one"),
        _rev(2, "one two"),
        _rev(3, "one two three"),
    ]
    diffs = diff_history(history)
    assert [d.revid for d in diffs] == [1, 2, 3]
    assert [d.words_added for d in diffs] == [1, 1, 1]
    assert all(d.words_removed == 0 for d in diffs)


def test_history_attributes_changes_to_the_right_users():
    history = [
        _rev(1, "start", user="Alice"),
        _rev(2, "start added", user="Bob"),
        _rev(3, "start", user="Carol"),  # Carol reverts Bob
    ]
    diffs = diff_history(history)
    assert diffs[1].user == "Bob" and diffs[1].net_words == 1
    assert diffs[2].user == "Carol" and diffs[2].net_words == -1


def test_empty_history():
    assert diff_history([]) == []
