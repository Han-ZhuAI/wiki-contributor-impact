"""Tests for transparent automated-account evidence and filtering policy."""

from wikicontrib.api import RawRevision
from wikicontrib.automation import detect_automation_candidates


def _revision(revid: int, user: str, comment: str = "") -> RawRevision:
    return RawRevision(
        revid=revid,
        parentid=revid - 1,
        timestamp="2020-01-01T00:00:00Z",
        user=user,
        userid=1,
        comment=comment,
        size=10,
        minor=False,
        anon=False,
        content="text",
    )


def test_username_markers_are_high_confidence_exclusion_candidates():
    report = detect_automation_candidates(
        [
            _revision(1, "Conversion script", "Automated conversion"),
            _revision(2, "The Anomebot"),
            _revision(3, "Alice"),
        ]
    )

    assert report.candidate_users == ("Conversion script", "The Anomebot")
    assert report.exclusion_candidates == ("Conversion script", "The Anomebot")
    assert all(candidate.confidence == "high" for candidate in report.candidates)
    assert report.candidates[0].evidence_revision_ids == (1,)


def test_comment_only_signal_is_review_only_and_not_excluded():
    report = detect_automation_candidates(
        [_revision(1, "Human editor", "Revert bot edits")]
    )

    assert report.candidate_users == ("Human editor",)
    assert report.exclusion_candidates == ()
    assert report.candidates[0].confidence == "review"
    assert report.candidates[0].eligible_for_exclusion is False


def test_talk_revisions_are_checked_and_evidence_is_deduplicated():
    report = detect_automation_candidates(
        [_revision(1, "Alice")],
        [
            _revision(10, "HelperBot", "automated"),
            _revision(11, "HelperBot", "using a script"),
        ],
    )

    candidate = report.candidates[0]
    assert candidate.user == "HelperBot"
    assert candidate.evidence_revision_ids == (10, 11)
    assert set(candidate.reasons) == {
        "explicit_automation_comment",
        "username_bot_marker",
    }
    assert report.as_dict()["history_treatment"].startswith("all revisions remain")
