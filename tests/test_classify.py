"""Tests for the additive-vs-maintenance classifier."""

import pytest

from wikicontrib.classify import (
    Classification,
    ClassifierConfig,
    EditType,
    classify_edit,
    strip_section_marker,
)
from wikicontrib.diff import RevisionDiff


def _diff(added=0, removed=0, *, comment="", minor=False, user="Alice"):
    return RevisionDiff(
        revid=2,
        parentid=1,
        user=user,
        timestamp="2020-01-01T00:00:00Z",
        minor=minor,
        anon=False,
        comment=comment,
        added=["w"] * added,
        removed=["w"] * removed,
    )


def cls(**kw):
    return classify_edit(_diff(**kw))


# -- section marker stripping ----------------------------------------------


def test_strip_section_marker():
    assert strip_section_marker("/* Early life */ added date") == "added date"
    assert strip_section_marker("no marker here") == "no marker here"
    assert strip_section_marker("") == ""


def test_section_marker_does_not_trigger_keywords():
    # "References" as a section name must not be read as a "ref" maintenance tag.
    c = classify_edit(_diff(added=40, comment="/* References */ added a paragraph"))
    assert c.edit_type is EditType.ADDITIVE


# -- revert detection (rule 1, highest priority) ---------------------------


@pytest.mark.parametrize("comment", [
    "rv vandalism", "reverted edits by X", "undid revision 123",
    "rvv", "restore previous version", "Undo",
])
def test_revert_comments_are_maintenance(comment):
    # Even though this "adds" a lot of words back, it is a revert.
    c = classify_edit(_diff(added=200, comment=comment))
    assert c.edit_type is EditType.MAINTENANCE
    assert c.reason == "revert-comment"


def test_rv_word_boundary_does_not_match_survey():
    c = classify_edit(_diff(added=30, comment="expanded the survey results"))
    assert c.edit_type is EditType.ADDITIVE


# -- formatting / no word change (rule 2) ----------------------------------


def test_markup_only_change_is_formatting():
    c = classify_edit(_diff(added=0, removed=0, comment="fixed link syntax"))
    assert c.edit_type is EditType.MAINTENANCE
    assert c.reason == "formatting"


# -- maintenance comments (rule 3) -----------------------------------------


@pytest.mark.parametrize("comment", [
    "fix typo", "ce", "copyedit", "fmt", "wikify", "cleanup",
    "spelling", "added category", "fixed refs", "grammar",
])
def test_maintenance_comments(comment):
    c = classify_edit(_diff(added=3, removed=1, comment=comment))
    assert c.edit_type is EditType.MAINTENANCE
    assert c.reason == "maintenance-comment"


# -- diff-signal rules (4-7) -----------------------------------------------


def test_trim_is_maintenance():
    c = cls(added=1, removed=40)
    assert c.edit_type is EditType.MAINTENANCE
    assert c.reason == "trim"


def test_high_churn_rewrite_is_maintenance():
    # 8 in, 8 out: churn 1.0, net 0 -> a rewrite/copy-edit.
    c = cls(added=8, removed=8)
    assert c.edit_type is EditType.MAINTENANCE
    assert c.reason == "rewrite"


def test_large_expansion_is_additive():
    c = cls(added=120, removed=2)
    assert c.edit_type is EditType.ADDITIVE
    assert c.reason == "expansion"


def test_small_addition_is_additive():
    c = cls(added=4, removed=0)
    assert c.edit_type is EditType.ADDITIVE
    assert c.reason == "small-addition"


def test_small_minor_flagged_addition_is_maintenance():
    c = cls(added=3, removed=0, minor=True)
    assert c.edit_type is EditType.MAINTENANCE
    assert c.reason == "minor-change"


def test_expansion_wins_even_when_flagged_minor():
    # A large net gain outweighs a (mis)applied minor flag.
    c = cls(added=120, removed=0, minor=True)
    assert c.edit_type is EditType.ADDITIVE


# -- priority ordering ------------------------------------------------------


def test_revert_comment_beats_additive_signal():
    # Big net-positive diff, but summary says revert -> maintenance wins.
    c = classify_edit(_diff(added=300, removed=0, comment="rv"))
    assert c.edit_type is EditType.MAINTENANCE
    assert c.reason == "revert-comment"


# -- config -----------------------------------------------------------------


def test_config_threshold_changes_outcome():
    diff = _diff(added=8, removed=0)
    strict = ClassifierConfig(additive_net_words=20)
    # 8 net words: additive under the default (>=10? no, 8<10 -> small-addition
    # which is still additive), but with a higher bar it's a small-addition too.
    default = classify_edit(diff)
    assert default.edit_type is EditType.ADDITIVE
    # Raise the trim threshold so a modest removal counts as a trim.
    lenient = ClassifierConfig(trim_net_words=-2)
    c = classify_edit(_diff(added=0, removed=3), lenient)
    assert c.reason == "trim"


def test_signals_recorded_for_audit():
    c = cls(added=10, removed=2, minor=False)
    assert c.signals["net_words"] == 8
    assert c.signals["gross_words"] == 12
    assert "churn" in c.signals


def test_classification_is_additive_helper():
    assert classify_edit(_diff(added=100)).is_additive is True
    assert classify_edit(_diff(added=0, comment="typo")).is_additive is False
