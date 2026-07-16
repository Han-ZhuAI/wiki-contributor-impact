"""On-disk cache for fetched revision histories.

Revision histories are large, slow to download and — for any revision that is
already in the past — **immutable**. Re-fetching them on every run would be
both wasteful and impolite to Wikipedia's servers, and it would make the
metrics work in later stages painfully slow to iterate on.

This module stores each fetched history as a JSON file under ``data/`` so a
history is pulled from the network at most once.

Cache validity
--------------
A history is fetched under a ``max_revisions`` cap, so a cached entry does not
automatically satisfy every later request. Each entry therefore records:

* ``complete`` — whether the *entire* history was fetched (no cap hit), in
  which case the entry can serve any request; and
* ``count`` — how many revisions were stored, so a request for fewer
  revisions can be served by slicing.

A request for *more* revisions than a capped entry holds is a cache miss.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .api import RawRevision

DEFAULT_CACHE_DIR = Path("data")
CACHE_FORMAT_VERSION = 1


def _slug(title: str) -> str:
    """A short, filesystem-safe hint of the title (readability only)."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower()
    return slug[:40] or "page"


class RevisionCache:
    """Stores and retrieves revision histories as JSON files on disk."""

    def __init__(self, root: Path | str = DEFAULT_CACHE_DIR) -> None:
        self.root = Path(root)

    # -- key/paths -----------------------------------------------------------

    def _key(self, title: str, api_url: str, include_content: bool) -> str:
        raw = f"{api_url}|{title}|content={include_content}"
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
        return f"{_slug(title)}-{'full' if include_content else 'meta'}-{digest}"

    def path_for(self, title: str, api_url: str, include_content: bool) -> Path:
        return self.root / f"{self._key(title, api_url, include_content)}.json"

    # -- read/write ----------------------------------------------------------

    def load(
        self,
        title: str,
        *,
        api_url: str,
        include_content: bool = False,
        max_revisions: int | None = None,
    ) -> list[RawRevision] | None:
        """Return cached revisions, or ``None`` on a miss.

        A miss occurs when nothing is cached, the file is unreadable/stale, or
        the entry holds too few revisions to satisfy ``max_revisions``.
        """
        path = self.path_for(title, api_url, include_content)
        if not path.exists():
            return None

        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None  # corrupt cache behaves as a miss, never as an error

        if entry.get("format") != CACHE_FORMAT_VERSION:
            return None

        if not self._satisfies(entry, max_revisions):
            return None

        revisions = [RawRevision(**rev) for rev in entry["revisions"]]
        if max_revisions is not None:
            revisions = revisions[:max_revisions]
        return revisions

    @staticmethod
    def _satisfies(entry: dict, max_revisions: int | None) -> bool:
        """Can this entry answer a request for ``max_revisions`` revisions?"""
        if entry.get("complete"):
            return True  # the whole history is here; any request is answerable
        if max_revisions is None:
            return False  # caller wants everything, we only have a capped slice
        return int(entry.get("count", 0)) >= max_revisions

    def save(
        self,
        title: str,
        revisions: list[RawRevision],
        *,
        api_url: str,
        include_content: bool = False,
        complete: bool,
    ) -> Path:
        """Write ``revisions`` to the cache and return the file path."""
        path = self.path_for(title, api_url, include_content)
        path.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "format": CACHE_FORMAT_VERSION,
            "title": title,
            "api_url": api_url,
            "include_content": include_content,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "complete": complete,
            "count": len(revisions),
            "revisions": [asdict(rev) for rev in revisions],
        }
        # Write via a temp file so an interrupted run cannot leave a half-written
        # cache entry behind.
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        return path
