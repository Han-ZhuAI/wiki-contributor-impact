"""Client for the MediaWiki Action API.

The model is data-driven: every metric ultimately derives from a page's
*revision history*, which the MediaWiki Action API exposes through the
``prop=revisions`` query. This module is responsible for one thing only —
reliably pulling that history out of the API — so the rest of the package can
work with plain Python objects and never think about HTTP.

Design notes
------------
* **Chronological order.** Revisions are fetched oldest-first (``rvdir=newer``)
  so downstream code can walk the history forward and diff consecutive states.
* **Pagination.** The API returns at most a few hundred revisions per request
  and hands back an ``rvcontinue`` token for the next page; we follow it until
  the history is exhausted or ``max_revisions`` is reached.
* **Politeness.** Wikipedia asks API clients to send a descriptive
  ``User-Agent`` and to avoid hammering the servers. We set a real UA and
  sleep a short interval between requests.

Reference: https://www.mediawiki.org/wiki/API:Revisions
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterator

import requests

from . import __version__

DEFAULT_API_URL = "https://en.wikipedia.org/w/api.php"
DEFAULT_USER_AGENT = (
    f"wikicontrib/{__version__} (contributor-impact research; "
    "https://github.com/Han-ZhuAI/wiki-contributor-impact)"
)

# Properties requested for each revision. These are the raw signals every
# downstream metric is built from.
REVISION_PROPS = "ids|timestamp|user|userid|comment|size|flags"

# The API caps rvlimit at 500 for regular users; we request the maximum so we
# make as few round-trips as possible.
API_PAGE_LIMIT = 500


class WikiAPIError(RuntimeError):
    """Raised when the MediaWiki API reports an error or a page is missing."""


@dataclass
class RawRevision:
    """A single revision as returned by the API, normalised to sane defaults.

    Optional/edge fields are handled here so the rest of the codebase never has
    to guess: anonymous edits have no ``userid`` and deleted-author revisions
    have no ``user`` at all.
    """

    revid: int
    parentid: int
    timestamp: str
    user: str | None
    userid: int | None
    comment: str
    size: int
    minor: bool
    anon: bool
    content: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, rev: dict[str, Any]) -> "RawRevision":
        # ``texthidden``/``userhidden`` etc. appear as empty-string keys when a
        # field has been suppressed; treat those as missing.
        user = rev.get("user")
        if "userhidden" in rev:
            user = None
        content = None
        slots = rev.get("slots")
        if slots and "main" in slots:
            content = slots["main"].get("content")
        elif "*" in rev:  # legacy, non-slot content shape
            content = rev["*"]
        return cls(
            revid=int(rev["revid"]),
            parentid=int(rev.get("parentid", 0)),
            timestamp=rev.get("timestamp", ""),
            user=user,
            userid=(int(rev["userid"]) if "userid" in rev and "userhidden" not in rev else None),
            comment=rev.get("comment", "") if "commenthidden" not in rev else "",
            size=int(rev.get("size", 0)),
            minor="minor" in rev,
            anon="anon" in rev,
            content=content,
        )


class MediaWikiClient:
    """A thin, polite wrapper around the MediaWiki Action API."""

    def __init__(
        self,
        api_url: str = DEFAULT_API_URL,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        min_interval: float = 0.1,
        session: requests.Session | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_url = api_url
        self.min_interval = min_interval
        self.timeout = timeout
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": user_agent})
        self._last_request_at = 0.0

    # -- low-level -----------------------------------------------------------

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        """Perform one rate-limited GET and return the parsed JSON payload."""
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

        query = {"format": "json", "formatversion": "2", **params}
        response = self._session.get(self.api_url, params=query, timeout=self.timeout)
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            info = data["error"].get("info", "unknown error")
            raise WikiAPIError(f"MediaWiki API error: {info}")
        return data

    # -- revisions -----------------------------------------------------------

    def iter_revisions(
        self,
        title: str,
        *,
        max_revisions: int | None = 500,
        include_content: bool = False,
    ) -> Iterator[RawRevision]:
        """Yield revisions of ``title`` oldest-first, following pagination.

        Parameters
        ----------
        title:
            Article title, e.g. ``"Alan Turing"``. Include the namespace prefix
            for non-article pages, e.g. ``"Talk:Alan Turing"``.
        max_revisions:
            Stop after yielding this many revisions. ``None`` means fetch the
            entire history.
        include_content:
            If true, request the full wikitext of every revision (needed for
            diffing). This is much heavier, so it is off by default.
        """
        rvprop = REVISION_PROPS + ("|content" if include_content else "")
        params: dict[str, Any] = {
            "action": "query",
            "prop": "revisions",
            "titles": title,
            "rvprop": rvprop,
            "rvlimit": API_PAGE_LIMIT,
            "rvdir": "newer",  # oldest first
            "rvslots": "main",
        }

        yielded = 0
        while True:
            if max_revisions is not None:
                remaining = max_revisions - yielded
                if remaining <= 0:
                    return
                params["rvlimit"] = min(API_PAGE_LIMIT, remaining)

            data = self._get(params)
            pages = data.get("query", {}).get("pages", [])
            if not pages:
                return
            page = pages[0]
            if page.get("missing"):
                raise WikiAPIError(f"page not found: {title!r}")

            for rev in page.get("revisions", []):
                yield RawRevision.from_api(rev)
                yielded += 1
                if max_revisions is not None and yielded >= max_revisions:
                    return

            cont = data.get("continue")
            if not cont or "rvcontinue" not in cont:
                return
            params["rvcontinue"] = cont["rvcontinue"]

    def fetch_revisions(
        self,
        title: str,
        *,
        max_revisions: int | None = 500,
        include_content: bool = False,
    ) -> list[RawRevision]:
        """Eagerly collect :meth:`iter_revisions` into a list."""
        return list(
            self.iter_revisions(
                title, max_revisions=max_revisions, include_content=include_content
            )
        )
