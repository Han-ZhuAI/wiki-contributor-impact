"""Content persistence — did a contributor's text survive?

Volume counts what someone *added*; persistence asks whether it *lasted*.
The two come apart sharply and meaningfully:

* a vandal who inserts 500 words that are reverted minutes later has high
  volume and zero persistence;
* an editor who writes one careful sentence that is still in the article years
  later has tiny volume but perfect persistence.

Persistence is the closest thing in the edit history to a measure of *accepted*
contribution — text the collaborative process kept — which is exactly the kind
of impact the assignment wants to surface beyond raw activity.

Method — token provenance (a simplified WikiWho)
------------------------------------------------
Walking the history oldest-first, the article is held as a list of tokens each
tagged with the user who introduced it. For each new revision we align the old
and new token sequences (:class:`difflib.SequenceMatcher`):

* tokens present in both keep their **original** author (they survived);
* tokens only in the new revision are **introduced** by the current editor,
  unless an exact revision revert or a substantial deleted span proves they
  were restored;
* tokens only in the old revision were **removed**.

After the whole history is processed, each author's *surviving* tokens are the
ones still present in the final revision. ``survival_rate`` is the fraction of
what they introduced that lived to the end.

Exact reverts restore the saved author map of the earlier revision. Deleted
token spans also retain their author maps for conservative partial-restoration
detection. This matters because restoring an older revision is maintenance
work, not authorship of every restored word.

Counts are over **word** tokens only (markup/punctuation excluded), keeping
persistence directly comparable with the volume metrics. Reference:
https://www.wikiwho.net/ — this is a lightweight approximation, not that model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .api import RawRevision
from .metrics import HIDDEN_AUTHOR
from .reverts import find_identity_reverts
from .tokenize import is_word, tokenize

# Partial restoration is inherently ambiguous for very short spans: an editor
# may independently add the same common word that someone removed years ago.
# Exact full-revision reverts are handled separately and have no length limit.
MIN_RESTORED_SPAN_WORDS = 3


@dataclass
class ContributorPersistence:
    """How much of one contributor's introduced text survived to the end."""

    user: str
    words_introduced: int = 0
    words_surviving: int = 0

    @property
    def survival_rate(self) -> float:
        """Fraction of introduced words still present in the final revision.

        Undefined for a contributor who introduced no words; reported as 0.0.
        """
        if self.words_introduced == 0:
            return 0.0
        return self.words_surviving / self.words_introduced


@dataclass
class PersistenceReport:
    """Persistence metrics for every contributor to an article."""

    contributors: dict[str, ContributorPersistence] = field(default_factory=dict)
    final_word_count: int = 0

    def share_of_surviving(self, user: str) -> float:
        """Fraction of the final article's words authored by ``user``."""
        if not self.final_word_count or user not in self.contributors:
            return 0.0
        return self.contributors[user].words_surviving / self.final_word_count

    def ranked(self, by: str = "words_surviving") -> list[ContributorPersistence]:
        """Contributors sorted high-to-low by ``by`` (ties broken by name)."""
        return sorted(
            self.contributors.values(),
            key=lambda c: (-getattr(c, by), c.user),
        )


def track_persistence(revisions: list[RawRevision]) -> PersistenceReport:
    """Track token provenance across a history and report survival per author.

    ``revisions`` must be chronological (oldest first) and carry content
    (fetch with ``include_content=True``).
    """
    report = PersistenceReport()

    def contributor(user: str | None) -> ContributorPersistence:
        name = user or HIDDEN_AUTHOR
        c = report.contributors.get(name)
        if c is None:
            c = ContributorPersistence(user=name)
            report.contributors[name] = c
        return c

    old_tokens: list[str] = []
    old_authors: list[str] = []
    identity_reverts = find_identity_reverts(revisions)
    restore_targets = set(identity_reverts.values())
    provenance_snapshots: dict[int, list[str]] = {}
    # Exact deleted spans support partial restoration and simple text moves.
    # Keep the first attribution observed for deterministic original authorship.
    deleted_span_authors: dict[tuple[str, ...], list[str]] = {}

    for rev in revisions:
        author = rev.user or HIDDEN_AUTHOR
        new_tokens = tokenize(rev.content)
        restored_revid = identity_reverts.get(rev.revid)

        if restored_revid is not None:
            # Exact content identity is strong evidence: restore the complete
            # provenance snapshot even when only one word changed in between.
            new_authors = list(provenance_snapshots[restored_revid])
        else:
            new_authors = [author] * len(new_tokens)
            matcher = SequenceMatcher(a=old_tokens, b=new_tokens, autojunk=False)
            opcodes = matcher.get_opcodes()

            # Record every removed span before processing insertions. A moved
            # span may be inserted earlier than its deletion opcode appears.
            for tag, i1, i2, _j1, _j2 in opcodes:
                if tag not in ("delete", "replace") or i1 == i2:
                    continue
                span = tuple(old_tokens[i1:i2])
                if span:
                    deleted_span_authors.setdefault(
                        span, list(old_authors[i1:i2])
                    )

            for tag, i1, i2, j1, j2 in opcodes:
                if tag == "equal":
                    # Surviving tokens keep whoever first introduced them.
                    new_authors[j1:j2] = old_authors[i1:i2]
                elif tag in ("insert", "replace"):
                    span = tuple(new_tokens[j1:j2])
                    restored_authors = deleted_span_authors.get(span)
                    restored_word_count = sum(1 for t in span if is_word(t))
                    if (
                        restored_authors is not None
                        and restored_word_count >= MIN_RESTORED_SPAN_WORDS
                    ):
                        new_authors[j1:j2] = restored_authors
                    else:
                        # Short/novel spans belong to the current editor.
                        contributor(author).words_introduced += restored_word_count

        old_tokens, old_authors = new_tokens, new_authors
        if rev.revid in restore_targets:
            provenance_snapshots[rev.revid] = list(new_authors)

    # Tally what remains in the final revision.
    for token, author in zip(old_tokens, old_authors):
        if is_word(token):
            contributor(author).words_surviving += 1
            report.final_word_count += 1

    return report
