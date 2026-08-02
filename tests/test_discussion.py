"""Tests for Talk-page parsing and discussion-impact metrics."""

from datetime import timezone

import pytest

from wikicontrib.api import RawRevision
from wikicontrib.discussion import analyze_discussion, parse_talk_page

TALK_PAGE = """{{Talk header}}
== Scope ==
Proposal text. --[[User:Alice|Alice]] 10:00, 1 January 2020 (UTC)
:Good idea. [[User talk:Bob|Bob]] 11:00, 1 January 2020 (UTC)
::I found a source. [[Special:Contributions/192.0.2.1|192.0.2.1]] 12:00, 1 January 2020 (UTC)
== Sources ==
New source thread. {{unsigned|Carol|09:00, 2 January 2020 (UTC)}}
"""


def _revision(
    revid: int,
    *,
    timestamp: str,
    user: str | None,
    content: str | None = None,
) -> RawRevision:
    return RawRevision(
        revid=revid,
        parentid=revid - 1,
        timestamp=timestamp,
        user=user,
        userid=1 if user else None,
        comment="",
        size=len(content or ""),
        minor=False,
        anon=False,
        content=content,
    )


def test_parser_recovers_threads_signatures_and_reply_depth():
    parsed = parse_talk_page(TALK_PAGE)
    assert [thread.title for thread in parsed.threads] == ["Scope", "Sources"]
    assert [post.user for post in parsed.posts] == [
        "Alice",
        "Bob",
        "192.0.2.1",
        "Carol",
    ]
    assert [post.depth for post in parsed.posts] == [0, 1, 2, 0]
    assert parsed.posts[0].text == "Proposal text."
    assert parsed.posts[0].timestamp.tzinfo == timezone.utc
    assert parsed.parse_rate == 1.0


def test_parser_keeps_signed_lead_comments_as_a_thread():
    content = (
        "Lead comment. [[User:Alice]] 10:00, 1 January 2020 (UTC)\n"
        "== Topic ==\n"
        "Body. [[User:Bob]] 11:00, 1 January 2020 (UTC)"
    )
    parsed = parse_talk_page(content)
    assert [thread.title for thread in parsed.threads] == ["(lead)", "Topic"]


def test_parser_reports_unattributed_timestamp_shaped_signatures():
    content = (
        "No user link 10:00, 1 January 2020 (UTC)\n"
        "Signed [[User:Alice]] 11:00, 1 January 2020 (UTC)"
    )
    parsed = parse_talk_page(content)
    assert parsed.signatures_seen == 2
    assert len(parsed.posts) == 1
    assert parsed.parse_rate == pytest.approx(0.5)


def test_distant_user_link_is_not_mistaken_for_a_signature():
    content = (
        "[[User:Quoted person]] "
        + ("long unsigned comment " * 40)
        + "10:00, 1 January 2020 (UTC)"
    )
    parsed = parse_talk_page(content)
    assert parsed.signatures_seen == 1
    assert parsed.posts == []


def test_reply_graph_targets_nearest_preceding_shallower_post():
    report = analyze_discussion(
        [
            _revision(
                10,
                timestamp="2020-01-03T00:00:00Z",
                user="Alice",
                content=TALK_PAGE,
            )
        ]
    )
    assert report.reply_edges == {
        ("Bob", "Alice"): 1,
        ("192.0.2.1", "Bob"): 1,
    }
    assert report.contributors["Bob"].replies_made == 1
    assert report.contributors["Bob"].replies_received == 1
    assert report.contributors["Alice"].replies_received == 1


def test_discussion_report_counts_threads_and_participation():
    report = analyze_discussion(
        [
            _revision(
                10,
                timestamp="2020-01-03T00:00:00Z",
                user="Alice",
                content=TALK_PAGE,
            )
        ]
    )
    assert report.total_posts == 4
    assert report.contributors["Alice"].threads_started == 1
    assert report.contributors["Carol"].threads_started == 1
    assert report.participation_share("Alice") == pytest.approx(0.25)
    assert report.thread_initiation_rate("Alice") == pytest.approx(0.5)
    assert report.participation_share("Unknown") == 0.0


