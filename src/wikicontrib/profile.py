"""Unified per-contributor feature profiles.

The model's dimensions deliberately remain separate: writing a large amount,
doing maintenance, leaving persistent text, and influencing a Talk-page
discussion are different behaviours.  This module joins their reports by user
and exposes both the raw evidence and four normalised profile axes.

Normalisation is transparent and article-local:

* ``volume`` is log-max-normalised gross words touched;
* ``additive`` is the share of article edits classified as additive;
* ``persistence`` is log-max-normalised words surviving in the final state;
* ``discussion`` is max-normalised reply-graph PageRank.

Log scaling keeps one prolific editor from flattening every other contributor
on a profile chart.  No weighted total is calculated here: choosing weights
and explaining a composite impact score belongs to the next model stage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import log1p

from .api import RawRevision
from .discussion import DiscussionReport, analyze_discussion
from .metrics import VolumeReport, aggregate_history
from .persistence import PersistenceReport, track_persistence


@dataclass(frozen=True)
class ContributorProfile:
    """Raw metrics and normalised axes for one contributor."""

    user: str

    # Article activity and contribution type.
    article_edits: int = 0
    words_added: int = 0
    words_removed: int = 0
    gross_words: int = 0
    net_words: int = 0
    additive_edits: int = 0
    maintenance_edits: int = 0
    maintenance_ratio: float = 0.0

    # Token provenance / persistence.
    words_introduced: int = 0
    words_surviving: int = 0
    survival_rate: float = 0.0

    # Talk-page activity and influence.
    talk_posts: int = 0
    threads_started: int = 0
    replies_made: int = 0
    replies_received: int = 0
    discussion_pagerank: float = 0.0
    follow_up_edits: int = 0

    # Comparable 0..1 feature axes.
    volume_score: float = 0.0
    additive_score: float = 0.0
    persistence_score: float = 0.0
    discussion_score: float = 0.0

    @property
    def feature_vector(self) -> dict[str, float]:
        """Named four-dimensional vector, ready for scoring or visualisation."""
        return {
            "volume": self.volume_score,
            "additive": self.additive_score,
            "persistence": self.persistence_score,
            "discussion": self.discussion_score,
        }

    @property
    def participation_scope(self) -> str:
        """Whether the user appears in article history, Talk history, or both."""
        in_article = self.article_edits > 0
        in_talk = self.talk_posts > 0
        if in_article and in_talk:
            return "article+talk"
        if in_article:
            return "article"
        if in_talk:
            return "talk"
        return "none"


@dataclass
class ProfileReport:
    """Unified feature profiles for every observed contributor."""

    contributors: dict[str, ContributorProfile] = field(default_factory=dict)

    def ranked(self, by: str = "volume_score") -> list[ContributorProfile]:
        """Rank by one explicit field; this is not a composite-impact ranking."""
        return sorted(
            self.contributors.values(),
            key=lambda profile: (-getattr(profile, by), profile.user),
        )

    @property
    def feature_matrix(self) -> list[dict[str, str | float]]:
        """Deterministic row representation suitable for pandas/JSON later."""
        return [
            {"user": user, **self.contributors[user].feature_vector}
            for user in sorted(self.contributors)
        ]


def build_profiles(
    article_revisions: list[RawRevision],
    talk_revisions: list[RawRevision] | None = None,
) -> ProfileReport:
    """Run all implemented metric pipelines and assemble contributor profiles."""
    volume = aggregate_history(article_revisions)
    persistence = track_persistence(article_revisions)
    discussion = analyze_discussion(talk_revisions or [], article_revisions)
    return assemble_profiles(volume, persistence, discussion)


def assemble_profiles(
    volume: VolumeReport,
    persistence: PersistenceReport,
    discussion: DiscussionReport,
) -> ProfileReport:
    """Join precomputed reports and normalise each feature dimension."""
    users = (
        set(volume.contributors)
        | set(persistence.contributors)
        | set(discussion.contributors)
    )
    if not users:
        return ProfileReport()

    max_gross_words = max(
        (contributor.gross_words for contributor in volume.contributors.values()),
        default=0,
    )
    max_surviving_words = max(
        (
            contributor.words_surviving
            for contributor in persistence.contributors.values()
        ),
        default=0,
    )
    max_pagerank = max(
        (contributor.pagerank for contributor in discussion.contributors.values()),
        default=0.0,
    )

    profiles: dict[str, ContributorProfile] = {}
    for user in sorted(users):
        volume_metrics = volume.contributors.get(user)
        persistence_metrics = persistence.contributors.get(user)
        discussion_metrics = discussion.contributors.get(user)

        article_edits = volume_metrics.edits if volume_metrics else 0
        gross_words = volume_metrics.gross_words if volume_metrics else 0
        words_surviving = (
            persistence_metrics.words_surviving if persistence_metrics else 0
        )
        pagerank = discussion_metrics.pagerank if discussion_metrics else 0.0

        profiles[user] = ContributorProfile(
            user=user,
            article_edits=article_edits,
            words_added=volume_metrics.words_added if volume_metrics else 0,
            words_removed=volume_metrics.words_removed if volume_metrics else 0,
            gross_words=gross_words,
            net_words=volume_metrics.net_words if volume_metrics else 0,
            additive_edits=volume_metrics.additive_edits if volume_metrics else 0,
            maintenance_edits=(
                volume_metrics.maintenance_edits if volume_metrics else 0
            ),
            maintenance_ratio=(
                volume_metrics.maintenance_ratio if volume_metrics else 0.0
            ),
            words_introduced=(
                persistence_metrics.words_introduced if persistence_metrics else 0
            ),
            words_surviving=words_surviving,
            survival_rate=(
                persistence_metrics.survival_rate if persistence_metrics else 0.0
            ),
            talk_posts=discussion_metrics.posts if discussion_metrics else 0,
            threads_started=(
                discussion_metrics.threads_started if discussion_metrics else 0
            ),
            replies_made=(
                discussion_metrics.replies_made if discussion_metrics else 0
            ),
            replies_received=(
                discussion_metrics.replies_received if discussion_metrics else 0
            ),
            discussion_pagerank=pagerank,
            follow_up_edits=(
                discussion_metrics.follow_up_edits if discussion_metrics else 0
            ),
            volume_score=_log_max_normalise(gross_words, max_gross_words),
            additive_score=(
                1.0 - volume_metrics.maintenance_ratio
                if volume_metrics and article_edits
                else 0.0
            ),
            persistence_score=_log_max_normalise(
                words_surviving, max_surviving_words
            ),
            discussion_score=(pagerank / max_pagerank if max_pagerank else 0.0),
        )

    return ProfileReport(contributors=profiles)


def _log_max_normalise(value: int, maximum: int) -> float:
    """Map a non-negative count to 0..1 with log scaling and a max anchor."""
    if value <= 0 or maximum <= 0:
        return 0.0
    return log1p(value) / log1p(maximum)
