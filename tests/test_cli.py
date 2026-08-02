"""Tests for CLI history-scope reporting and safeguards."""

from types import SimpleNamespace

from wikicontrib.__main__ import _run_analyze
from wikicontrib.api import RawRevision


def _revision(revid: int, *, user: str = "Alice", content: str | None = None) -> RawRevision:
    return RawRevision(
        revid=revid,
        parentid=revid - 1,
        timestamp=f"2020-01-0{revid}T00:00:00Z",
        user=user,
        userid=1,
        comment="",
        size=10,
        minor=False,
        anon=False,
        content=content,
    )


class FakeStore:
    def __init__(self, revisions, talk_revisions=None):
        self.revisions = revisions
        self.talk_revisions = talk_revisions or []

    def get_page_history(self, *_args, **_kwargs):
        return SimpleNamespace(
            title="Example",
            revisions=self.revisions,
            editors={"Alice"},
            has_talk=bool(self.talk_revisions),
            talk_title="Talk:Example",
            talk_revisions=self.talk_revisions,
            talk_participants={r.user for r in self.talk_revisions if r.user},
        )


def test_capped_history_is_labelled_as_a_historical_slice(monkeypatch, capsys):
    monkeypatch.setattr(
        "wikicontrib.store.RevisionStore",
        lambda: FakeStore([_revision(1), _revision(2)]),
    )

    assert _run_analyze("Example", 2) == 0
    output = capsys.readouterr().out
    assert "latest fetched edit" in output
    assert "history scope      : earliest 2 revisions" in output
    assert "not the current article" in output


def test_uncapped_history_is_labelled_complete(monkeypatch, capsys):
    monkeypatch.setattr(
        "wikicontrib.store.RevisionStore",
        lambda: FakeStore([_revision(1), _revision(2)]),
    )

    assert _run_analyze("Example", None) == 0
    output = capsys.readouterr().out
    assert "history scope      : complete" in output
    assert "not the current article" not in output


def test_discussion_leaderboard_is_printed(monkeypatch, capsys):
    talk = (
        "== Topic ==\n"
        "Start. [[User:Alice|A]] 10:00, 1 January 2020 (UTC)\n"
        ":Reply. [[User:Bob|B]] 11:00, 1 January 2020 (UTC)"
    )
    monkeypatch.setattr(
        "wikicontrib.store.RevisionStore",
        lambda: FakeStore(
            [_revision(1)],
            [_revision(2, user="Bob", content=talk)],
        ),
    )

    assert _run_analyze("Example", 10, with_discussion=True) == 0
    output = capsys.readouterr().out
    assert "discussion impact" in output
    assert "reply-graph PageRank" in output
    assert "Alice" in output
    assert "Bob" in output
