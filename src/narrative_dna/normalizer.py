"""Deterministic transcript normalization helpers."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Mapping
from typing import Any

INVISIBLE_CHARS_RE = re.compile(r"[\u200b\u200c\u200d\ufeff\u2060]")
WHITESPACE_RE = re.compile(r"\s+")

CHAR_REPLACEMENTS = str.maketrans(
    {
        "\u00a0": " ",
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u2026": "...",
    }
)


def normalize_text(text: str) -> str:
    """Normalize transcript text without changing its narrative content."""

    normalized = unicodedata.normalize("NFKC", str(text))
    normalized = normalized.translate(CHAR_REPLACEMENTS)
    normalized = INVISIBLE_CHARS_RE.sub("", normalized)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = WHITESPACE_RE.sub(" ", normalized)
    return normalized.strip()


def normalize_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return metadata as a plain JSON-compatible mapping."""

    if not metadata:
        return {}
    return dict(metadata)


def stable_document_id(
    *,
    source_path: str | None = None,
    content: str | bytes | None = None,
    prefix: str = "doc",
) -> str:
    """Build a stable identifier from source identity and transcript content."""

    digest = hashlib.sha256()
    if source_path:
        digest.update(source_path.replace("\\", "/").encode("utf-8"))
    if content is not None:
        if isinstance(content, str):
            content = content.encode("utf-8")
        digest.update(content)
    return f"{prefix}_{digest.hexdigest()[:16]}"
