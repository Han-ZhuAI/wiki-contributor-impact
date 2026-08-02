"""Talk-page parsing and discussion-impact metrics.

Wikipedia talk pages are semi-structured wikitext rather than a purpose-built
thread format.  This module uses the two conventions that are stable enough to
measure:

* section headings delimit discussion threads;
* signed comments end in a user link and UTC timestamp, while leading colons
  encode reply depth.

For each page snapshot we build a weighted reply graph.  An edge ``u -> v``
means that ``u`` replied to ``v``; weighted PageRank therefore estimates whose
comments attracted attention.  We also record whether a participant edited the
article within a configurable window after posting.  That temporal link is a
transparent activity proxy, not proof that the discussion caused the edit.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .api import RawRevision

DEFAULT_LINK_WINDOW_DAYS = 14
MAX_SIGNATURE_PREFIX_CHARS = 500

_HEADING_RE = re.compile(
    r"^(?P<marks>={2,6})[ \t]*(?P<title>.*?)[ \t]*(?P=marks)[ \t]*$",
    re.MULTILINE,
)
_TIMESTAMP_RE = re.compile(
    r"(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d),\s*"
    r"(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]{3,9})\s+"
    r"(?P<year>\d{4})\s*\(UTC\)",
    re.IGNORECASE,
)
_USER_LINK_RE = re.compile(
    r"\[\[\s*:?(?:User(?:[ _]talk)?):"
    r"(?P<user>[^]|#]+)(?:#[^]|]*)?(?:\|[^\]]*)?\]\]",
    re.IGNORECASE,
)
_CONTRIBUTIONS_LINK_RE = re.compile(
    r"\[\[\s*:?(?:Special:)?Contributions/"
    r"(?P<user>[^]|#]+)(?:#[^]|]*)?(?:\|[^\]]*)?\]\]",
    re.IGNORECASE,
)
_UNSIGNED_RE = re.compile(
    r"\{\{\s*unsigned(?:IP)?\s*\|\s*(?P<user>[^|}]+)",
    re.IGNORECASE,
)
_WIKILINK_RE = re.compile(r"\[\[(?:[^]|]*\|)?([^]]+)\]\]")


@dataclass(frozen=True)
class TalkPost:
    """One signed comment recovered from a talk-page snapshot."""

    thread_id: int
    thread_title: str
    user: str
    timestamp: datetime
    depth: int
    text: str


@dataclass
class TalkThread:
    """A section heading and the signed posts beneath it."""

    thread_id: int
    title: str
    posts: list[TalkPost] = field(default_factory=list)


@dataclass
class TalkParseResult:
    """Parser output plus an explicit signature-recovery diagnostic."""

    threads: list[TalkThread] = field(default_factory=list)
    signatures_seen: int = 0

    @property
    def posts(self) -> list[TalkPost]:
        return [post for thread in self.threads for post in thread.posts]

    @property
    def parse_rate(self) -> float:
        """Share of timestamp-shaped signatures attributed to a user."""
        if not self.signatures_seen:
            return 1.0
        return len(self.posts) / self.signatures_seen


@dataclass
class ContributorDiscussion:
    """Discussion signals attributed to one talk-page participant."""

    user: str
    posts: int = 0
    threads_started: int = 0
    replies_made: int = 0
    replies_received: int = 0
    linked_posts: int = 0
    follow_up_edits: int = 0
    pagerank: float = 0.0

    @property
    def linked_post_rate(self) -> float:
        """Share of posts followed by one of the user's article edits."""
        return self.linked_posts / self.posts if self.posts else 0.0


