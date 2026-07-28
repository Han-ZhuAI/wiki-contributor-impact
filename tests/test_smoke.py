"""Smoke tests confirming the package imports and the CLI parser builds."""

import pytest

import wikicontrib
from wikicontrib.__main__ import build_parser


def test_version_is_exposed():
    assert isinstance(wikicontrib.__version__, str)
    assert wikicontrib.__version__


def test_parser_accepts_analyze_command():
    parser = build_parser()
    args = parser.parse_args(["analyze", "Alan Turing", "--max-revisions", "10"])
    assert args.command == "analyze"
    assert args.article == "Alan Turing"
    assert args.max_revisions == 10


def test_parser_fetches_full_history_by_default():
    parser = build_parser()
    args = parser.parse_args(["analyze", "Alan Turing"])
    assert args.max_revisions is None


@pytest.mark.parametrize("value", ["0", "-1"])
def test_parser_rejects_non_positive_revision_caps(value):
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["analyze", "Alan Turing", "--max-revisions", value])
