"""Transcript loading entry points."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from narrative_dna.models import NarrativeDocument, SegmentationInfo
from narrative_dna.normalizer import normalize_metadata, normalize_text, stable_document_id
from narrative_dna.segmenter import SourceSegment, segment_transcript

SUPPORTED_SUFFIXES = {".txt", ".json", ".jsonl"}


class TranscriptLoadError(ValueError):
    """Raised when a transcript file cannot be loaded as a document."""


def load_document(path: str | Path) -> NarrativeDocument:
    """Load exactly one transcript document from a file path."""

    documents = load_documents(path)
    if len(documents) != 1:
        raise TranscriptLoadError(f"expected exactly one document, loaded {len(documents)}")
    return documents[0]


def load_text_document(
    text: str,
    *,
    document_id: str | None = None,
    source_path: str = "<text>",
    metadata: dict[str, Any] | None = None,
    language: str = "und",
) -> NarrativeDocument:
    """Build one transcript document directly from an in-memory text string."""

    normalized = normalize_text(text)
    if not normalized:
        raise TranscriptLoadError("text transcript must not be empty")
    normalized_metadata = normalize_metadata(metadata)
    effective_document_id = (
        document_id
        or _document_id_from_metadata(normalized_metadata)
        or stable_document_id(source_path=source_path, content=normalized)
    )
    return _build_document(
        path=Path(source_path),
        source_path=source_path,
        source_type="txt",
        document_id=effective_document_id,
        text=normalized,
        metadata=normalized_metadata,
        language=language,
    )


def load_documents(path: str | Path, *, limit: int | None = None) -> list[NarrativeDocument]:
    """Load supported transcript files from a file or directory."""

    source = Path(path)
    if source.is_dir():
        documents: list[NarrativeDocument] = []
        for transcript_path in _iter_transcript_files(source):
            documents.extend(load_documents(transcript_path))
            if limit is not None and len(documents) >= limit:
                return documents[:limit]
        return documents

    if source.suffix.lower() == ".txt":
        return [_load_txt(source)]
    if source.suffix.lower() == ".json":
        return [_load_json(source)]
    if source.suffix.lower() == ".jsonl":
        return _load_jsonl(source)
    raise TranscriptLoadError(f"unsupported transcript format: {source}")


def _load_txt(path: Path) -> NarrativeDocument:
    text = normalize_text(path.read_text(encoding="utf-8"))
    metadata = _load_sidecar_metadata(path)
    document_id = _document_id_from_metadata(metadata) or stable_document_id(
        source_path=str(path.resolve()), content=text
    )
    return _build_document(
        path=path,
        source_type="txt",
        document_id=document_id,
        text=text,
        metadata=metadata,
        language=_language_from_metadata(metadata),
    )


def _load_json(path: Path) -> NarrativeDocument:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TranscriptLoadError(f"JSON transcript must be an object: {path}")
    metadata = normalize_metadata(payload.get("metadata"))
    metadata.update(_load_sidecar_metadata(path, include_if_same_file=False))
    document_id = str(
        payload.get("document_id")
        or _document_id_from_metadata(metadata)
        or stable_document_id(
            source_path=str(path.resolve()),
            content=json.dumps(payload, sort_keys=True),
        )
    )
    segments = _segments_from_payload(payload.get("segments"))
    text = normalize_text(str(payload.get("transcript") or payload.get("text") or ""))
    if not text and not segments:
        raise TranscriptLoadError(f"JSON transcript needs transcript/text or segments: {path}")
    return _build_document(
        path=path,
        source_type="json",
        document_id=document_id,
        text=text,
        segments=segments,
        metadata=metadata,
        language=str(payload.get("language") or _language_from_metadata(metadata)),
    )


def _load_jsonl(path: Path) -> list[NarrativeDocument]:
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if not rows:
        raise TranscriptLoadError(f"empty JSONL transcript: {path}")
    if not all(isinstance(row, dict) for row in rows):
        raise TranscriptLoadError(f"JSONL rows must be objects: {path}")

    if _looks_like_segment_jsonl(rows):
        metadata = _load_sidecar_metadata(path)
        document_id = str(
            rows[0].get("document_id")
            or rows[0].get("video_id")
            or _document_id_from_metadata(metadata)
            or stable_document_id(source_path=str(path.resolve()), content=path.read_bytes())
        )
        return [
            _build_document(
                path=path,
                source_type="jsonl",
                document_id=document_id,
                segments=_segments_from_payload(rows),
                metadata=metadata,
                language=_language_from_metadata(metadata),
            )
        ]

    documents: list[NarrativeDocument] = []
    for index, row in enumerate(rows):
        metadata = normalize_metadata(row.get("metadata"))
        document_id = str(
            row.get("document_id")
            or stable_document_id(
                source_path=f"{path.resolve()}#{index}",
                content=json.dumps(row, sort_keys=True),
            )
        )
        documents.append(
            _build_document(
                path=path,
                source_type="jsonl",
                document_id=document_id,
                text=normalize_text(str(row.get("transcript") or row.get("text") or "")),
                segments=_segments_from_payload(row.get("segments")),
                metadata=metadata,
                language=str(row.get("language") or _language_from_metadata(metadata)),
            )
        )
    return documents


def _build_document(
    *,
    path: Path,
    source_path: str | None = None,
    source_type: str,
    document_id: str,
    metadata: dict[str, Any],
    language: str,
    text: str = "",
    segments: list[SourceSegment] | None = None,
) -> NarrativeDocument:
    units = segment_transcript(
        document_id=document_id,
        text=text,
        source_segments=segments,
    )
    normalized_text = text or " ".join(segment.text for segment in segments or [])
    return NarrativeDocument.model_validate(
        {
            "document_id": document_id,
            "source_path": source_path or str(path.resolve()),
            "source_type": source_type,
            "language": language or "und",
            "metadata": metadata,
            "segmentation": SegmentationInfo(
                strategy="rule_semantic_v1",
                unit_count=len(units),
                notes=[
                    "unclassified_units",
                    "json_first_loader",
                    "timestamped_segments" if segments else "plain_text_offsets",
                ],
            ).model_dump(mode="json"),
            "units": [unit.model_dump(mode="json") for unit in units],
            "relations": [],
            "chains": [],
            "document_metrics": {
                "unit_count": len(units),
                "char_count": len(normalize_text(normalized_text)),
                "has_timestamps": bool(segments),
            },
            "audit_summary": {
                "taxonomy_version_effective": "v1_0",
                "prompt_version_effective": "v1_0",
                "validator_version_effective": "v1_0",
                "unclassified_unit_count": len(units),
            },
        }
    )


def _segments_from_payload(payload: Any) -> list[SourceSegment]:
    if not payload:
        return []
    if not isinstance(payload, list):
        raise TranscriptLoadError("segments must be a list")
    segments: list[SourceSegment] = []
    for item in payload:
        if not isinstance(item, dict):
            raise TranscriptLoadError("segment entries must be objects")
        text = normalize_text(str(item.get("text") or ""))
        if not text:
            continue
        segments.append(
            SourceSegment(
                text=text,
                start_ms=_coerce_ms(item, "start"),
                end_ms=_coerce_ms(item, "end"),
            )
        )
    return segments


def _coerce_ms(item: dict[str, Any], base_name: str) -> int | None:
    ms_key = f"{base_name}_ms"
    seconds_key = f"{base_name}_seconds"
    if ms_key in item and item[ms_key] is not None:
        return round(float(item[ms_key]))
    if seconds_key in item and item[seconds_key] is not None:
        return round(float(item[seconds_key]) * 1000)
    if base_name in item and item[base_name] is not None:
        value = float(item[base_name])
        return round(value * 1000) if value < 10_000 else round(value)
    return None


def _looks_like_segment_jsonl(rows: list[dict[str, Any]]) -> bool:
    return all("text" in row for row in rows) and any(
        {"start_ms", "end_ms", "start_seconds", "end_seconds", "start", "end"} & set(row)
        for row in rows
    )


def _iter_transcript_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        if path.is_dir():
            preferred = _preferred_transcript_file(path)
            if preferred:
                files.append(preferred)
            else:
                files.extend(_iter_transcript_files(path))
        elif _is_standalone_transcript_file(path):
            files.append(path)
    return files


def _preferred_transcript_file(directory: Path) -> Path | None:
    for name in ("transcript_segments.jsonl", "transcript.json", "transcript.txt"):
        candidate = directory / name
        if candidate.exists():
            return candidate
    return None


def _is_standalone_transcript_file(path: Path) -> bool:
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        return False
    return path.name not in {"transcript_metadata.json", "transcript_insights.json"}


def _load_sidecar_metadata(path: Path, *, include_if_same_file: bool = True) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    metadata_path = path.parent / "transcript_metadata.json"
    insights_path = path.parent / "transcript_insights.json"
    if include_if_same_file or metadata_path.resolve() != path.resolve():
        if metadata_path.exists():
            metadata["source_metadata"] = json.loads(metadata_path.read_text(encoding="utf-8"))
    if insights_path.exists():
        metadata["source_insights"] = json.loads(insights_path.read_text(encoding="utf-8"))
    return metadata


def _document_id_from_metadata(metadata: dict[str, Any]) -> str | None:
    source_metadata = metadata.get("source_metadata")
    if isinstance(source_metadata, dict):
        for key in ("document_id", "video_id", "id"):
            if source_metadata.get(key):
                return str(source_metadata[key])
    for key in ("document_id", "video_id", "id"):
        if metadata.get(key):
            return str(metadata[key])
    return None


def _language_from_metadata(metadata: dict[str, Any]) -> str:
    source_metadata = metadata.get("source_metadata")
    language = None
    if isinstance(source_metadata, dict):
        language = source_metadata.get("language")
    language = language or metadata.get("language") or "und"
    return str(language or "und")
