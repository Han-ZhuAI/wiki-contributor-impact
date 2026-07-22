"""Tests for hash-based identity-revert detection."""

from wikicontrib.api import RawRevision
from wikicontrib.reverts import find_identity_reverts, reverted_revids


def _rev(revid, content, user="Alice"):
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


def test_no_reverts_in_linear_history():
    history = [_rev(1, "a"), _rev(2, "a b"), _rev(3, "a b c")]
    assert find_identity_reverts(history) == {}


def test_simple_revert_detected():
    history = [
        _rev(1, "good text"),
        _rev(2, "good text VANDALISM", user="Vandal"),
        _rev(3, "good text", user="Patroller"),  # restores rev 1
    ]
    assert find_identity_reverts(history) == {3: 1}


def test_null_edit_is_not_a_revert():
    history = [_rev(1, "same"), _rev(2, "same")]
    assert find_identity_reverts(history) == {}


def test_null_edit_after_revert_is_not_double_counted():
    history = [
        _rev(1, "good"),
        _rev(2, "bad", user="Vandal"),
        _rev(3, "good", user="Patroller"),  # the revert
        _rev(4, "good"),                    # null edit right after
    ]
    assert find_identity_reverts(history) == {3: 1}


def test_revert_war_maps_to_first_occurrence():
    history = [
        _rev(1, "A"),
        _rev(2, "B", user="Vandal"),
        _rev(3, "A", user="Patroller"),
        _rev(4, "B", user="Vandal"),
        _rev(5, "A", user="Patroller"),
    ]
    reverts = find_identity_reverts(history)
    assert reverts == {3: 1, 4: 2, 5: 1}


def test_missing_content_treated_as_empty():
    # Revisions without content must not crash; empty pages can legitimately
    # repeat (e.g. page blanked twice).
    blank1 = _rev(1, "")
    filled = _rev(2, "text")
    blanked = _rev(3, "")
    assert find_identity_reverts([blank1, filled, blanked]) == {3: 1}


# -- reverted_revids --------------------------------------------------------


def test_reverted_revids_identifies_undone_edits():
    history = [
        _rev(1, "good"),
        _rev(2, "bad", user="Vandal"),
        _rev(3, "worse", user="Vandal"),
        _rev(4, "good", user="Patroller"),  # undoes 2 and 3
    ]
    assert reverted_revids(history) == {2, 3}


def test_reverted_revids_empty_when_no_reverts():
    assert reverted_revids([_rev(1, "a"), _rev(2, "a b")]) == set()


def test_revert_war_marks_all_intermediate_edits():
    history = [
        _rev(1, "A"),
        _rev(2, "B", user="Vandal"),
        _rev(3, "A", user="Patroller"),
        _rev(4, "B", user="Vandal"),
        _rev(5, "A", user="Patroller"),
    ]
    # 2 was undone by 3; 3 was "undone" by 4; 4 undone by 5.
    assert reverted_revids(history) == {2, 3, 4}


def test_accepts_precomputed_reverts():
    history = [_rev(1, "good"), _rev(2, "bad"), _rev(3, "good")]
    reverts = find_identity_reverts(history)
    assert reverted_revids(history, reverts) == {2}
