"""Tests for wikitext tokenisation."""

import pytest

from wikicontrib.tokenize import count_words, is_word, tokenize, word_tokens


def test_plain_sentence():
    assert tokenize("Alan Turing was a mathematician.") == [
        "Alan", "Turing", "was", "a", "mathematician", ".",
    ]


def test_empty_and_none():
    assert tokenize("") == []
    assert tokenize(None) == []
    assert count_words(None) == 0


def test_whitespace_is_discarded():
    # Re-wrapping a paragraph must not look like a change.
    assert tokenize("one two") == tokenize("one\n\n   two") == ["one", "two"]


def test_markup_becomes_symbol_tokens():
    assert tokenize("[[Link]]") == ["[", "[", "Link", "]", "]"]
    assert word_tokens("[[Link]]") == ["Link"]


def test_markup_is_not_counted_as_prose():
    plain = "Turing was a mathematician"
    marked = "[[Turing]] was a ''mathematician''"
    # Same prose, very different markup -> identical word count.
    assert count_words(plain) == count_words(marked) == 4


def test_template_syntax_contributes_no_words_beyond_its_text():
    assert word_tokens("{{cite|title=X}}") == ["cite", "title", "X"]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Turing's", ["Turing's"]),          # apostrophe kept inside a word
        ("well-known", ["well-known"]),      # hyphen kept inside a word
        ("Turing’s", ["Turing’s"]),          # curly apostrophe too
    ],
)
def test_intra_word_punctuation_is_kept(text, expected):
    assert word_tokens(text) == expected


def test_unicode_words_are_tokenised():
    assert word_tokens("图灵 was a 数学家") == ["图灵", "was", "a", "数学家"]
    assert word_tokens("Gödel Écriture") == ["Gödel", "Écriture"]


def test_digits_count_as_words():
    assert word_tokens("born in 1912") == ["born", "in", "1912"]


@pytest.mark.parametrize(
    "token, expected",
    [("Turing", True), ("1912", True), ("图灵", True),
     ("[", False), ("|", False), ("", False), ("_", False)],
)
def test_is_word(token, expected):
    assert is_word(token) is expected


def test_count_words_matches_word_tokens():
    text = "[[Alan Turing]] (1912-1954) was a British {{nowrap|mathematician}}."
    assert count_words(text) == len(word_tokens(text))
