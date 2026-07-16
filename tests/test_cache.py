"""Tests for the on-disk revision cache."""

from wikicontrib.api import RawRevision
from wikicontrib.cache import RevisionCache

API = "https://en.wikipedia.org/w/api.php"


def _revs(n):
    return [
        RawRevision(
            revid=i,
            parentid=i - 1,
            timestamp=f"2020-01-{i:02d}T00:00:00Z",
            user="Alice",
            userid=1,
            comment="edit",
            size=100 + i,
            minor=False,
            anon=False,
        )
        for i in range(1, n + 1)
    ]


def test_miss_when_nothing_cached(tmp_path):
    cache = RevisionCache(tmp_path)
    assert cache.load("X", api_url=API) is None


def test_roundtrip_preserves_revisions(tmp_path):
    cache = RevisionCache(tmp_path)
    cache.save("X", _revs(3), api_url=API, complete=True)
    loaded = cache.load("X", api_url=API)
    assert [r.revid for r in loaded] == [1, 2, 3]
    assert loaded[0].user == "Alice"
    assert isinstance(loaded[0], RawRevision)


def test_complete_entry_serves_any_request(tmp_path):
    cache = RevisionCache(tmp_path)
    cache.save("X", _revs(3), api_url=API, complete=True)
    # asking for everything, or for a slice, both hit
    assert len(cache.load("X", api_url=API, max_revisions=None)) == 3
    assert len(cache.load("X", api_url=API, max_revisions=2)) == 2


def test_capped_entry_cannot_serve_request_for_everything(tmp_path):
    cache = RevisionCache(tmp_path)
    cache.save("X", _revs(3), api_url=API, complete=False)
    assert cache.load("X", api_url=API, max_revisions=None) is None


def test_capped_entry_serves_smaller_request_but_not_larger(tmp_path):
    cache = RevisionCache(tmp_path)
    cache.save("X", _revs(3), api_url=API, complete=False)
    assert len(cache.load("X", api_url=API, max_revisions=3)) == 3
    assert len(cache.load("X", api_url=API, max_revisions=2)) == 2
    assert cache.load("X", api_url=API, max_revisions=10) is None


def test_content_and_meta_entries_are_separate(tmp_path):
    cache = RevisionCache(tmp_path)
    cache.save("X", _revs(2), api_url=API, include_content=False, complete=True)
    assert cache.load("X", api_url=API, include_content=True) is None
    assert cache.load("X", api_url=API, include_content=False) is not None


def test_distinct_titles_do_not_collide(tmp_path):
    cache = RevisionCache(tmp_path)
    cache.save("X", _revs(1), api_url=API, complete=True)
    cache.save("Y", _revs(5), api_url=API, complete=True)
    assert len(cache.load("X", api_url=API)) == 1
    assert len(cache.load("Y", api_url=API)) == 5


def test_corrupt_file_is_treated_as_miss(tmp_path):
    cache = RevisionCache(tmp_path)
    path = cache.path_for("X", API, False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")
    assert cache.load("X", api_url=API) is None


def test_no_tmp_file_left_behind(tmp_path):
    cache = RevisionCache(tmp_path)
    cache.save("X", _revs(2), api_url=API, complete=True)
    assert list(tmp_path.glob("*.tmp")) == []
