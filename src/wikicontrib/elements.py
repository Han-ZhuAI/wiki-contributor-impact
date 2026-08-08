"""Semantic wikitext element classification and per-revision deltas.

Word-level volume alone treats a prose sentence and a template parameter as
equivalent.  This module adds an orthogonal, auditable view of *where* changed
words occur: prose, headings, references, templates, tables, categories, or
links.  Markup punctuation is excluded, keeping the counts comparable with the
existing word-level diff metrics.

The classifier is deliberately conservative and dependency-free.  It marks
balanced MediaWiki constructs and applies a documented precedence for nested
content: comments are ignored, then references, templates, tables,
categories/links, headings, and finally prose.  For example, a link inside a
reference is credited to the reference rather than double-counted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum

from .api import RawRevision
from .tokenize import is_word, tokenize


class WikitextElement(str, Enum):
    """Mutually exclusive semantic locations for wikitext word tokens."""

    PROSE = "prose"
    HEADING = "heading"
    REFERENCE = "reference"
    TEMPLATE = "template"
    TABLE = "table"
    CATEGORY = "category"
    LINK = "link"


ELEMENTS = tuple(WikitextElement)


@dataclass(frozen=True)
class ElementToken:
    """One word token paired with its semantic wikitext location."""

    value: str
    element: WikitextElement


def _zero_counts() -> dict[WikitextElement, int]:
    return {element: 0 for element in ELEMENTS}


@dataclass
class ElementDelta:
    """Added and removed word counts for every semantic element."""

    added: dict[WikitextElement, int] = field(default_factory=_zero_counts)
    removed: dict[WikitextElement, int] = field(default_factory=_zero_counts)

    def net(self, element: WikitextElement) -> int:
        return self.added[element] - self.removed[element]

    def as_dict(self) -> dict[str, dict[str, int]]:
        return {
            element.value: {
                "added": self.added[element],
                "removed": self.removed[element],
                "net": self.net(element),
            }
            for element in ELEMENTS
        }

    def accumulate(self, other: ElementDelta) -> None:
        for element in ELEMENTS:
            self.added[element] += other.added[element]
            self.removed[element] += other.removed[element]


@dataclass
class ContributorElements:
    """Semantic element changes attributed to one contributor."""

    user: str
    delta: ElementDelta = field(default_factory=ElementDelta)


@dataclass
class ElementReport:
    """Article-wide and per-contributor semantic wikitext deltas."""

    contributors: dict[str, ContributorElements] = field(default_factory=dict)
    total: ElementDelta = field(default_factory=ElementDelta)


_COMMENT_RE = re.compile(r"<!--.*?(?:-->|\Z)", re.DOTALL)
_REF_RE = re.compile(
    r"<ref\b[^>]*(?:/>|>.*?(?:</ref\s*>|\Z))",
    re.IGNORECASE | re.DOTALL,
)
_TABLE_RE = re.compile(r"(?ms)^\{\|.*?(?:^\|\}[^\n]*$|\Z)")
_HEADING_RE = re.compile(r"(?m)^(={2,6})[ \t]*(.*?)[ \t]*\1[ \t]*$")
_EXTERNAL_LINK_RE = re.compile(r"\[(?:https?:)?//[^\]\n]+\]", re.IGNORECASE)


def classify_wikitext(text: str | None) -> list[ElementToken]:
    """Return word tokens labelled by semantic wikitext element.

    Each word receives exactly one label, so element totals never double-count.
    Comments and markup punctuation are omitted.
    """
    if not text:
        return []

    labels: list[WikitextElement | None] = [WikitextElement.PROSE] * len(text)
    priorities = [0] * len(text)

    def mark(
        start: int, end: int, label: WikitextElement | None, priority: int
    ) -> None:
        for index in range(max(0, start), min(len(text), end)):
            if priority >= priorities[index]:
                labels[index] = label
                priorities[index] = priority

    for match in _COMMENT_RE.finditer(text):
        mark(match.start(), match.end(), None, 100)
    for match in _REF_RE.finditer(text):
        mark(match.start(), match.end(), WikitextElement.REFERENCE, 90)
    for start, end in _balanced_spans(text, "{{", "}}"):
        mark(start, end, WikitextElement.TEMPLATE, 80)
    for match in _TABLE_RE.finditer(text):
        mark(match.start(), match.end(), WikitextElement.TABLE, 70)
    for start, end in _balanced_spans(text, "[[", "]]"):
        inner = text[start + 2 : end - 2].lstrip()
        element = (
            WikitextElement.CATEGORY
            if inner.casefold().startswith("category:")
            else WikitextElement.LINK
        )
        mark(start, end, element, 60)
    for match in _EXTERNAL_LINK_RE.finditer(text):
        mark(match.start(), match.end(), WikitextElement.LINK, 60)
    for match in _HEADING_RE.finditer(text):
        mark(match.start(2), match.end(2), WikitextElement.HEADING, 50)

    result: list[ElementToken] = []
    cursor = 0
    for token in tokenize(text):
        start = text.find(token, cursor)
        if start < 0:  # pragma: no cover - tokenize preserves source order
            continue
        cursor = start + len(token)
        label = labels[start]
        if label is not None and is_word(token):
            result.append(ElementToken(token, label))
    return result


def diff_wikitext_elements(before: str | None, after: str | None) -> ElementDelta:
    """Measure semantic word-token changes between two article states."""
    old = classify_wikitext(before)
    new = classify_wikitext(after)
    delta = ElementDelta()
    matcher = SequenceMatcher(a=old, b=new, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            for token in old[i1:i2]:
                delta.removed[token.element] += 1
        if tag in ("replace", "insert"):
            for token in new[j1:j2]:
                delta.added[token.element] += 1
    return delta


def aggregate_element_history(revisions: list[RawRevision]) -> ElementReport:
    """Aggregate semantic wikitext deltas by contributor and article."""
    report = ElementReport()
    previous_text: str | None = None
    for revision in revisions:
        delta = diff_wikitext_elements(previous_text, revision.content)
        user = revision.user or "(hidden)"
        contributor = report.contributors.setdefault(user, ContributorElements(user))
        contributor.delta.accumulate(delta)
        report.total.accumulate(delta)
        previous_text = revision.content
    return report


def _balanced_spans(text: str, opener: str, closer: str) -> list[tuple[int, int]]:
    """Find outermost balanced spans, conservatively extending unclosed ones."""
    spans: list[tuple[int, int]] = []
    depth = 0
    start = 0
    index = 0
    while index < len(text):
        if text.startswith(opener, index):
            if depth == 0:
                start = index
            depth += 1
            index += len(opener)
            continue
        if depth and text.startswith(closer, index):
            depth -= 1
            index += len(closer)
            if depth == 0:
                spans.append((start, index))
            continue
        index += 1
    if depth:
        spans.append((start, len(text)))
    return spans
