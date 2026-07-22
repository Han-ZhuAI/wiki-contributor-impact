"""Validation of the classifier against hand-labelled real edits.

The fixture holds 25 edits from the real history of "Alan Turing", labelled by
inspecting each edit's summary and its actual added/removed tokens (see the
fixture's per-item notes). This is the honesty check the synthetic unit tests
cannot provide: real edit summaries are sloppy, real minor-flags are
over-applied (every early edit in this sample carries one), and real edits mix
motives.

The bar is deliberately not 100%: borderline cases are included *with* their
honest labels rather than being cherry-picked out, and known disagreements are
documented in the fixture notes.
"""

import json
from pathlib import Path

from wikicontrib.classify import classify_edit
from wikicontrib.diff import RevisionDiff

FIXTURE = Path(__file__).parent / "fixtures" / "labelled_edits.json"

#: Minimum fraction of the labelled sample the classifier must get right.
ACCURACY_FLOOR = 0.85


def load_sample():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["labelled"]


def to_diff(item) -> RevisionDiff:
    """Rebuild a RevisionDiff carrying the fixture's recorded signals."""
    return RevisionDiff(
        revid=item["revid"],
        parentid=0,
        user="someone",
        timestamp="2002-01-01T00:00:00Z",
        minor=item["minor"],
        anon=False,
        comment=item["comment"],
        added=["w"] * item["words_added"],
        removed=["w"] * item["words_removed"],
    )


def test_fixture_is_wellformed():
    sample = load_sample()
    assert len(sample) >= 20
    assert all(item["label"] in ("additive", "maintenance") for item in sample)
    # ground truth should contain both classes in non-trivial proportion
    additive = sum(1 for item in sample if item["label"] == "additive")
    assert 0.2 <= additive / len(sample) <= 0.8


def test_classifier_accuracy_on_labelled_real_edits():
    sample = load_sample()
    wrong = []
    for item in sample:
        c = classify_edit(to_diff(item), identity_revert=item["identity_revert"])
        if c.edit_type.value != item["label"]:
            wrong.append((item["revid"], item["label"], c.edit_type.value, c.reason))

    accuracy = 1 - len(wrong) / len(sample)
    assert accuracy >= ACCURACY_FLOOR, (
        f"accuracy {accuracy:.2f} below floor {ACCURACY_FLOOR}; "
        f"misclassified: {wrong}"
    )


def test_hash_detected_reverts_are_never_missed():
    """The two unlabelled real reverts must classify as maintenance.

    These carry no rv keyword and (in one case) no comment at all — exactly
    the cases hash detection exists for, so they are asserted individually
    rather than left to the aggregate accuracy floor.
    """
    for item in load_sample():
        if item["identity_revert"]:
            c = classify_edit(to_diff(item), identity_revert=True)
            assert c.edit_type.value == "maintenance"
            assert c.reason == "identity-revert"
