"""Tests for CLI history scope, scoring, and JSON export."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from wikicontrib.__main__ import (
    _print_discussion_leaderboard,
    _run_analyze,
    _run_evaluate,
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
            "--exclude-automated-candidates",
        ]
    )
    assert args.output_json == Path("result.json")
    assert args.weight_volume == 1.0
    assert args.weight_persistence == 2.0
    assert args.top == 7
    assert args.charts_dir == Path("figures")
    assert args.exclude_automated_candidates is True


def test_parser_accepts_multi_article_evaluation_outputs():
    args = build_parser().parse_args(
        [
            "evaluate",
            "Alan Turing",
            "Kimchi",
            "--max-revisions",
            "50",
            "--top-k",
            "5",
            "--output-json",
            "evaluation.json",
            "--output-markdown",
            "evaluation.md",
        ]
    )
    assert args.articles == ["Alan Turing", "Kimchi"]
    assert args.max_revisions == 50
    assert args.top_k == 5
    assert args.output_json == Path("evaluation.json")
    assert args.output_markdown == Path("evaluation.md")


def test_evaluate_requires_two_articles():
    with pytest.raises(SystemExit) as exc_info:
        main(["evaluate", "Only one"])
    assert exc_info.value.code == 2


def test_evaluate_writes_cross_article_reports(monkeypatch, capsys, tmp_path):
    class EvaluationStore:
        def get_page_history(self, title, **kwargs):
            first = _revision(1)
            second = _revision(2)
            second.user = "Bob" if title == "Second" else "Alice"
            return SimpleNamespace(
                title=title,
                revisions=[first, second],
                talk_revisions=[],
            )

    monkeypatch.setattr("wikicontrib.store.RevisionStore", EvaluationStore)
    json_path = tmp_path / "evaluation.json"
    markdown_path = tmp_path / "evaluation.md"
    assert (
        _run_evaluate(
            ["First", "Second"],
            2,
            top_k=2,
            output_json=json_path,
            output_markdown=markdown_path,
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "weight-sensitivity evaluation" in output
    assert "First" in output and "Second" in output
    assert json.loads(json_path.read_text())["method"]["revision_limit"] == 2
    assert markdown_path.is_file()


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
    assert payload["schema_version"] == 3
    assert payload["automation"]["candidates"] == []
    assert payload["ranking"] == {
        "excluded_users": [],
        "history_and_provenance_preserved": True,
    }
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
    assert payload["wikitext_elements"]["prose"] == {
        "added": 3,
        "removed": 0,
        "net": 3,
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
    assert contributor["wikitext_elements"]["prose"]["added"] == 3
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


def test_automation_filter_is_explicit_and_preserves_history(monkeypatch, capsys):
    bot = _revision(1)
    bot.user = "ImportBot"
    human = _revision(2)
    human.user = "Alice"
    store = FakeStore([bot, human])
    monkeypatch.setattr("wikicontrib.store.RevisionStore", lambda: store)

    assert (
        _run_analyze(
            "Example",
            2,
            exclude_automated_candidates=True,
        )
        == 0
    )

    output = capsys.readouterr().out
    assert store.kwargs["include_content"] is True
    assert "ImportBot: confidence=high" in output
    assert "excluded from composite ranking: ImportBot" in output
    assert "all revisions remain in diff and provenance calculations" in output


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