def test_pagerank_measures_attention_received_and_sums_to_one():
    report = analyze_discussion(
        [
            _revision(
                10,
                timestamp="2020-01-03T00:00:00Z",
                user="Alice",
                content=TALK_PAGE,
            )
        ]
    )
    ranks = {user: contributor.pagerank for user, contributor in report.contributors.items()}
    assert sum(ranks.values()) == pytest.approx(1.0)
    assert ranks["Alice"] > ranks["Bob"] > ranks["192.0.2.1"]
    assert report.ranked()[0].user == "Alice"


def test_temporal_link_counts_same_user_article_edits_within_window():
    talk_content = (
        "== Topic ==\n"
        "Proposal. [[User:Alice]] 10:00, 1 January 2020 (UTC)\n"
        ":Reply. [[User:Bob]] 12:00, 1 January 2020 (UTC)"
    )
    talk_revisions = [
        _revision(
            10,
            timestamp="2020-01-02T00:00:00Z",
            user="Alice",
            content=talk_content,
        )
    ]
    article_revisions = [
        _revision(1, timestamp="2019-12-31T00:00:00Z", user="Alice"),
        _revision(2, timestamp="2020-01-02T00:00:00Z", user="Alice"),
        _revision(3, timestamp="2020-01-03T00:00:00Z", user="Alice"),
        _revision(4, timestamp="2020-01-02T00:00:00Z", user="Carol"),
        _revision(5, timestamp="2020-01-20T00:00:00Z", user="Bob"),
    ]

    report = analyze_discussion(talk_revisions, article_revisions)
    alice = report.contributors["Alice"]
    bob = report.contributors["Bob"]
    assert alice.linked_posts == 1
    assert alice.follow_up_edits == 2
    assert alice.linked_post_rate == 1.0
    assert bob.linked_posts == 0
    assert bob.follow_up_edits == 0


def test_overlapping_post_windows_do_not_double_count_article_edits():
    talk_content = (
        "== One ==\n"
        "First. [[User:Alice]] 10:00, 1 January 2020 (UTC)\n"
        "== Two ==\n"
        "Second. [[User:Alice]] 10:00, 2 January 2020 (UTC)"
    )
    report = analyze_discussion(
        [
            _revision(
                10,
                timestamp="2020-01-03T00:00:00Z",
                user="Alice",
                content=talk_content,
            )
        ],
        [_revision(20, timestamp="2020-01-03T00:00:00Z", user="Alice")],
    )
    assert report.contributors["Alice"].linked_posts == 2
    assert report.contributors["Alice"].follow_up_edits == 1


def test_only_latest_cumulative_talk_snapshot_is_counted():
    first = "== Topic ==\nFirst. [[User:Alice]] 10:00, 1 January 2020 (UTC)"
    second = (
        first
        + "\n:Second. [[User:Bob]] 11:00, 1 January 2020 (UTC)"
    )
    report = analyze_discussion(
        [
            _revision(
                10,
                timestamp="2020-01-01T10:00:00Z",
                user="Alice",
                content=first,
            ),
            _revision(
                11,
                timestamp="2020-01-01T11:00:00Z",
                user="Bob",
                content=second,
            ),
        ]
    )
    assert report.total_posts == 2
    assert set(report.contributors) == {"Alice", "Bob"}


def test_missing_talk_content_returns_empty_report():
    report = analyze_discussion(
        [
            _revision(
                10,
                timestamp="2020-01-01T10:00:00Z",
                user="Alice",
                content=None,
            )
        ]
    )
    assert report.contributors == {}
    assert report.threads == []
    assert report.parse_rate == 1.0


def test_negative_link_window_is_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        analyze_discussion([], link_window_days=-1)
