"""Tests for Talk-page parsing, reply graphs and discussion PageRank."""

import pytest

from wikicontrib.api import RawRevision
from wikicontrib.talk import (
    TalkComment,
    analyze_discussion,
    build_reply_graph,
    comments_from_history,
    parse_talk_page,
    weighted_pagerank,
)


def _revision(revid: int, content: str) -> RawRevision:
    return RawRevision(
        revid=revid,
        parentid=revid - 1,
        timestamp=f"2020-01-{revid:02d}T00:00:00Z",
        user="Editor",
        userid=1,
        comment="talk edit",
        size=len(content),
        minor=False,
        anon=False,
        content=content,
    )


def _comment(author: str, depth: int, order: int, thread: str = "Topic"):
    return TalkComment(
        author=author,
        text=f"comment {order}",
        thread=thread,
        depth=depth,
        timestamp=f"00:0{order}, 1 January 2020 (UTC)",
        order=order,
    )


def test_parse_registered_user_signature_and_heading():
    comments = parse_talk_page(
        "== Sources ==\nPlease add a citation. --[[User:Alice|Alice]] "
        "12:34, 1 January 2020 (UTC)"
    )
    assert len(comments) == 1
    assert comments[0].author == "Alice"
    assert comments[0].thread == "Sources"
    assert comments[0].text == "Please add a citation."
    assert comments[0].timestamp == "12:34, 1 January 2020 (UTC)"


def test_parse_user_talk_signature_and_indentation():
    comments = parse_talk_page(
        "== Topic ==\n::Agreed. [[User talk:Bob|Bob]] "
        "09:05, 2 February 2021 (UTC)"
    )
    assert comments[0].author == "Bob"
    assert comments[0].depth == 2
    assert comments[0].text == "Agreed."


def test_parse_ipv4_contributions_signature():
    comments = parse_talk_page(
        "Comment --[[Special:Contributions/192.0.2.1|192.0.2.1]] "
        "08:00, 3 March 2022 (UTC)"
    )
    assert comments[0].author == "192.0.2.1"


def test_parse_ipv6_contributions_signature():
    comments = parse_talk_page(
        "Comment --[[Special:Contributions/2001:db8::1|2001:db8::1]] "
        "08:00, 3 March 2022 (UTC)"
    )
    assert comments[0].author == "2001:db8::1"


def test_reject_non_ip_contributions_link():
    assert parse_talk_page(
        "Comment [[Special:Contributions/not-an-ip|someone]] "
        "08:00, 3 March 2022 (UTC)"
    ) == []


def test_parse_unsigned_template():
    comments = parse_talk_page(
        "Forgot to sign this. {{unsigned|Carol|10:10, 4 April 2023 (UTC)}}"
    )
    assert comments[0].author == "Carol"
    assert comments[0].text == "Forgot to sign this."
    assert comments[0].timestamp == "10:10, 4 April 2023 (UTC)"


def test_ignore_unattributed_prose():
    assert parse_talk_page("== Topic ==\nThis has no signature.") == []


def test_inline_user_mention_is_not_mistaken_for_signature():
    assert parse_talk_page("Please ask [[User:Alice|Alice]] about it.") == []


def test_parse_multiline_comment():
    comments = parse_talk_page(
        "== Topic ==\nFirst line of the point.\nSecond line. --[[User:Alice|A]] "
        "12:34, 1 January 2020 (UTC)"
    )
    assert comments[0].text == "First line of the point. Second line."


def test_heading_markup_is_rendered_as_plain_thread_name():
    comments = parse_talk_page(
        "== ''Sources'' for [[Alan Turing|Turing]] ==\n"
        "Point. [[User:Alice|A]] 12:34, 1 January 2020 (UTC)"
    )
    assert comments[0].thread == "Sources for Turing"


def test_comments_before_first_heading_use_lead_thread():
    comments = parse_talk_page(
        "Lead comment. [[User:Alice|A]] 12:34, 1 January 2020 (UTC)"
    )
    assert comments[0].thread == "(lead)"


def test_revid_is_attached_to_parsed_comment():
    comments = parse_talk_page(
        "Point. [[User:Alice|A]] 12:34, 1 January 2020 (UTC)", revid=99
    )
    assert comments[0].revid == 99


def test_history_counts_a_persistent_comment_once():
    first = "== Topic ==\nOne. [[User:Alice|A]] 10:00, 1 January 2020 (UTC)"
    second = (
        first
        + "\n:Two. [[User:Bob|B]] 11:00, 1 January 2020 (UTC)"
    )
    comments = comments_from_history([_revision(1, first), _revision(2, second)])
    assert [comment.author for comment in comments] == ["Alice", "Bob"]
    assert [comment.revid for comment in comments] == [1, 2]


