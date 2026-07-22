"""Per-contributor metrics aggregated from a revision history.

The diff engine (:mod:`wikicontrib.diff`) tells us what each *edit* did. This
module rolls those per-edit facts up to the *contributor* level, which is the
unit the assignment asks us to differentiate.

This first stage covers the **volume** dimension — how much text each person
contributed. The additive-vs-maintenance split, persistence and discussion
impact are layered on in later stages of the schedule, but they all aggregate
the same way, so the machinery here is deliberately reusable.

Why several volume numbers, not one
-----------------------------------
A single "words added" figure hides as much as it shows. The model keeps a
small family of volume measures so contributors with genuinely different
behaviour do not collapse to the same score:

* ``words_added`` — gross new words introduced (the headline volume figure);
* ``words_removed`` — words taken out (a deleter is not a writer);
* ``net_words`` — the two combined: the contributor's lasting footprint on
  article length;
* ``gross_words`` — total words touched, the amount of *work* done regardless
  of direction, so a heavy rewriter is not scored as idle;
* ``edits`` — how many revisions, which separates one big contribution from
  the same volume spread over sustained involvement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .api import RawRevision
from .classify import ClassifierConfig, EditType, classify_edit
from .diff import RevisionDiff, diff_history
from .reverts import find_identity_reverts

#: Label used for edits whose author has been suppressed/hidden by the API.
HIDDEN_AUTHOR = "(hidden)"


@dataclass
class ContributorVolume:
    """Volume metrics for a single contributor on one article."""

    user: str
    edits: int = 0
    minor_edits: int = 0
    anon: bool = False
    words_added: int = 0
    words_removed: int = 0
    additive_edits: int = 0
    maintenance_edits: int = 0
    additive_words: int = 0
    first_edit: str = ""
    last_edit: str = ""

    @property
    def net_words(self) -> int:
        """Lasting footprint on article length (added minus removed)."""
        return self.words_added - self.words_removed

    @property
    def gross_words(self) -> int:
        """Total words touched, regardless of direction — the work done."""
        return self.words_added + self.words_removed

    @property
    def avg_words_per_edit(self) -> float:
        """Mean gross words per edit; 0 for a contributor with no edits."""
        return self.gross_words / self.edits if self.edits else 0.0

    @property
    def maintenance_ratio(self) -> float:
        """Fraction of this contributor's edits that were maintenance (0.0–1.0).

        This is the per-contributor form of the additive-vs-maintenance
        distinction: a content author sits near 0, a gnome/vandal-fighter near
        1. Undefined for someone with no edits, reported as 0.0.
        """
        return self.maintenance_edits / self.edits if self.edits else 0.0

    def _accumulate(self, diff: RevisionDiff, edit_type: EditType) -> None:
        self.edits += 1
        if diff.minor:
            self.minor_edits += 1
        self.words_added += diff.words_added
        self.words_removed += diff.words_removed
        if edit_type.is_additive:
            self.additive_edits += 1
            self.additive_words += diff.words_added
        else:
            self.maintenance_edits += 1
        if not self.first_edit or diff.timestamp < self.first_edit:
            self.first_edit = diff.timestamp
        if diff.timestamp > self.last_edit:
            self.last_edit = diff.timestamp


@dataclass
class VolumeReport:
    """Volume metrics for every contributor to an article."""

    contributors: dict[str, ContributorVolume] = field(default_factory=dict)

    @property
    def total_words_added(self) -> int:
        return sum(c.words_added for c in self.contributors.values())

    def share_of_added(self, user: str) -> float:
        """Fraction of all added words contributed by ``user`` (0.0–1.0)."""
        total = self.total_words_added
        if not total or user not in self.contributors:
            return 0.0
        return self.contributors[user].words_added / total

    def ranked(self, by: str = "net_words") -> list[ContributorVolume]:
        """Contributors sorted high-to-low by attribute/metric ``by``.

        ``by`` may name any numeric field or property of
        :class:`ContributorVolume` (e.g. ``"words_added"``, ``"net_words"``,
        ``"gross_words"``, ``"edits"``). Ties break alphabetically by user so
        the ordering is deterministic.
        """
        def key(c: ContributorVolume):
            value = getattr(c, by)
            return (-value, c.user)

        return sorted(self.contributors.values(), key=key)


def aggregate_volume(
    diffs: list[RevisionDiff],
    config: ClassifierConfig | None = None,
    identity_reverts: set[int] | None = None,
) -> VolumeReport:
    """Aggregate per-edit diffs into per-contributor volume metrics.

    Each edit is also classified (additive vs. maintenance) so the per-
    contributor additive/maintenance split is available alongside raw volume.
    ``identity_reverts`` holds revids proven to be reverts by content hashing
    (:mod:`wikicontrib.reverts`); those classify as maintenance regardless of
    their summaries.

    Empty edits (null edits, whitespace-only, pure markup churn that touched no
    words) still count towards a contributor's ``edits`` tally — they happened —
    but naturally add nothing to the word totals.
    """
    revert_ids = identity_reverts or set()
    report = VolumeReport()
    for diff in diffs:
        user = diff.user or HIDDEN_AUTHOR
        contributor = report.contributors.get(user)
        if contributor is None:
            contributor = ContributorVolume(user=user, anon=diff.anon)
            report.contributors[user] = contributor
        classification = classify_edit(
            diff, config, identity_revert=diff.revid in revert_ids
        )
        contributor._accumulate(diff, classification.edit_type)
    return report


def aggregate_history(
    revisions: list[RawRevision], config: ClassifierConfig | None = None
) -> VolumeReport:
    """Full pipeline: revisions (with content) -> diffs -> reverts -> report.

    Convenience entry point wiring together the diff engine, hash-based revert
    detection and per-contributor aggregation in one call.
    """
    diffs = diff_history(revisions)
    identity_reverts = set(find_identity_reverts(revisions))
    return aggregate_volume(diffs, config, identity_reverts)
