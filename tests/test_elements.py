"""Tests for semantic wikitext element classification and deltas."""

from wikicontrib.api import RawRevision
from wikicontrib.elements import (
    WikitextElement,
    aggregate_element_history,
    classify_wikitext,
    diff_wikitext_elements,
)


def _by_element(text):
    result = {}
    for token in classify_wikitext(text):
        result.setdefault(token.element, []).append(token.value)
    return result


def _revision(revid, content, user="Alice"):
    return RawRevision(
        revid=revid,
        parentid=revid - 1,
        timestamp=f"2020-01-{revid:02d}T00:00:00Z",
        user=user,
        userid=1,
        comment="",
        size=len(content),
        minor=False,
        anon=False,
        content=content,
    )


def test_classifies_all_supported_wikitext_elements():
    text = """Lead prose words.
== Early life ==
See [[Alan Turing|Turing]].
{{Infobox person|name=Alan}}
Claim.<ref>Reliable source</ref>
{| class="wikitable"
| table cell
|}
[[Category:British mathematicians]]
"""
    grouped = _by_element(text)
    assert grouped[WikitextElement.PROSE] == ["Lead", "prose", "words", "See", "Claim"]
    assert grouped[WikitextElement.HEADING] == ["Early", "life"]
    assert grouped[WikitextElement.LINK] == ["Alan", "Turing", "Turing"]
    assert grouped[WikitextElement.TEMPLATE] == ["Infobox", "person", "name", "Alan"]
    assert grouped[WikitextElement.REFERENCE] == ["ref", "Reliable", "source", "ref"]
    assert grouped[WikitextElement.TABLE] == ["class", "wikitable", "table", "cell"]
    assert grouped[WikitextElement.CATEGORY] == [
        "Category",
        "British",
        "mathematicians",
    ]


def test_nested_link_inside_reference_is_not_double_counted():
    grouped = _by_element("Text<ref>See [[Source title]]</ref>")
    assert grouped[WikitextElement.PROSE] == ["Text"]
    assert grouped[WikitextElement.REFERENCE] == [
        "ref",
        "See",
        "Source",
        "title",
        "ref",
    ]
    assert WikitextElement.LINK not in grouped


def test_comments_are_ignored():
    tokens = classify_wikitext("Visible <!-- hidden words --> prose")
    assert [token.value for token in tokens] == ["Visible", "prose"]


def test_external_links_are_classified_as_links():
    grouped = _by_element("Read [https://example.org reliable source]")
    assert grouped[WikitextElement.PROSE] == ["Read"]
    assert grouped[WikitextElement.LINK] == [
        "https",
        "example",
        "org",
        "reliable",
        "source",
    ]


def test_element_diff_detects_additions_and_context_moves():
    delta = diff_wikitext_elements("Alpha", "== Alpha ==\nNew prose")
    assert delta.removed[WikitextElement.PROSE] == 1
    assert delta.added[WikitextElement.HEADING] == 1
    assert delta.added[WikitextElement.PROSE] == 2


def test_history_aggregates_element_deltas_by_contributor():
    report = aggregate_element_history(
        [
            _revision(1, "Lead text", "Alice"),
            _revision(2, "Lead text\n== History ==", "Bob"),
            _revision(3, "Lead text\n== History ==\n<ref>Book</ref>", "Alice"),
        ]
    )
    assert report.contributors["Alice"].delta.added[WikitextElement.PROSE] == 2
    assert report.contributors["Alice"].delta.added[WikitextElement.REFERENCE] == 3
    assert report.contributors["Bob"].delta.added[WikitextElement.HEADING] == 1
    assert report.total.added[WikitextElement.HEADING] == 1


def test_unclosed_template_is_classified_conservatively_to_end():
    grouped = _by_element("Before {{cite web|title=Source")
    assert grouped[WikitextElement.PROSE] == ["Before"]
    assert grouped[WikitextElement.TEMPLATE] == ["cite", "web", "title", "Source"]
