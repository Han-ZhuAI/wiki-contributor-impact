"""Tests for CLI history-scope reporting and safeguards."""

from types import SimpleNamespace

from wikicontrib.__main__ import _print_discussion_leaderboard, _run_analyze
from wikicontrib.api import RawRevision


def _revision(revid: int) -> RawRevision:
    return RawRevision(
        revid=revid,
        parentid=revid - 1,
        timestamp=f"2020-01-0{revid}T00:00:00Z",
        user="Alice",
        userid=1,
        comment="",
        size=10,
        minor=False,
        anon=False,
    )


class FakeStore:
    def __init__(self, revisions):
        self.revisions = revisions

    def get_page_history(self, *_args, **_kwargs):
        return SimpleNamespace(
            title="Example",
            revisions=self.revisions,
            editors={"Alice"},
            has_talk=False,
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


def test_discussion_leaderboard_explains_centrality_and_temporal_link(capsys):
    talk_revision = _revision(10)
    talk_revision.content = (
        "== Topic ==\n"
        "Proposal. [[User:Alice]] 10:00, 1 January 2020 (UTC)\n"
        ":Reply. [[User:Bob]] 11:00, 1 January 2020 (UTC)"
    )
    article_revision = _revision(11)
    article_revision.timestamp = "2020-01-02T00:00:00Z"

    _print_discussion_leaderboard([talk_revision], [article_revision])
    output = capsys.readouterr().out
    assert "discussion impact" in output
    assert "reply centrality" in output
    assert "Alice" in output
    assert "Bob" in output
    assert "temporal proxy, not proof of causation" in output
