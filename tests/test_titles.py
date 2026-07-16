"""Tests for title/namespace handling."""

import pytest

from wikicontrib.titles import (
    is_talk_title,
    split_namespace,
    subject_title,
    talk_title,
)


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Alan Turing", "Talk:Alan Turing"),
        ("User:Example", "User talk:Example"),
        ("Wikipedia:Sandbox", "Wikipedia talk:Sandbox"),
        ("Template:Infobox", "Template talk:Infobox"),
        ("Category:Mathematics", "Category talk:Mathematics"),
    ],
)
def test_talk_title(title, expected):
    assert talk_title(title) == expected


@pytest.mark.parametrize(
    "title", ["Talk:Alan Turing", "User talk:Example", "Template talk:Infobox"]
)
def test_talk_title_is_idempotent(title):
    assert talk_title(title) == title


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Talk:Alan Turing", "Alan Turing"),
        ("User talk:Example", "User:Example"),
        ("Alan Turing", "Alan Turing"),  # already a subject page
    ],
)
def test_subject_title(title, expected):
    assert subject_title(title) == expected


def test_talk_and_subject_round_trip():
    for title in ["Alan Turing", "User:Example", "Category:Mathematics"]:
        assert subject_title(talk_title(title)) == title


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Alan Turing", False),
        ("Talk:Alan Turing", True),
        ("User:Example", False),
        ("User talk:Example", True),
    ],
)
def test_is_talk_title(title, expected):
    assert is_talk_title(title) is expected


def test_unknown_prefix_stays_in_main_namespace():
    # A colon in an ordinary article title must not be mistaken for a namespace.
    assert split_namespace("Apollo 11: The Movie") == (None, "Apollo 11: The Movie")
    assert talk_title("Apollo 11: The Movie") == "Talk:Apollo 11: The Movie"


def test_split_namespace_recognises_known_prefixes():
    assert split_namespace("User:Example") == ("User", "Example")
    assert split_namespace("Talk:Alan Turing") == ("Talk", "Alan Turing")
    assert split_namespace("Alan Turing") == (None, "Alan Turing")
