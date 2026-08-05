"""Tests for CLI history scope, scoring, and JSON export."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from wikicontrib.__main__ import (
    _print_discussion_leaderboard,
    _run_analyze,
    build_parser,
    main,
)
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
        content="alpha beta" if revid == 1 else "alpha beta gamma",
    )


class FakeStore:
    def __init__(self, revisions):
        self.revisions = revisions

    def get_page_history(self, *_args, **_kwargs):
        self.kwargs = _kwargs
        return SimpleNamespace(
            title="Example",
            revisions=self.revisions,
            editors={"Alice"},
            has_talk=False,
            talk_title="Talk:Example",
            talk_revisions=[],
            talk_participants=set(),
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


def test_parser_accepts_json_alias_weights_and_top_limit():
    args = build_parser().parse_args(
        [
            "analyze",
            "Example",
            "--json",
            "result.json",
            "--weight-volume",
            "1",
            "--weight-persistence",
            "2",
            "--top",
            "7",
            "--charts-dir",
            "figures",
        ]
    )
    assert args.output_json == Path("result.json")
    assert args.weight_volume == 1.0
    assert args.weight_persistence == 2.0
    assert args.top == 7
    assert args.charts_dir == Path("figures")


@pytest.mark.parametrize("value", ["-1", "nan", "inf"])
def test_parser_rejects_invalid_weight(value):
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(["analyze", "Example", "--weight-discussion", value])
    assert exc_info.value.code == 2


def test_main_rejects_an_all_zero_weight_policy():
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "analyze",
                "Example",
                "--weight-volume",
                "0",
                "--weight-additive",
                "0",
                "--weight-persistence",
                "0",
                "--weight-discussion",
                "0",
            ]
        )
    assert exc_info.value.code == 2


def test_json_export_enables_content_analysis_and_is_self_explaining(
    monkeypatch, capsys, tmp_path
):
    store = FakeStore([_revision(1), _revision(2)])
    monkeypatch.setattr("wikicontrib.store.RevisionStore", lambda: store)
    output_path = tmp_path / "nested" / "analysis.json"

    assert (
        _run_analyze(
            "Example",
            2,
            output_json=output_path,
            limit=1,
        )
        == 0
    )

    assert store.kwargs["include_content"] is True
    output = capsys.readouterr().out
    assert "composite impact — top 1" in output
    assert "JSON report" in output

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["article"] == {
        "title": "Example",
        "talk_title": "Talk:Example",
        "revision_count": 2,
        "talk_revision_count": 0,
        "first_edit": "2020-01-01T00:00:00Z",
        "latest_fetched_edit": "2020-01-02T00:00:00Z",
        "history_scope": "earliest 2",
        "historical_slice": True,
    }
    assert payload["weights"] == {
        "volume": 0.25,
        "additive": 0.25,
        "persistence": 0.25,
        "discussion": 0.25,
    }
    assert [row["rank"] for row in payload["contributors"]] == [1]
    contributor = payload["contributors"][0]
    assert contributor["user"] == "Alice"
    assert contributor["features"].keys() == {
        "volume",
        "additive",
        "persistence",
        "discussion",
    }
    assert contributor["contributions"]["volume"].keys() == {
        "axis_score",
        "weight",
        "weighted_value",
    }
    assert "words_surviving" in contributor["raw_metrics"]
    assert "Breakdown:" in contributor["explanation"]


def test_custom_cli_weights_are_normalised_in_output(monkeypatch, tmp_path):
    store = FakeStore([_revision(1), _revision(2)])
    monkeypatch.setattr("wikicontrib.store.RevisionStore", lambda: store)
    output_path = tmp_path / "analysis.json"

    assert (
        main(
            [
                "analyze",
                "Example",
                "--max-revisions",
                "2",
                "--output-json",
                str(output_path),
                "--weight-volume",
                "1",
                "--weight-additive",
                "1",
                "--weight-persistence",
                "2",
                "--weight-discussion",
                "1",
            ]
        )
        == 0
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["weights"] == {
        "volume": 0.2,
        "additive": 0.2,
        "persistence": 0.4,
        "discussion": 0.2,
    }


def test_charts_dir_enables_content_analysis_and_writes_pngs(
    monkeypatch, capsys, tmp_path
):
    store = FakeStore([_revision(1), _revision(2)])
    monkeypatch.setattr("wikicontrib.store.RevisionStore", lambda: store)
    charts_dir = tmp_path / "figures"

    assert _run_analyze("Example", 2, charts_dir=charts_dir, limit=1) == 0

    assert store.kwargs["include_content"] is True
    output = capsys.readouterr().out
    assert "charts generated  : 4" in output
    assert (charts_dir / "impact_leaderboard.png").is_file()
    assert (charts_dir / "additive_maintenance.png").is_file()
    assert (charts_dir / "edit_timeline.png").is_file()
    assert len(list((charts_dir / "radars").glob("*.png"))) == 1
