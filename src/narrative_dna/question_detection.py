"""Shared question-anchor detection helpers."""

from __future__ import annotations

from collections.abc import Iterable

INVERTED_QUESTION_MARK = "\u00bf"
MOJIBAKE_INVERTED_QUESTION_MARK = "\u00c2\u00bf"
CLOSING_AFTER_QUESTION = set(")]}\"'")


def has_question_anchor(
    text: str,
    *,
    previous_text: str | None = None,
    relation_types: Iterable[str] | None = None,
) -> bool:
    """Return true when text or local context contains a real question anchor."""

    relation_set = {relation.upper() for relation in relation_types or []}
    return (
        find_question_anchor_span(text) is not None
        or (previous_text is not None and find_question_anchor_span(previous_text) is not None)
        or "ANS" in relation_set
    )


def find_question_anchor_span(text: str) -> tuple[int, int] | None:
    """Find question punctuation without treating mojibake inside words as a question."""

    if not text:
        return None
    inverted_index = text.find(INVERTED_QUESTION_MARK)
    if inverted_index >= 0:
        return inverted_index, inverted_index + 1
    mojibake_index = text.find(MOJIBAKE_INVERTED_QUESTION_MARK)
    if mojibake_index >= 0:
        return mojibake_index, mojibake_index + len(MOJIBAKE_INVERTED_QUESTION_MARK)

    for index, char in enumerate(text):
        if char != "?":
            continue
        if _is_embedded_replacement_marker(text, index):
            continue
        if _looks_like_question_boundary(text, index):
            return index, index + 1
    return None


def _is_embedded_replacement_marker(text: str, index: int) -> bool:
    previous_char = text[index - 1] if index > 0 else ""
    next_char = text[index + 1] if index + 1 < len(text) else ""
    return bool(_is_word_char(previous_char) and _is_word_char(next_char))


def _looks_like_question_boundary(text: str, index: int) -> bool:
    before = text[:index].rstrip()
    after = text[index + 1 :].lstrip()
    if not before:
        return bool(after and (after[0].isupper() or after[0].isdigit()))
    if not after:
        return True
    next_char = after[0]
    return (
        next_char in CLOSING_AFTER_QUESTION
        or next_char.isupper()
        or next_char.isdigit()
        or next_char in {INVERTED_QUESTION_MARK, "\u00a1"}
        or after.startswith(MOJIBAKE_INVERTED_QUESTION_MARK)
    )


def _is_word_char(char: str) -> bool:
    return bool(char and (char.isalnum() or char == "_"))
