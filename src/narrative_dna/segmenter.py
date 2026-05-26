"""Narrative unit segmentation entry points."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from narrative_dna.models import NarrativeUnit, ValidatorFlag
from narrative_dna.normalizer import normalize_text
from narrative_dna.notation import compile_notation

DEFAULT_TAXONOMY_VERSION = "v1_0"
DEFAULT_PROMPT_VERSION = "v1_0"
DEFAULT_VALIDATOR_VERSION = "v1_0"
DEFAULT_MAX_UNIT_CHARS = 280

SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?;:])\s+(?=[A-ZÁÉÍÓÚÜÑ¿¡0-9])")
SOFT_BOUNDARY_RE = re.compile(
    r"\s+(?=(?:pero|aunque|porque|entonces|sin embargo|por eso|además|luego|después)\b)",
    re.IGNORECASE,
)
COMMA_BOUNDARY_RE = re.compile(r"(?<=,)\s+")


@dataclass(frozen=True)
class SourceSegment:
    text: str
    start_ms: int | None = None
    end_ms: int | None = None


@dataclass(frozen=True)
class UnitCandidate:
    text: str
    start_ms: int | None = None
    end_ms: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    approximate_timing: bool = False


def segment_transcript(
    *,
    document_id: str,
    text: str | None = None,
    source_segments: list[SourceSegment] | None = None,
    max_unit_chars: int = DEFAULT_MAX_UNIT_CHARS,
    taxonomy_version: str = DEFAULT_TAXONOMY_VERSION,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    validator_version: str = DEFAULT_VALIDATOR_VERSION,
) -> list[NarrativeUnit]:
    """Segment transcript text into unclassified narrative units."""

    if source_segments:
        candidates = _segment_timestamped_sources(source_segments, max_unit_chars=max_unit_chars)
    else:
        candidates = _segment_plain_text(text or "", max_unit_chars=max_unit_chars)

    units = [
        _make_unclassified_unit(
            document_id=document_id,
            sequence_index=index,
            candidate=candidate,
            taxonomy_version=taxonomy_version,
            prompt_version=prompt_version,
            validator_version=validator_version,
        )
        for index, candidate in enumerate(candidates)
    ]
    _link_neighbors(units)
    return units


def _segment_plain_text(text: str, *, max_unit_chars: int) -> list[UnitCandidate]:
    normalized = normalize_text(text)
    pieces = _split_semantic_text(normalized, max_unit_chars=max_unit_chars)
    candidates: list[UnitCandidate] = []
    cursor = 0
    for piece in pieces:
        start = normalized.find(piece, cursor)
        if start == -1:
            start = cursor
        end = start + len(piece)
        candidates.append(UnitCandidate(text=piece, char_start=start, char_end=end))
        cursor = end
    return candidates


def _segment_timestamped_sources(
    source_segments: list[SourceSegment],
    *,
    max_unit_chars: int,
) -> list[UnitCandidate]:
    candidates: list[UnitCandidate] = []
    for source in source_segments:
        text = normalize_text(source.text)
        if not text:
            continue
        pieces = _split_semantic_text(text, max_unit_chars=max_unit_chars)
        approximate = len(pieces) > 1 and source.start_ms is not None and source.end_ms is not None
        for index, piece in enumerate(pieces):
            start_ms, end_ms = _piece_timing(source, index=index, total=len(pieces))
            candidates.append(
                UnitCandidate(
                    text=piece,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    approximate_timing=approximate,
                )
            )
    return candidates


def _split_semantic_text(text: str, *, max_unit_chars: int) -> list[str]:
    pieces = _split_by_regex(normalize_text(text), SENTENCE_BOUNDARY_RE)
    refined: list[str] = []
    for piece in pieces:
        refined.extend(_split_long_piece(piece, max_unit_chars=max_unit_chars))
    return [piece for piece in refined if piece]


def _split_long_piece(piece: str, *, max_unit_chars: int) -> list[str]:
    if len(piece) <= max_unit_chars:
        return [piece]

    for boundary in (SOFT_BOUNDARY_RE, COMMA_BOUNDARY_RE):
        split = _split_by_regex(piece, boundary)
        if len(split) > 1 and max(len(part) for part in split) <= max_unit_chars:
            return split

    words = piece.split()
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        projected = current_len + len(word) + (1 if current else 0)
        if current and projected > max_unit_chars:
            chunks.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len = projected
    if current:
        chunks.append(" ".join(current))
    return chunks


def _split_by_regex(text: str, pattern: re.Pattern[str]) -> list[str]:
    return [part.strip() for part in pattern.split(text) if part.strip()]


def _piece_timing(
    source: SourceSegment,
    *,
    index: int,
    total: int,
) -> tuple[int | None, int | None]:
    if source.start_ms is None or source.end_ms is None or total <= 1:
        return source.start_ms, source.end_ms
    duration = source.end_ms - source.start_ms
    start = source.start_ms + round(duration * index / total)
    end = source.start_ms + round(duration * (index + 1) / total)
    return start, end


def _make_unclassified_unit(
    *,
    document_id: str,
    sequence_index: int,
    candidate: UnitCandidate,
    taxonomy_version: str,
    prompt_version: str,
    validator_version: str,
) -> NarrativeUnit:
    flags: list[dict[str, Any]] = []
    if candidate.approximate_timing:
        flags.append(
            ValidatorFlag(
                rule_id="approximate_timing",
                severity="info",
                message="Timing was interpolated after segment splitting.",
                field="start_ms",
            ).model_dump(mode="json")
        )

    payload: dict[str, Any] = {
        "document_id": document_id,
        "unit_id": f"{document_id}_u{sequence_index:05d}",
        "sequence_index": sequence_index,
        "text": candidate.text,
        "normalized_text": normalize_text(candidate.text).lower(),
        "start_ms": candidate.start_ms,
        "end_ms": candidate.end_ms,
        "char_start": candidate.char_start,
        "char_end": candidate.char_end,
        "previous_unit_id": None,
        "next_unit_id": None,
        "functions": ["N"],
        "primary_function": "N",
        "secondary_functions": [],
        "inherited_functions": [],
        "certainty": "none",
        "emotion_expressed": "N",
        "emotion_intensity": 0,
        "emotions_mentioned": [],
        "stance": "neutral",
        "target": None,
        "speech_act": None,
        "logic": None,
        "evidence_spans": [],
        "rejected_labels": [],
        "validator_flags": flags,
        "heuristic_candidates": [],
        "llm_votes": [],
        "confidence": 0.0,
        "method": "none",
        "needs_review": False,
        "review_reasons": [],
        "review_status": "pending",
        "final_notation": compile_notation(
            {
                "functions": ["N"],
                "certainty": "none",
                "emotion_expressed": "N",
                "emotion_intensity": 0,
                "stance": "neutral",
            }
        ),
        "taxonomy_version": taxonomy_version,
        "prompt_version": prompt_version,
        "validator_version": validator_version,
    }
    return NarrativeUnit.model_validate(payload)


def _link_neighbors(units: list[NarrativeUnit]) -> None:
    for index, unit in enumerate(units):
        unit.previous_unit_id = units[index - 1].unit_id if index > 0 else None
        unit.next_unit_id = units[index + 1].unit_id if index < len(units) - 1 else None