@dataclass
class DiscussionReport:
    """Talk threads, reply graph and per-contributor discussion metrics."""

    contributors: dict[str, ContributorDiscussion] = field(default_factory=dict)
    threads: list[TalkThread] = field(default_factory=list)
    reply_edges: dict[tuple[str, str], int] = field(default_factory=dict)
    signatures_seen: int = 0

    @property
    def total_posts(self) -> int:
        return sum(contributor.posts for contributor in self.contributors.values())

    @property
    def parse_rate(self) -> float:
        if not self.signatures_seen:
            return 1.0
        return self.total_posts / self.signatures_seen

    def participation_share(self, user: str) -> float:
        """Fraction of parsed posts written by ``user``."""
        total = self.total_posts
        if not total or user not in self.contributors:
            return 0.0
        return self.contributors[user].posts / total

    def thread_initiation_rate(self, user: str) -> float:
        """Fraction of parsed threads started by ``user``."""
        if not self.threads or user not in self.contributors:
            return 0.0
        return self.contributors[user].threads_started / len(self.threads)

    def ranked(self) -> list[ContributorDiscussion]:
        """Rank by reply-graph centrality, then engagement, deterministically."""
        return sorted(
            self.contributors.values(),
            key=lambda contributor: (
                -contributor.pagerank,
                -contributor.replies_received,
                -contributor.posts,
                contributor.user,
            ),
        )


def parse_talk_page(content: str) -> TalkParseResult:
    """Parse signed posts from one talk-page wikitext snapshot.

    Sections with no recoverable signed posts are excluded.  Text before the
    first heading is retained as a ``"(lead)"`` thread only when it contains a
    signed post.
    """
    headings = list(_HEADING_RE.finditer(content))
    sections: list[tuple[str, str]] = []

    if headings:
        sections.append(("(lead)", content[: headings[0].start()]))
        for index, heading in enumerate(headings):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
            sections.append((heading.group("title").strip(), content[heading.end() : end]))
    else:
        sections.append(("(lead)", content))

    result = TalkParseResult()
    for title, section_text in sections:
        thread_id = len(result.threads)
        posts, signatures_seen = _parse_section(section_text, title, thread_id)
        result.signatures_seen += signatures_seen
        if posts:
            result.threads.append(
                TalkThread(thread_id=thread_id, title=title, posts=posts)
            )
    return result


def analyze_discussion(
    talk_revisions: Iterable[RawRevision],
    article_revisions: Iterable[RawRevision] = (),
    *,
    link_window_days: int = DEFAULT_LINK_WINDOW_DAYS,
) -> DiscussionReport:
    """Build discussion metrics from the latest available talk-page snapshot.

    Revision content is cumulative, so parsing every snapshot would count the
    same signed post repeatedly.  We therefore parse only the latest revision
    with visible content, then correlate its posts with article edits.
    """
    if link_window_days < 0:
        raise ValueError("link_window_days must be non-negative")

    latest_content = next(
        (
            revision.content
            for revision in reversed(list(talk_revisions))
            if revision.content is not None
        ),
        None,
    )
    if latest_content is None:
        return DiscussionReport()

    parsed = parse_talk_page(latest_content)
    report = DiscussionReport(
        threads=parsed.threads,
        signatures_seen=parsed.signatures_seen,
    )

    for thread in parsed.threads:
        for post in thread.posts:
            contributor = report.contributors.setdefault(
                post.user, ContributorDiscussion(user=post.user)
            )
            contributor.posts += 1
        if thread.posts:
            report.contributors[thread.posts[0].user].threads_started += 1

        for post_index, post in enumerate(thread.posts):
            if post.depth <= 0:
                continue
            target = next(
                (
                    earlier
                    for earlier in reversed(thread.posts[:post_index])
                    if earlier.depth < post.depth
                ),
                None,
            )
            if target is None or target.user == post.user:
                continue
            edge = (post.user, target.user)
            report.reply_edges[edge] = report.reply_edges.get(edge, 0) + 1
            report.contributors[post.user].replies_made += 1
            report.contributors[target.user].replies_received += 1

    ranks = _weighted_pagerank(report.contributors, report.reply_edges)
    for user, rank in ranks.items():
        report.contributors[user].pagerank = rank

    _link_posts_to_article_edits(
        report,
        article_revisions,
        link_window=timedelta(days=link_window_days),
    )
    return report


def _parse_section(
    text: str, thread_title: str, thread_id: int
) -> tuple[list[TalkPost], int]:
    posts: list[TalkPost] = []
    signatures_seen = 0
    cursor = 0

    for timestamp_match in _TIMESTAMP_RE.finditer(text):
        signatures_seen += 1
        chunk = text[cursor : timestamp_match.end()]
        author = _find_signature_author(chunk)
        cursor = timestamp_match.end()
        if author is None:
            continue

        user, signature_start = author
        raw_post = chunk[:signature_start]
        posts.append(
            TalkPost(
                thread_id=thread_id,
                thread_title=thread_title,
                user=user,
                timestamp=_timestamp_from_match(timestamp_match),
                depth=_reply_depth(raw_post),
                text=_clean_post_text(raw_post),
            )
        )

    return posts, signatures_seen