def test_history_retains_comment_removed_from_later_state():
    first = "Old point. [[User:Alice|A]] 10:00, 1 January 2020 (UTC)"
    comments = comments_from_history([_revision(1, first), _revision(2, "")])
    assert [comment.author for comment in comments] == ["Alice"]


def test_history_uses_signature_identity_when_comment_text_is_edited():
    first = "Typo. [[User:Alice|A]] 10:00, 1 January 2020 (UTC)"
    fixed = "Fixed typo. [[User:Alice|A]] 10:00, 1 January 2020 (UTC)"
    comments = comments_from_history([_revision(1, first), _revision(2, fixed)])
    assert len(comments) == 1


def test_reply_targets_nearest_shallower_comment():
    comments = [
        _comment("Alice", 0, 0),
        _comment("Bob", 1, 1),
        _comment("Carol", 2, 2),
        _comment("Dave", 1, 3),
    ]
    assert build_reply_graph(comments) == {
        ("Bob", "Alice"): 1,
        ("Carol", "Bob"): 1,
        ("Dave", "Alice"): 1,
    }


def test_unindented_followup_targets_thread_starter():
    comments = [_comment("Alice", 0, 0), _comment("Bob", 0, 1)]
    assert build_reply_graph(comments) == {("Bob", "Alice"): 1}


def test_repeated_replies_become_edge_weight():
    comments = [
        _comment("Alice", 0, 0),
        _comment("Bob", 1, 1),
        _comment("Bob", 1, 2),
    ]
    assert build_reply_graph(comments) == {("Bob", "Alice"): 2}


def test_self_reply_does_not_create_influence_edge():
    comments = [_comment("Alice", 0, 0), _comment("Alice", 1, 1)]
    assert build_reply_graph(comments) == {}


def test_threads_do_not_cross_link():
    comments = [
        _comment("Alice", 0, 0, "First"),
        _comment("Bob", 0, 1, "Second"),
    ]
    assert build_reply_graph(comments) == {}


def test_empty_pagerank():
    assert weighted_pagerank([], {}) == {}


def test_single_node_pagerank_is_one():
    assert weighted_pagerank(["Alice"], {}) == {"Alice": 1.0}


def test_pagerank_scores_sum_to_one():
    scores = weighted_pagerank(
        ["Alice", "Bob", "Carol"],
        {("Bob", "Alice"): 2, ("Carol", "Alice"): 1},
    )
    assert sum(scores.values()) == pytest.approx(1.0)
    assert scores["Alice"] > scores["Bob"]
    assert scores["Alice"] > scores["Carol"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"damping": 0.0},
        {"damping": 1.0},
        {"tolerance": 0.0},
        {"max_iterations": 0},
    ],
)
def test_pagerank_rejects_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        weighted_pagerank(["Alice"], {}, **kwargs)


def test_analyze_discussion_aggregates_activity_and_influence():
    first = (
        "== Sources ==\n"
        "Start. [[User:Alice|A]] 10:00, 1 January 2020 (UTC)"
    )
    second = (
        first
        + "\n:Reply. [[User:Bob|B]] 11:00, 1 January 2020 (UTC)"
        + "\n::Follow-up. [[User:Carol|C]] 12:00, 1 January 2020 (UTC)"
    )
    report = analyze_discussion([_revision(1, first), _revision(2, second)])

    assert len(report.comments) == 3
    assert report.edges == {("Bob", "Alice"): 1, ("Carol", "Bob"): 1}
    assert report.contributors["Alice"].threads_started == 1
    assert report.contributors["Alice"].replies_received == 1
    assert report.contributors["Bob"].comments == 1
    assert report.contributors["Bob"].replies == 1
    assert report.contributors["Bob"].replies_received == 1
    assert report.contributors["Carol"].replies == 1
    assert sum(c.pagerank for c in report.contributors.values()) == pytest.approx(1.0)


def test_report_ranking_has_stable_alphabetical_ties():
    report = analyze_discussion(
        [
            _revision(
                1,
                "== A ==\nOne. [[User:Bob|B]] 10:00, 1 January 2020 (UTC)\n"
                "== B ==\nTwo. [[User:Alice|A]] 11:00, 1 January 2020 (UTC)",
            )
        ]
    )
    assert [contributor.user for contributor in report.ranked()] == ["Alice", "Bob"]
