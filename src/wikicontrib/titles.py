"""Helpers for MediaWiki page titles and namespaces.

Every content page on Wikipedia has a paired *talk* page where contributors
argue about, propose and agree on changes. That pairing is expressed purely in
the title: the article ``Alan Turing`` is discussed at ``Talk:Alan Turing``,
and the user page ``User:Example`` at ``User talk:Example``.

The discussion-impact metric needs both halves of that pair, so this module
turns a content title into its talk title (and back) without a network call.

Reference: https://www.mediawiki.org/wiki/Manual:Namespace
"""

from __future__ import annotations

#: Subject namespaces that have a distinct talk namespace. The main (article)
#: namespace has no prefix and is handled separately.
SUBJECT_TO_TALK = {
    "User": "User talk",
    "Wikipedia": "Wikipedia talk",
    "File": "File talk",
    "MediaWiki": "MediaWiki talk",
    "Template": "Template talk",
    "Help": "Help talk",
    "Category": "Category talk",
    "Portal": "Portal talk",
    "Draft": "Draft talk",
    "Module": "Module talk",
}

TALK_TO_SUBJECT = {talk: subject for subject, talk in SUBJECT_TO_TALK.items()}

#: The talk namespace paired with the main article namespace.
MAIN_TALK_PREFIX = "Talk"


def split_namespace(title: str) -> tuple[str | None, str]:
    """Split ``title`` into ``(namespace, rest)``.

    Returns ``(None, title)`` for main-namespace pages. Only recognised
    namespaces are split off, so a title like ``"Apollo 11: The Movie"`` keeps
    its colon and stays in the main namespace.
    """
    if ":" not in title:
        return None, title
    prefix, rest = title.split(":", 1)
    prefix = prefix.strip()
    rest = rest.strip()
    known = set(SUBJECT_TO_TALK) | set(TALK_TO_SUBJECT) | {MAIN_TALK_PREFIX}
    if prefix in known:
        return prefix, rest
    return None, title


def is_talk_title(title: str) -> bool:
    """True if ``title`` already refers to a talk page."""
    namespace, _ = split_namespace(title)
    if namespace is None:
        return False
    return namespace == MAIN_TALK_PREFIX or namespace in TALK_TO_SUBJECT


def talk_title(title: str) -> str:
    """Return the talk page title paired with ``title``.

    Idempotent: passing a talk title returns it unchanged.

    >>> talk_title("Alan Turing")
    'Talk:Alan Turing'
    >>> talk_title("User:Example")
    'User talk:Example'
    >>> talk_title("Talk:Alan Turing")
    'Talk:Alan Turing'
    """
    if is_talk_title(title):
        return title
    namespace, rest = split_namespace(title)
    if namespace is None:
        return f"{MAIN_TALK_PREFIX}:{title.strip()}"
    return f"{SUBJECT_TO_TALK[namespace]}:{rest}"


def subject_title(title: str) -> str:
    """Return the content page paired with a talk ``title``.

    Idempotent: passing a subject title returns it unchanged.

    >>> subject_title("Talk:Alan Turing")
    'Alan Turing'
    >>> subject_title("User talk:Example")
    'User:Example'
    """
    if not is_talk_title(title):
        return title
    namespace, rest = split_namespace(title)
    if namespace == MAIN_TALK_PREFIX:
        return rest
    return f"{TALK_TO_SUBJECT[namespace]}:{rest}"
