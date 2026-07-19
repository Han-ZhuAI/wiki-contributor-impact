"""Word-level diffing between consecutive revisions.

This is the analytical core the metrics are built on. Given two consecutive
states of an article, it answers: *which tokens did this edit add, and which
did it remove?* From that one answer the model derives all three dimensions the
assignment asks about:

* **volume** — how many words a contributor added;
* **additive vs. maintenance** — an edit that mostly *adds* tokens is growing
  the article, while one that removes and replaces in equal measure is
  maintaining it (see :attr:`RevisionDiff.churn`);
* **persistence** — the added tokens are the units later revisions are checked
  against to see whether the contribution survived.

Why diff tokens rather than bytes
---------------------------------
The API reports each revision's byte ``size``, and the naive metric is
``size - parent_size``. That figure cannot distinguish *replacing* a
200-character paragraph with a different 200-character paragraph (net zero,
substantial work) from *no edit at all* (also net zero). Token diffing sees
both the removal and the addition, so rewrites are measured rather than
cancelling out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .api import RawRevision
from .tokenize import is_word, tokenize


@dataclass
class RevisionDiff:
    """What one revision changed, relative to its predecessor."""

    revid: int
    parentid: int
    user: str | None
    timestamp: str
    minor: bool
    anon: bool
    comment: str = ""
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    # -- counts ---------------------------------------------------------------

    @property
    def words_added(self) -> int:
        """Word tokens added (markup and punctuation excluded)."""
        return sum(1 for t in self.added if is_word(t))

    @property
    def words_removed(self) -> int:
        return sum(1 for t in self.removed if is_word(t))

    @property
    def net_words(self) -> int:
        """Growth this edit caused. Negative for net deletions."""
        return self.words_added - self.words_removed

    @property
    def gross_words(self) -> int:
        """Total word churn — how much text the editor actually touched.

        A rewrite scores highly here while scoring ~0 on :attr:`net_words`,
        which is exactly the distinction byte-delta metrics miss.
        """
        return self.words_added + self.words_removed

    @property
    def is_empty(self) -> bool:
        """True if nothing changed (e.g. a null edit)."""
        return not self.added and not self.removed

    @property
    def churn(self) -> float:
        """How far this edit *replaced* text rather than only adding or removing.

        ``1.0`` — every touched word was swapped for another (a rewrite).
        ``0.0`` — the edit moved in one direction only.

        Note that **pure insertion and pure deletion both score 0**: churn
        measures overlap between the two sides, not direction. Direction comes
        from :attr:`net_words`, and the Day-6 classifier needs *both* signals:

        =================  =====  ==========  ==========================
        edit               churn  net_words   reads as
        =================  =====  ==========  ==========================
        writes new prose     ~0        > 0    additive
        trims/reverts        ~0        < 0    maintenance
        copy-edit/rewrite    ~1        ~ 0    maintenance
        expands and edits   mid        > 0    mixed
        =================  =====  ==========  ==========================
        """
        if self.gross_words == 0:
            return 0.0
        return 2 * min(self.words_added, self.words_removed) / self.gross_words


def diff_tokens(before: list[str], after: list[str]) -> tuple[list[str], list[str]]:
    """Return ``(added, removed)`` tokens transforming ``before`` into ``after``.

    Unchanged tokens are reported in neither list.

    >>> diff_tokens(["a", "b"], ["a", "c"])
    (['c'], ['b'])
    """
    added: list[str] = []
    removed: list[str] = []
    # autojunk heuristically ignores tokens appearing in >1% of a long sequence,
    # which for wikitext means common words like "the" — disastrous for our
    # counts, so it must stay off.
    matcher = SequenceMatcher(a=before, b=after, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            removed.extend(before[i1:i2])
        if tag in ("replace", "insert"):
            added.extend(after[j1:j2])
    return added, removed


def diff_revision(
    revision: RawRevision, previous_text: str | None
) -> RevisionDiff:
    """Diff one revision against the text that preceded it."""
    before = tokenize(previous_text)
    after = tokenize(revision.content)
    added, removed = diff_tokens(before, after)
    return RevisionDiff(
        revid=revision.revid,
        parentid=revision.parentid,
        user=revision.user,
        timestamp=revision.timestamp,
        minor=revision.minor,
        anon=revision.anon,
        comment=revision.comment,
        added=added,
        removed=removed,
    )


def diff_history(revisions: list[RawRevision]) -> list[RevisionDiff]:
    """Diff each revision in a chronological history against its predecessor.

    ``revisions`` must be oldest-first (as :mod:`wikicontrib.store` returns
    them) and must carry content — fetch with ``include_content=True``.

    The first revision is diffed against empty text, so the page's creator is
    correctly credited with everything the article started with.
    """
    diffs: list[RevisionDiff] = []
    previous_text: str | None = None
    for revision in revisions:
        diffs.append(diff_revision(revision, previous_text))
        previous_text = revision.content
    return diffs
