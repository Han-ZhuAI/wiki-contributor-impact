"""Tests for the MediaWiki API client.

These never touch the network: a ``FakeSession`` returns canned JSON payloads
so we can assert on pagination, error handling and field normalisation
deterministically.
"""

import pytest

from wikicontrib.api import MediaWikiClient, RawRevision, WikiAPIError


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeSession:
    """Replays a queued list of payloads and records the params it was called with."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(params)
        return FakeResponse(self._payloads.pop(0))


def _page(revisions, cont=None):
    payload = {"query": {"pages": [{"pageid": 1, "title": "X", "revisions": revisions}]}}
    if cont is not None:
        payload["continue"] = {"rvcontinue": cont, "continue": "||"}
    return payload


def _rev(revid, parentid=0, user="Alice", **extra):
    base = {
        "revid": revid,
        "parentid": parentid,
        "timestamp": "2020-01-01T00:00:00Z",
        "user": user,
        "userid": 42,
        "comment": "edit",
        "size": 100,
    }
    base.update(extra)
    return base


def make_client(payloads):
    session = FakeSession(payloads)
    client = MediaWikiClient(session=session, min_interval=0)
    return client, session


def test_single_page_fetch():
    client, _ = make_client([_page([_rev(1), _rev(2, parentid=1)])])
    revs = client.fetch_revisions("X")
    assert [r.revid for r in revs] == [1, 2]
    assert all(isinstance(r, RawRevision) for r in revs)


def test_follows_pagination():
    payloads = [
        _page([_rev(1)], cont="1|2"),
        _page([_rev(2, parentid=1)], cont="1|3"),
        _page([_rev(3, parentid=2)]),
    ]
    client, session = make_client(payloads)
    revs = client.fetch_revisions("X")
    assert [r.revid for r in revs] == [1, 2, 3]
    # second and third calls must carry the continuation token
    assert session.calls[1]["rvcontinue"] == "1|2"
    assert session.calls[2]["rvcontinue"] == "1|3"


def test_max_revisions_caps_output_and_stops_paging():
    payloads = [_page([_rev(1), _rev(2, parentid=1)], cont="1|3")]
    client, session = make_client(payloads)
    revs = client.fetch_revisions("X", max_revisions=2)
    assert [r.revid for r in revs] == [1, 2]
    # only one request should have been made — we hit the cap on page one
    assert len(session.calls) == 1


def test_missing_page_raises():
    client, _ = make_client([{"query": {"pages": [{"missing": True, "title": "X"}]}}])
    with pytest.raises(WikiAPIError):
        client.fetch_revisions("X")


def test_api_error_raises():
    client, _ = make_client([{"error": {"code": "bad", "info": "boom"}}])
    with pytest.raises(WikiAPIError):
        client.fetch_revisions("X")


def test_minor_and_anon_flags_and_hidden_user():
    payloads = [
        _page(
            [
                _rev(1, minor=True),
                _rev(2, parentid=1, anon=True, user="1.2.3.4"),
                {"revid": 3, "parentid": 2, "timestamp": "t", "userhidden": True,
                 "comment": "x", "size": 10},
            ]
        )
    ]
    client, _ = make_client(payloads)
    revs = client.fetch_revisions("X")
    assert revs[0].minor is True and revs[0].anon is False
    assert revs[1].anon is True
    assert revs[2].user is None  # suppressed author normalised to None


def test_content_parsed_from_slots():
    rev = _rev(1)
    rev["slots"] = {"main": {"content": "hello world"}}
    client, _ = make_client([_page([rev])])
    revs = client.fetch_revisions("X", include_content=True)
    assert revs[0].content == "hello world"
