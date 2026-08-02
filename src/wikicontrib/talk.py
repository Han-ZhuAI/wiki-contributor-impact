"""Talk-page parsing and reply-graph discussion impact.

Wikipedia Talk pages encode conversation structure in wikitext rather than in
a dedicated comment API.  A signed line is a comment, section headings define
threads, and leading ``:``/``*`` markers indicate reply depth.  This module
turns those conventions into an auditable contributor graph:

* comments are recovered from successive Talk-page revisions;
* duplicate comments that persist across revisions are counted once;
* a directed edge runs from the replier to the contributor being answered;
* weighted PageRank therefore rewards contributors whose comments attract
  responses, rather than simply rewarding raw comment volume.

The parser deliberately prefers precision over guessing.  Unsigned prose that
cannot be attributed to a user is ignored; ``{{unsigned|...}}`` annotations
are supported when another editor has supplied the missing attribution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
import re
from typing import Iterable

from .api import RawRevision


LEAD_THREAD = "(lead)"

_HEADING_RE = re.compile(r"^\s*(={2,6})\s*(.*?)\s*\1\s*$")
_USER_LINK_RE = re.compile(
    r"\[\[\s*(?:User|User[ _]talk)\s*:\s*([^|\]#]+)"
    r"(?:#[^|\]]*)?(?:\|[^\]]*)?\]\]",
    re.IGNORECASE,
)
_CONTRIB_LINK_RE = re.compile(
    r"\[\[\s*Special\s*:\s*Contributions\s*/\s*([^|\]]+)"
    r"(?:\|[^\]]*)?\]\]",
    re.IGNORECASE,
)
_UNSIGNED_RE = re.compile(
    r"\{\{\s*unsigned\s*\|\s*([^|}]+)(?:\|([^}]+))?\}\}",
    re.IGNORECASE,
)
_TIMESTAMP_RE = re.compile(
    r"\b(\d{1,2}:\d{2},\s+\d{1,2}\s+[A-Z][a-z]+\s+\d{4}\s+\(UTC\))"
)
_INDENT_RE = re.compile(r"^\s*([:*#]+)\s*")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WIKILINK_RE = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]")


@dataclass(frozen=True)
class TalkComment:
    """One attributable comment recovered from Talk-page wikitext."""

    author: str
    text: str
    thread: str
    depth: int
    timestamp: str = ""
    revid: int | None = None
    order: int = 0

    @property
    def identity(self) -> tuple[str, ...]:
        """Stable key used to deduplicate a comment across page revisions."""
        if self.timestamp:
            return (self.thread, self.author, self.timestamp)
        return (self.thread, self.author, _normalise_space(self.text))


@dataclass
class ContributorDiscussion:
    """Discussion activity and influence for one participant."""

    user: str
    comments: int = 0
    threads_started: int = 0
    replies: int = 0
    replies_received: int = 0
    pagerank: float = 0.0


@dataclass
class DiscussionReport:
    """Talk-page reply graph and per-contributor discussion metrics."""

    comments: list[TalkComment] = field(default_factory=list)
    edges: dict[tuple[str, str], int] = field(default_factory=dict)
    contributors: dict[str, ContributorDiscussion] = field(default_factory=dict)

    def ranked(self, by: str = "pagerank") -> list[ContributorDiscussion]:
        """Return contributors high-to-low by ``by``, with stable name ties."""
        return sorted(
            self.contributors.values(),
            key=lambda contributor: (-getattr(contributor, by), contributor.user),
        )


def parse_talk_page(wikitext: str | None, *, revid: int | None = None) -> list[TalkComment]:
    """Parse signed comments from one Talk-page state.

    A comment may span several lines; it is emitted when a user signature or
    ``{{unsigned|user}}`` annotation is encountered.  Section headings group
    comments into threads and leading indentation markers determine depth.
    """
    if not wikitext:
        return []

    comments: list[TalkComment] = []
    pending: list[str] = []
    thread = LEAD_THREAD

    def flush() -> None:
        nonlocal pending
        if not pending:
            return
        block = "\n".join(pending)
        author, timestamp = _signature(block)
        if author:
            first_content_line = next((line for line in pending if line.strip()), "")
            depth = _indent_depth(first_content_line)
            text = _comment_text(block)
            comments.append(
                TalkComment(
                    author=author,
                    text=text,
                    thread=thread,
                    depth=depth,
                    timestamp=timestamp,
                    revid=revid,
                    order=len(comments),
                )
            )
        pending = []

    for line in wikitext.splitlines():
        heading = _HEADING_RE.match(line)
        if heading:
            flush()
            thread = _plain_text(heading.group(2)) or LEAD_THREAD
            continue

        if not line.strip():
            if pending:
                pending.append(line)
            continue

        pending.append(line)
        if _signature("\n".join(pending))[0]:
            flush()

    flush()
    return comments


def comments_from_history(revisions: Iterable[RawRevision]) -> list[TalkComment]:
    """Recover first-seen comments from chronological Talk-page revisions."""
    comments: list[TalkComment] = []
    seen: set[tuple[str, ...]] = set()
    for revision in revisions:
        for parsed in parse_talk_page(revision.content, revid=revision.revid):
            if parsed.identity in seen:
                continue
            seen.add(parsed.identity)
            comments.append(
                TalkComment(
                    author=parsed.author,
                    text=parsed.text,
                    thread=parsed.thread,
                    depth=parsed.depth,
                    timestamp=parsed.timestamp,
                    revid=parsed.revid,
                    order=len(comments),
                )
            )
    return comments


def build_reply_graph(comments: Iterable[TalkComment]) -> dict[tuple[str, str], int]:
    """Build weighted ``replier -> replied-to`` edges from comment indentation.

    The nearest previous shallower comment is the parent.  An unindented
    follow-up is conservatively attached to the thread starter.  Self-replies
    are excluded because they do not represent interpersonal influence.
    """
    by_thread: dict[str, list[TalkComment]] = {}
    for comment in comments:
        by_thread.setdefault(comment.thread, []).append(comment)

    edges: dict[tuple[str, str], int] = {}
    for thread_comments in by_thread.values():
        if not thread_comments:
            continue
        starter = thread_comments[0]
        stack: dict[int, TalkComment] = {starter.depth: starter}
        for comment in thread_comments[1:]:
            shallower = [depth for depth in stack if depth < comment.depth]
            if shallower:
                parent = stack[max(shallower)]
            else:
                parent = starter

            if comment.author != parent.author:
                edge = (comment.author, parent.author)
                edges[edge] = edges.get(edge, 0) + 1

            stack[comment.depth] = comment
            for depth in [depth for depth in stack if depth > comment.depth]:
                del stack[depth]
    return edges


def weighted_pagerank(
    nodes: Iterable[str],
    edges: dict[tuple[str, str], int],
    *,
    damping: float = 0.85,
    tolerance: float = 1e-12,
    max_iterations: int = 100,
) -> dict[str, float]:
    """Compute deterministic weighted PageRank without an external graph library."""
    node_list = sorted(set(nodes))
    if not node_list:
        return {}
    if not 0.0 < damping < 1.0:
        raise ValueError("damping must be between 0 and 1")
    if tolerance <= 0:
        raise ValueError("tolerance must be positive")
    if max_iterations <= 0:
        raise ValueError("max_iterations must be positive")

    node_set = set(node_list)
    outgoing: dict[str, dict[str, int]] = {node: {} for node in node_list}
    for (source, target), weight in edges.items():
        if source not in node_set or target not in node_set or weight <= 0:
            continue
        outgoing[source][target] = outgoing[source].get(target, 0) + weight

    count = len(node_list)
    scores = {node: 1.0 / count for node in node_list}
    teleport = (1.0 - damping) / count

    for _ in range(max_iterations):
        dangling = sum(scores[node] for node in node_list if not outgoing[node])
        updated = {
            node: teleport + damping * dangling / count for node in node_list
        }
        for source in node_list:
            total_weight = sum(outgoing[source].values())
            if not total_weight:
                continue
            for target, weight in outgoing[source].items():
                updated[target] += damping * scores[source] * weight / total_weight

        delta = sum(abs(updated[node] - scores[node]) for node in node_list)
        scores = updated
        if delta < tolerance:
            break

    # Remove harmless floating-point drift so the public invariant is exact.
    total = sum(scores.values())
    return {node: score / total for node, score in scores.items()}


def analyze_discussion(revisions: Iterable[RawRevision]) -> DiscussionReport:
    """Parse Talk history and calculate activity plus reply-graph PageRank."""
    comments = comments_from_history(revisions)
    edges = build_reply_graph(comments)
    report = DiscussionReport(comments=comments, edges=edges)

    for comment in comments:
        contributor = report.contributors.setdefault(
            comment.author, ContributorDiscussion(user=comment.author)
        )
        contributor.comments += 1

    by_thread: dict[str, list[TalkComment]] = {}
    for comment in comments:
        by_thread.setdefault(comment.thread, []).append(comment)
    for thread_comments in by_thread.values():
        if not thread_comments:
            continue
        report.contributors[thread_comments[0].author].threads_started += 1
        for reply in thread_comments[1:]:
            report.contributors[reply.author].replies += 1

    for (_source, target), weight in edges.items():
        report.contributors[target].replies_received += weight

    scores = weighted_pagerank(report.contributors, edges)
    for user, score in scores.items():
        report.contributors[user].pagerank = score
    return report


def _signature(text: str) -> tuple[str | None, str]:
    """Return ``(author, timestamp)`` for a signed block."""
    unsigned = _UNSIGNED_RE.search(text)
    if unsigned:
        author = _normalise_user(unsigned.group(1))
        timestamp = _normalise_space(unsigned.group(2) or "")
        return (author or None, timestamp)

    timestamp_match = _TIMESTAMP_RE.search(text)
    users = _USER_LINK_RE.findall(text)
    if users and timestamp_match:
        author = _normalise_user(users[0])
        return (author or None, timestamp_match.group(1))

    for candidate in _CONTRIB_LINK_RE.findall(text):
        author = _normalise_user(candidate)
        try:
            ipaddress.ip_address(author)
        except ValueError:
            continue
        if timestamp_match:
            return (author, timestamp_match.group(1))
    return (None, "")


def _comment_text(block: str) -> str:
    """Remove indentation and signature markup while retaining comment prose."""
    unsigned = _UNSIGNED_RE.search(block)
    cut_at = unsigned.start() if unsigned else None
    timestamp = _TIMESTAMP_RE.search(block)
    if timestamp and (cut_at is None or timestamp.start() < cut_at):
        cut_at = timestamp.start()
    if cut_at is not None:
        block = block[:cut_at]

    # A signature user link normally appears immediately before the timestamp.
    user_links = list(_USER_LINK_RE.finditer(block))
    contrib_links = list(_CONTRIB_LINK_RE.finditer(block))
    signature_links = user_links or contrib_links
    if signature_links:
        block = block[: signature_links[0].start()]

    lines = [_INDENT_RE.sub("", line) for line in block.splitlines()]
    return _plain_text(" ".join(lines)).strip(" -–—~")


def _indent_depth(line: str) -> int:
    match = _INDENT_RE.match(line)
    return len(match.group(1)) if match else 0


def _plain_text(text: str) -> str:
    text = _COMMENT_RE.sub("", text)
    text = _TAG_RE.sub("", text)
    text = _WIKILINK_RE.sub(r"\1", text)
    text = re.sub(r"'{2,5}", "", text)
    return _normalise_space(text)


def _normalise_space(text: str) -> str:
    return " ".join(text.replace("_", " ").split())


def _normalise_user(user: str) -> str:
    return _normalise_space(user).strip()
