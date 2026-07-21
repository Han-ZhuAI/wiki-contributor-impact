"""Classifying edits as additive vs. maintenance.

The assignment asks the model to "differentiate between contributions that are
additive as opposed to maintenance." An edit that adds a paragraph of new prose
and an edit that reverts vandalism or fixes a typo are worlds apart in intent,
yet a naive edit count treats them identically. This module assigns each edit a
type so that difference becomes measurable.

Two complementary sources of evidence are combined:

1. **What the diff shows** — net and gross word change and churn
   (:mod:`wikicontrib.diff`). New content is net-positive with low churn;
   reverts, trims and copy-edits are net-negative or high-churn.
2. **What the editor said** — the edit summary. Wikipedians flag maintenance
   explicitly ("rv vandalism", "typo", "ce", "fmt"), and the ``minor`` flag is
   a self-declared "this is not substantive."

The result is a binary :class:`EditType` (the additive/maintenance split the
assignment wants) plus a finer ``reason`` tag, kept because it makes the
classification auditable rather than a black box. This is a deliberately
transparent, rule-based v1; Day 7 hardens the revert detection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from .diff import RevisionDiff


class EditType(str, Enum):
    """The additive-vs-maintenance split at the heart of the model."""

    ADDITIVE = "additive"       # grows the article with new content
    MAINTENANCE = "maintenance"  # reverts, trims, copy-edits, formatting

    @property
    def is_additive(self) -> bool:
        return self is EditType.ADDITIVE


# Edit-summary markers. Wikipedia conventions:
#   https://en.wikipedia.org/wiki/Wikipedia:Edit_summary_legend
# Word-boundary regexes so "rv" does not match "survey" and "ce" does not match
# "cent". Ordered high-confidence (revert) first.
_REVERT_RE = re.compile(
    r"\b(rv|rvv|rvt|revert(?:ed|ing)?|undo|undid|unvandali[sz]e|restore[ds]?)\b",
    re.IGNORECASE,
)
_MAINTENANCE_RE = re.compile(
    r"\b(typo|typos|sp|spelling|grammar|punctuation|ce|copy-?edit(?:ed|ing)?|"
    r"fmt|format(?:ting)?|wikif(?:y|ied)|cleanup|clean-?up|tidy|"
    r"cat|categor(?:y|ies|ise|ize)|link(?:s|ing|fix)?|delink|"
    r"ref(?:s|erence)?|reflink|template|infobox|"
    r"whitespace|spacing|dab|disambig(?:uation)?)\b",
    re.IGNORECASE,
)


@dataclass
class ClassifierConfig:
    """Tunable thresholds for :func:`classify_edit`.

    Kept in one place so Day 14's sensitivity analysis can sweep them without
    touching the rules.
    """

    #: Net word gain at or above which an edit is a substantive expansion.
    additive_net_words: int = 10
    #: Churn at or above which an edit reads as a rewrite (maintenance) even
    #: when a few words were netted.
    high_churn: float = 0.5
    #: Net word loss at or below which an edit is a trim/removal (maintenance).
    trim_net_words: int = -5


@dataclass
class Classification:
    """The outcome of classifying one edit."""

    edit_type: EditType
    reason: str
    signals: dict = field(default_factory=dict)

    @property
    def is_additive(self) -> bool:
        return self.edit_type.is_additive


def strip_section_marker(comment: str) -> str:
    """Remove the ``/* Section */`` auto-prefix from an edit summary.

    Section markers are boilerplate the software inserts, not something the
    editor wrote, so they should not feed keyword matching.

    >>> strip_section_marker("/* Early life */ added birth date")
    'added birth date'
    """
    return re.sub(r"/\*.*?\*/", "", comment or "").strip()


def classify_edit(
    diff: RevisionDiff, config: ClassifierConfig | None = None
) -> Classification:
    """Classify a single edit as additive or maintenance.

    Rules are applied in priority order and the first match wins, so the
    ``reason`` names exactly which rule fired.
    """
    cfg = config or ClassifierConfig()
    comment = strip_section_marker(diff.comment)
    signals = {
        "net_words": diff.net_words,
        "gross_words": diff.gross_words,
        "churn": round(diff.churn, 3),
        "minor": diff.minor,
    }

    def result(edit_type: EditType, reason: str) -> Classification:
        return Classification(edit_type, reason, signals)

    # 1. Explicit revert summaries are the strongest maintenance signal.
    if _REVERT_RE.search(comment):
        return result(EditType.MAINTENANCE, "revert-comment")

    # 2. No words changed: markup/whitespace/formatting only.
    if diff.gross_words == 0:
        return result(EditType.MAINTENANCE, "formatting")

    # 3. Explicit maintenance summaries (typo, ce, fmt, cat, ...).
    if _MAINTENANCE_RE.search(comment):
        return result(EditType.MAINTENANCE, "maintenance-comment")

    # 4. Net removal of text is a trim.
    if diff.net_words <= cfg.trim_net_words:
        return result(EditType.MAINTENANCE, "trim")

    # 5. High churn with little net gain is a rewrite/copy-edit.
    if diff.churn >= cfg.high_churn and diff.net_words < cfg.additive_net_words:
        return result(EditType.MAINTENANCE, "rewrite")

    # 6. Substantive net growth is an expansion.
    if diff.net_words >= cfg.additive_net_words:
        return result(EditType.ADDITIVE, "expansion")

    # 7. Small net-positive edits: additive, unless flagged minor.
    if diff.net_words > 0 and not diff.minor:
        return result(EditType.ADDITIVE, "small-addition")

    return result(EditType.MAINTENANCE, "minor-change")
