"""Tests for the caching data-access layer."""

import pytest

from wikicontrib.api import RawRevision, WikiAPIError
from wikicontrib.cache import RevisionCache
from wikicontrib.store import RevisionStore

API = "https://en.wikipedia.org/w/api.php"


def _rev(revid, user="Alice"):
    return RawRevision(
        revid=revid,
        parentid=revid - 1,
        timestamp=f"2020-01-{revid:02d}T00:00:00Z",
        user=user,
        userid=1,
        comment="edit",
        size=100,
        minor=False,
        anon=False,
    )


class FakeClient:
    """Records every fetch so we can assert the cache prevents re-fetching."""

    api_url = API

    def __init__(self, pages):
        self.pages = pages  # title -> list[RawRevision] (or WikiAPIError)
        self.fetches = []

    def fetch_revisions(self, title, *, max_revisions=500, include_content=False):
        self.fetches.append(title)
        result = self.pages.get(title)
        if result is None:
            raise WikiAPIError(f"page not found: {title!r}")
        if max_revisions is None:
            return list(result)
        return list(result[:max_revisions])


def make_store(tmp_path, pages):
    client = FakeClient(pages)
    return RevisionStore(client=client, cache=RevisionCache(tmp_path)), client


def test_fetches_then_serves_second_call_from_cache(tmp_path):
    store, client = make_store(tmp_path, {"X": [_rev(1), _rev(2)]})
    first = store.get_revisions("X", max_revisions=10)
    second = store.get_revisions("X", max_revisions=10)
    assert [r.revid for r in first] == [1, 2]
    assert [r.revid for r in second] == [1, 2]
    assert client.fetches == ["X"]  # only one network call


def test_refresh_bypasses_cache(tmp_path):
    store, client = make_store(tmp_path, {"X": [_rev(1)]})
    store.get_revisions("X", max_revisions=10)
    store.get_revisions("X", max_revisions=10, refresh=True)
    assert client.fetches == ["X", "X"]


def test_short_result_marks_history_complete_so_larger_request_hits_cache(tmp_path):
    # Only 2 revisions exist but we allowed 10 -> the history is complete, so a
    # later uncapped request must not trigger another fetch.
    store, client = make_store(tmp_path, {"X": [_rev(1), _rev(2)]})
    store.get_revisions("X", max_revisions=10)
    store.get_revisions("X", max_revisions=None)
    assert client.fetches == ["X"]


def test_capped_result_refetches_when_more_requested(tmp_path):
    store, client = make_store(tmp_path, {"X": [_rev(i) for i in range(1, 6)]})
    store.get_revisions("X", max_revisions=2)  # hit the cap; may be incomplete
    store.get_revisions("X", max_revisions=5)
    assert client.fetches == ["X", "X"]


def test_missing_page_raises_by_default(tmp_path):
    store, _ = make_store(tmp_path, {})
    with pytest.raises(WikiAPIError):
        store.get_revisions("Nope")


def test_missing_talk_page_returns_empty(tmp_path):
    store, _ = make_store(tmp_path, {"X": [_rev(1)]})
    assert store.get_talk_revisions("X") == []


def test_get_talk_revisions_uses_talk_namespace(tmp_path):
    store, client = make_store(tmp_path, {"Talk:X": [_rev(1)]})
    revs = store.get_talk_revisions("X")
    assert [r.revid for r in revs] == [1]
    assert client.fetches == ["Talk:X"]


def test_get_page_history_pairs_article_and_talk(tmp_path):
    pages = {"X": [_rev(1), _rev(2, user="Bob")], "Talk:X": [_rev(3, user="Carol")]}
    store, _ = make_store(tmp_path, pages)
    history = store.get_page_history("X")
    assert history.title == "X"
    assert history.talk_title == "Talk:X"
    assert [r.revid for r in history.revisions] == [1, 2]
    assert [r.revid for r in history.talk_revisions] == [3]
    assert history.has_talk is True
    assert history.editors == {"Alice", "Bob"}
    assert history.talk_participants == {"Carol"}


def test_page_history_without_talk(tmp_path):
    store, _ = make_store(tmp_path, {"X": [_rev(1)]})
    history = store.get_page_history("X")
    assert history.has_talk is False
    assert history.talk_participants == set()
