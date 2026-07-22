"""Detecting reverts from content, not comments.

The Day-6 classifier spots reverts only when the editor *says* "rv" in the
edit summary. Plenty of reverts carry no summary at all — vandals are rarely
courteous, and neither are the people cleaning up after them in a hurry.

The reliable signal is in the content itself: a revert restores the page to a
state it has already been in, so its full text is **byte-identical to an
earlier revision**. Hashing every revision's content and looking for repeats
finds these *identity reverts* regardless of what the summary says.

Distinctions that matter here:

* A revision identical to its **immediate parent** is a *null edit* (nothing
  changed) — not a revert, and it is excluded.
* A revision identical to an **older ancestor** restored that state: the edits
  in between were undone. That is the revert.
* Hashing is exact by design. A "partial revert" that also tweaks a word will
  not match; catching those is the comment-regex's job, and the two detectors
  are complementary.
"""

from __future__ import annotations

import hashlib

from .api import RawRevision


def _content_hash(text: str | None) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def find_identity_reverts(revisions: list[RawRevision]) -> dict[int, int]:
    """Map each reverting revision to the revision whose state it restored.

    ``revisions`` must be chronological (oldest first) and carry content.
    Returns ``{reverting_revid: restored_revid}``. Null edits (identical to
    the immediate parent) are not reverts and are omitted.

    When the same state appears several times (revert wars), every later
    occurrence maps back to the *first* revision that had that content.
    """
    first_seen: dict[str, int] = {}
    reverts: dict[int, int] = {}
    previous_hash: str | None = None

    for rev in revisions:
        h = _content_hash(rev.content)
        if h == previous_hash:
            pass  # null edit: nothing changed, nothing was restored
        elif h in first_seen:
            reverts[rev.revid] = first_seen[h]
        if h not in first_seen:
            first_seen[h] = rev.revid
        previous_hash = h

    return reverts


def reverted_revids(
    revisions: list[RawRevision], identity_reverts: dict[int, int] | None = None
) -> set[int]:
    """Revids of edits that were later undone by an identity revert.

    For each revert, the undone edits are those strictly between the restored
    revision and the reverting revision. Knowing whose work was thrown away
    matters later for persistence: text that never survived should not score.
    """
    if identity_reverts is None:
        identity_reverts = find_identity_reverts(revisions)
    if not identity_reverts:
        return set()

    order = {rev.revid: i for i, rev in enumerate(revisions)}
    undone: set[int] = set()
    for reverting, restored in identity_reverts.items():
        lo, hi = order[restored], order[reverting]
        for rev in revisions[lo + 1 : hi]:
            undone.add(rev.revid)
    return undone
