"""Tokenisation of wikitext into comparable units.

Measuring "how much did this person contribute" requires a unit to count. Raw
byte size — the figure the API hands us for free — is a poor one: it swings
wildly when someone reformats a table or fixes an encoding, while a carefully
written sentence and an equally long block of template syntax count the same.

So the model counts **word tokens** instead, and keeps punctuation/markup as
separate tokens so a diff can be precise without those symbols inflating a
contributor's word count.

Two token classes
-----------------
* **word** — a run of letters/digits (Unicode-aware, so non-English articles
  tokenise correctly). These are what volume metrics count.
* **symbol** — anything else non-whitespace: brackets, pipes, braces, quotes.
  Wiki markup (``[[link]]``, ``{{template}}``, ``''italic''``) is built from
  these, so heavy markup churn is visible to the diff but never counted as
  prose.

Whitespace is discarded: re-wrapping a paragraph must not register as a change.
"""

from __future__ import annotations

import re

#: A word is a Unicode letter/digit run. Apostrophes and hyphens *inside* a word
#: are kept ("Turing's", "well-known") because splitting them would make trivial
#: copy-edits look like large rewrites.
_TOKEN_RE = re.compile(
    r"""
    (?P<word>[^\W_]+(?:['’\-][^\W_]+)*)   # word, optionally hyphen/apostrophe-joined
    | (?P<symbol>\S)                       # any other non-space character
    """,
    re.UNICODE | re.VERBOSE,
)

_WORD_RE = re.compile(r"^[^\W_]", re.UNICODE)


def tokenize(text: str | None) -> list[str]:
    """Split ``text`` into word and symbol tokens, discarding whitespace.

    >>> tokenize("Alan Turing was a mathematician.")
    ['Alan', 'Turing', 'was', 'a', 'mathematician', '.']
    >>> tokenize("[[Alan Turing]]")
    ['[', '[', 'Alan', 'Turing', ']', ']']
    """
    if not text:
        return []
    return [m.group(0) for m in _TOKEN_RE.finditer(text)]


def is_word(token: str) -> bool:
    """True if ``token`` is a word rather than punctuation or markup.

    >>> is_word("Turing"), is_word("[")
    (True, False)
    """
    return bool(token) and bool(_WORD_RE.match(token))


def word_tokens(text: str | None) -> list[str]:
    """Tokenise ``text`` and keep only the words.

    >>> word_tokens("[[Alan Turing]] was a ''mathematician''.")
    ['Alan', 'Turing', 'was', 'a', 'mathematician']
    """
    return [t for t in tokenize(text) if is_word(t)]


def count_words(text: str | None) -> int:
    """Number of word tokens in ``text``.

    >>> count_words("Alan Turing was a mathematician.")
    5
    """
    return len(word_tokens(text))
