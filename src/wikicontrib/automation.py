"""Auditable detection of accounts that may represent automated editing.

Automation is not inherently low-impact, and a username heuristic cannot prove
that an account is a bot.  This module therefore separates high-confidence
username markers, which may be excluded from a human-contributor ranking on an
opt-in basis, from weaker edit-comment evidence that only requests review.

Detection never removes revisions from the history.  Keeping every revision in
the diff and provenance chain preserves the article state that later editors
actually saw; only the final ranking can omit selected accounts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .api import RawRevision

_BOT_USERNAME_RE = re.compile(r"(?:^|[\s_-])bot(?:$|[\s_-])|bot$", re.IGNORECASE)
_SCRIPT_USERNAME_RE = re.compile(r"(?:^|[\s_-])script(?:$|[\s_-])", re.IGNORECASE)
_AUTOMATED_COMMENT_RE = re.compile(
    r"\b(?:automated|automatic(?:ally)?|scripted|using (?:a )?script)\b",
    re.IGNORECASE,
)
_BOT_COMMENT_RE = re.compile(r"\bbot(?:-assisted)?\b", re.IGNORECASE)


@dataclass(frozen=True)
class AutomationCandidate:
    """Evidence that one observed account may represent automated editing."""

    user: str
    confidence: str
    reasons: tuple[str, ...]
    evidence_revision_ids: tuple[int, ...]

    @property
    def eligible_for_exclusion(self) -> bool:
        """Whether an explicit automated-account filter may omit this user."""
        return self.confidence == "high"

    def as_dict(self) -> dict:
        return {
            "user": self.user,
            "confidence": self.confidence,
            "eligible_for_exclusion": self.eligible_for_exclusion,
            "reasons": list(self.reasons),
            "evidence_revision_ids": list(self.evidence_revision_ids),
        }


@dataclass(frozen=True)
class AutomationReport:
    """Deterministic automation candidates and the policy derived from them."""

    candidates: tuple[AutomationCandidate, ...] = ()

    @property
    def candidate_users(self) -> tuple[str, ...]:
        return tuple(candidate.user for candidate in self.candidates)

    @property
    def exclusion_candidates(self) -> tuple[str, ...]:
        """High-confidence candidates safe for explicit ranking comparison."""
        return tuple(
            candidate.user
            for candidate in self.candidates
            if candidate.eligible_for_exclusion
        )

    def as_dict(self) -> dict:
        return {
            "policy": (
                "high-confidence username markers may be excluded from ranking; "
                "comment-only candidates remain review-only"
            ),
            "history_treatment": (
                "all revisions remain in diff and provenance calculations"
            ),
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "exclusion_candidates": list(self.exclusion_candidates),
        }


def detect_automation_candidates(
    article_revisions: list[RawRevision],
    talk_revisions: list[RawRevision] | None = None,
) -> AutomationReport:
    """Find transparent automation signals in article and Talk histories.

    Username markers provide the high-confidence tier.  An edit comment by
    itself is weaker because a human editor may merely mention a bot, so those
    candidates are surfaced for review but are not automatically eligible for
    ranking exclusion.
    """
    reasons_by_user: dict[str, set[str]] = {}
    revision_ids_by_user: dict[str, set[int]] = {}
    username_signal_users: set[str] = set()

    for revision in [*article_revisions, *(talk_revisions or [])]:
        if not revision.user:
            continue
        reasons: set[str] = set()
        if _BOT_USERNAME_RE.search(revision.user):
            reasons.add("username_bot_marker")
            username_signal_users.add(revision.user)
        if _SCRIPT_USERNAME_RE.search(revision.user):
            reasons.add("username_script_marker")
            username_signal_users.add(revision.user)
        if _AUTOMATED_COMMENT_RE.search(revision.comment):
            reasons.add("explicit_automation_comment")
        if _BOT_COMMENT_RE.search(revision.comment):
            reasons.add("bot_mentioned_in_comment")
        if not reasons:
            continue
        reasons_by_user.setdefault(revision.user, set()).update(reasons)
        revision_ids_by_user.setdefault(revision.user, set()).add(revision.revid)

    candidates = tuple(
        AutomationCandidate(
            user=user,
            confidence="high" if user in username_signal_users else "review",
            reasons=tuple(sorted(reasons_by_user[user])),
            evidence_revision_ids=tuple(sorted(revision_ids_by_user[user])),
        )
        for user in sorted(reasons_by_user)
    )
    return AutomationReport(candidates)
