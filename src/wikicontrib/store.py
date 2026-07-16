"""The data-access layer the rest of the model talks to.

:mod:`api` knows how to fetch, :mod:`cache` knows how to persist and
:mod:`titles` knows how pages are paired. This module composes the three into
one interface so the metric code can simply ask for "the history of this
article and its talk page" and never think about HTTP, caching or namespaces.

Fetching an article always implies its talk page, because the model treats a
wiki entry as the pair *(content, discussion)*: the article records what was
written, the talk page records how it was argued for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .api import DEFAULT_API_URL, MediaWikiClient, RawRevision, WikiAPIError
from .cache import RevisionCache
from .titles import talk_title


@dataclass
class PageHistory:
    """The full collaborative record of one wiki entry."""

    title: str
    revisions: list[RawRevision] = field(default_factory=list)
    talk_title: str = ""
    talk_revisions: list[RawRevision] = field(default_factory=list)

    @property
    def has_talk(self) -> bool:
        return bool(self.talk_revisions)

    @property
    def editors(self) -> set[str]:
        """Distinct named/IP editors of the article body."""
        return {r.user for r in self.revisions if r.user}

    @property
    def talk_participants(self) -> set[str]:
        """Distinct contributors to the discussion."""
        return {r.user for r in self.talk_revisions if r.user}


class RevisionStore:
    """Fetches revision histories, transparently backed by the disk cache."""

    def __init__(
        self,
        client: MediaWikiClient | None = None,
        cache: RevisionCache | None = None,
        *,
        cache_dir: Path | str | None = None,
    ) -> None:
        self.client = client or MediaWikiClient()
        if cache is not None:
            self.cache = cache
        else:
            self.cache = RevisionCache(cache_dir) if cache_dir else RevisionCache()

    @property
    def api_url(self) -> str:
        return getattr(self.client, "api_url", DEFAULT_API_URL)

    def get_revisions(
        self,
        title: str,
        *,
        max_revisions: int | None = 500,
        include_content: bool = False,
        refresh: bool = False,
        missing_ok: bool = False,
    ) -> list[RawRevision]:
        """Return the revision history of ``title``, oldest first.

        Served from the cache when possible; otherwise fetched and cached.

        Parameters
        ----------
        refresh:
            Bypass the cache and re-fetch from the API.
        missing_ok:
            Return ``[]`` instead of raising when the page does not exist.
            Used for talk pages, which many articles simply do not have.
        """
        if not refresh:
            cached = self.cache.load(
                title,
                api_url=self.api_url,
                include_content=include_content,
                max_revisions=max_revisions,
            )
            if cached is not None:
                return cached

        try:
            revisions = self.client.fetch_revisions(
                title, max_revisions=max_revisions, include_content=include_content
            )
        except WikiAPIError:
            if missing_ok:
                return []
            raise

        # If the API returned fewer revisions than we allowed, we necessarily
        # reached the end of the history — so this entry can serve any future
        # request, not just ones capped at the same number.
        complete = max_revisions is None or len(revisions) < max_revisions

        self.cache.save(
            title,
            revisions,
            api_url=self.api_url,
            include_content=include_content,
            complete=complete,
        )
        return revisions

    def get_talk_revisions(
        self,
        title: str,
        *,
        max_revisions: int | None = 500,
        include_content: bool = False,
        refresh: bool = False,
    ) -> list[RawRevision]:
        """Return the history of ``title``'s talk page (``[]`` if it has none)."""
        return self.get_revisions(
            talk_title(title),
            max_revisions=max_revisions,
            include_content=include_content,
            refresh=refresh,
            missing_ok=True,
        )

    def get_page_history(
        self,
        title: str,
        *,
        max_revisions: int | None = 500,
        include_content: bool = False,
        refresh: bool = False,
    ) -> PageHistory:
        """Return the article history together with its discussion history."""
        revisions = self.get_revisions(
            title,
            max_revisions=max_revisions,
            include_content=include_content,
            refresh=refresh,
        )
        talk_revisions = self.get_talk_revisions(
            title,
            max_revisions=max_revisions,
            include_content=include_content,
            refresh=refresh,
        )
        return PageHistory(
            title=title,
            revisions=revisions,
            talk_title=talk_title(title),
            talk_revisions=talk_revisions,
        )
