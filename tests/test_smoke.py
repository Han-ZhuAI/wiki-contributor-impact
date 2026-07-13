"""Smoke tests confirming the package imports and the CLI parser builds."""

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