def _find_signature_author(chunk: str) -> tuple[str, int] | None:
    candidates: list[tuple[int, str]] = []
    earliest_signature_start = max(0, len(chunk) - MAX_SIGNATURE_PREFIX_CHARS)
    for pattern in (_USER_LINK_RE, _CONTRIBUTIONS_LINK_RE, _UNSIGNED_RE):
        for match in pattern.finditer(chunk):
            if match.start() >= earliest_signature_start:
                candidates.append((match.start(), match.group("user")))
    if not candidates:
        return None
    start, user = max(candidates, key=lambda candidate: candidate[0])
    return _normalise_user(user), start


def _normalise_user(user: str) -> str:
    return re.sub(r"\s+", " ", user.replace("_", " ")).strip()


def _timestamp_from_match(match: re.Match[str]) -> datetime:
    raw = (
        f"{match.group('day')} {match.group('month')} {match.group('year')} "
        f"{match.group('hour')}:{match.group('minute')}"
    )
    for format_string in ("%d %B %Y %H:%M", "%d %b %Y %H:%M"):
        try:
            return datetime.strptime(raw, format_string).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue
    raise ValueError(f"unsupported talk-page timestamp: {match.group(0)!r}")


def _reply_depth(raw_post: str) -> int:
    for line in reversed(raw_post.splitlines()):
        if line.strip():
            return _colon_depth(line)
    return 0


def _colon_depth(line: str) -> int:
    stripped = line.lstrip()
    return len(stripped) - len(stripped.lstrip(":"))


def _clean_post_text(raw_post: str) -> str:
    lines = [re.sub(r"^\s*:+\s?", "", line) for line in raw_post.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = _WIKILINK_RE.sub(r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip(" -–—~")


def _weighted_pagerank(
    contributors: dict[str, ContributorDiscussion],
    edges: dict[tuple[str, str], int],
    *,
    damping: float = 0.85,
    tolerance: float = 1e-12,
    max_iterations: int = 100,
) -> dict[str, float]:
    users = sorted(contributors)
    if not users:
        return {}

    count = len(users)
    ranks = {user: 1.0 / count for user in users}
    outgoing = {user: 0 for user in users}
    for (source, _target), weight in edges.items():
        outgoing[source] += weight

    for _ in range(max_iterations):
        dangling_share = sum(
            ranks[user] for user in users if outgoing[user] == 0
        ) / count
        updated = {
            user: (1.0 - damping) / count + damping * dangling_share
            for user in users
        }
        for (source, target), weight in edges.items():
            updated[target] += (
                damping * ranks[source] * weight / outgoing[source]
            )
        delta = sum(abs(updated[user] - ranks[user]) for user in users)
        ranks = updated
        if delta < tolerance:
            break

    total = sum(ranks.values())
    return {user: rank / total for user, rank in ranks.items()}


def _link_posts_to_article_edits(
    report: DiscussionReport,
    article_revisions: Iterable[RawRevision],
    *,
    link_window: timedelta,
) -> None:
    revisions_by_user: dict[str, list[tuple[int, datetime]]] = {}
    for revision in article_revisions:
        if not revision.user:
            continue
        timestamp = _revision_timestamp(revision.timestamp)
        if timestamp is None:
            continue
        revisions_by_user.setdefault(_normalise_user(revision.user), []).append(
            (revision.revid, timestamp)
        )

    linked_revision_ids: dict[str, set[int]] = {
        user: set() for user in report.contributors
    }
    for thread in report.threads:
        for post in thread.posts:
            matches = {
                revid
                for revid, timestamp in revisions_by_user.get(post.user, [])
                if timedelta(0) <= timestamp - post.timestamp <= link_window
            }
            if matches:
                report.contributors[post.user].linked_posts += 1
                linked_revision_ids[post.user].update(matches)

    for user, revision_ids in linked_revision_ids.items():
        report.contributors[user].follow_up_edits = len(revision_ids)


def _revision_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
