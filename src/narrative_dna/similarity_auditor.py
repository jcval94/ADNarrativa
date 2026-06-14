"""Semantic similarity audit entry points."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Protocol

from pydantic import Field

from narrative_dna.models import (
    ConflictExplanationType,
    NarrativeDocument,
    NarrativeUnit,
    SimilarityConflict,
    StrictBaseModel,
)
from narrative_dna.question_detection import has_question_anchor as text_has_question_anchor

DEFAULT_RUN_ID = "in_memory_similarity_audit"
DEFAULT_THRESHOLD = 0.82
DEFAULT_TOP_K = 10
DEFAULT_EMBEDDING_DIMENSIONS = 128
DEFAULT_EMBEDDING_CACHE_DIR = Path(".cache/narrative_dna/embeddings")
DEFAULT_CONFIG_PATH = Path("configs/similarity_audit_config.json")
DEFAULT_TAXONOMY_VERSION = "v1_0"
DEFAULT_PROMPT_VERSION = "v1_0"
DEFAULT_VALIDATOR_VERSION = "v1_0"
TOKEN_RE = re.compile(r"[a-z0-9]+")
VIEWER_ADDRESS_RE = re.compile(r"\b(tu|tus|te|ti|contigo|ustedes|preguntate)\b")


class EmbeddingProvider(Protocol):
    """Interface for embedding providers used by the similarity auditor."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per text."""


class LocalHashEmbeddingProvider:
    """Deterministic token-hashing embeddings for tests and offline audits."""

    def __init__(self, *, dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS) -> None:
        self.dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token, count in Counter(_tokens(text)).items():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign * float(count)
        return _normalize_vector(vector)


class CachedEmbeddingProvider:
    """Cache embeddings by provider id and contextual text hash."""

    def __init__(
        self,
        provider: EmbeddingProvider,
        *,
        provider_id: str,
        cache_dir: str | Path = DEFAULT_EMBEDDING_CACHE_DIR,
    ) -> None:
        self.provider = provider
        self.provider_id = provider_id
        self.cache_dir = Path(cache_dir)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        cached: dict[int, list[float]] = {}
        missing_indexes: list[int] = []
        missing_texts: list[str] = []
        for index, text in enumerate(texts):
            cache_path = self._cache_path(text)
            if cache_path.exists():
                cached[index] = json.loads(cache_path.read_text(encoding="utf-8"))["embedding"]
            else:
                missing_indexes.append(index)
                missing_texts.append(text)

        if missing_texts:
            embeddings = self.provider.embed_texts(missing_texts)
            for index, text, embedding in zip(
                missing_indexes, missing_texts, embeddings, strict=True
            ):
                cached[index] = embedding
                cache_path = self._cache_path(text)
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(
                    json.dumps(
                        {
                            "provider_id": self.provider_id,
                            "text_sha256": _text_hash(text),
                            "embedding": embedding,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
        return [cached[index] for index in range(len(texts))]

    def _cache_path(self, text: str) -> Path:
        return self.cache_dir / self.provider_id / f"{_text_hash(text)}.json"


class OpenAIEmbeddingProvider:
    """Configurable OpenAI embeddings provider.

    The model is injected by config/caller. Tests use local providers and never
    need live API calls.
    """

    def __init__(self, *, model: str, api_key: str | None = None) -> None:
        if not model:
            raise ValueError("OpenAI embedding model must be configured.")
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI embeddings.")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on runtime package state.
            raise RuntimeError("The openai package is required for OpenAI embeddings.") from exc
        client = OpenAI(api_key=self.api_key)
        response = client.embeddings.create(model=self.model, input=texts)
        return [list(item.embedding) for item in response.data]


class SimilarityAuditSummary(StrictBaseModel):
    run_id: str = Field(min_length=1)
    total_units: int = Field(ge=0)
    total_pairs_considered: int = Field(ge=0)
    total_conflicts: int = Field(ge=0)
    threshold: float = Field(ge=0, le=1)
    top_k: int = Field(ge=1)
    conflicts_by_type: dict[str, int] = Field(default_factory=dict)
    taxonomy_version_effective: str = Field(min_length=1)
    prompt_version_effective: str = Field(min_length=1)
    validator_version_effective: str = Field(min_length=1)


def audit_similarity(
    documents: NarrativeDocument | list[NarrativeDocument],
    *,
    run_id: str = DEFAULT_RUN_ID,
    provider: EmbeddingProvider | None = None,
    top_k: int = DEFAULT_TOP_K,
    threshold: float = DEFAULT_THRESHOLD,
) -> tuple[list[SimilarityConflict], SimilarityAuditSummary]:
    """Audit semantically similar units for notation inconsistencies."""

    document_list = documents if isinstance(documents, list) else [documents]
    units = [unit for document in document_list for unit in document.units]
    if not units:
        return [], _summary(
            run_id=run_id,
            total_units=0,
            pairs=0,
            conflicts=[],
            top_k=top_k,
            threshold=threshold,
        )

    provider = provider or embedding_provider_from_config()
    contextual_texts = [contextual_embedding_text(unit, units) for unit in units]
    embeddings = provider.embed_texts(contextual_texts)
    conflicts: list[SimilarityConflict] = []
    pairs_considered = 0

    for index, unit in enumerate(units):
        neighbors: list[tuple[int, float]] = []
        for other_index, other in enumerate(units):
            if index == other_index:
                continue
            if (
                unit.document_id == other.document_id
                and abs(unit.sequence_index - other.sequence_index) <= 1
            ):
                continue
            similarity = cosine_similarity(embeddings[index], embeddings[other_index])
            if similarity >= threshold:
                neighbors.append((other_index, similarity))
        neighbors.sort(key=lambda item: item[1], reverse=True)
        for other_index, similarity in neighbors[:top_k]:
            if index >= other_index:
                continue
            pairs_considered += 1
            conflict = build_similarity_conflict(
                run_id=run_id,
                unit_a=unit,
                unit_b=units[other_index],
                all_units=units,
                similarity=similarity,
            )
            if conflict is not None:
                conflicts.append(conflict)

    return conflicts, _summary(
        run_id=run_id,
        total_units=len(units),
        pairs=pairs_considered,
        conflicts=conflicts,
        top_k=top_k,
        threshold=threshold,
    )


def build_similarity_conflict(
    *,
    run_id: str,
    unit_a: NarrativeUnit,
    unit_b: NarrativeUnit,
    all_units: list[NarrativeUnit],
    similarity: float,
) -> SimilarityConflict | None:
    differing_fields = differing_notation_fields(unit_a, unit_b)
    if not differing_fields:
        return None
    notation_distance = compute_notation_distance(unit_a, unit_b)
    if notation_distance <= 0:
        return None
    avg_confidence = (unit_a.confidence + unit_b.confidence) / 2
    conflict_score = similarity * notation_distance * avg_confidence
    explanation_type, explanation, needs_review = explain_conflict(
        unit_a,
        unit_b,
        all_units=all_units,
        differing_fields=differing_fields,
    )
    return SimilarityConflict.model_validate(
        {
            "conflict_id": _conflict_id(run_id, unit_a, unit_b),
            "run_id": run_id,
            "unit_id_a": unit_a.unit_id,
            "unit_id_b": unit_b.unit_id,
            "similarity": round(similarity, 6),
            "notation_distance": round(notation_distance, 6),
            "conflict_score": round(conflict_score, 6),
            "conflict_explanation_type": explanation_type,
            "differing_fields": differing_fields,
            "explanation": explanation,
            "needs_review": needs_review,
        }
    )


def write_similarity_audit(
    *,
    conflicts: list[SimilarityConflict],
    summary: SimilarityAuditSummary,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Write JSONL conflicts and JSON summary as derived outputs."""

    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    conflicts_path = target / "similarity_conflicts.jsonl"
    summary_path = target / "similarity_conflicts_summary.json"
    conflict_lines = [
        json.dumps(conflict.model_dump(mode="json"), ensure_ascii=False) for conflict in conflicts
    ]
    conflicts_path.write_text(
        "\n".join(conflict_lines) + ("\n" if conflicts else ""),
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return conflicts_path, summary_path


def audit_similarity_run(
    *,
    run_id: str,
    outputs_dir: str | Path = "outputs",
    provider: EmbeddingProvider | None = None,
    top_k: int = DEFAULT_TOP_K,
    threshold: float = DEFAULT_THRESHOLD,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> tuple[list[SimilarityConflict], SimilarityAuditSummary]:
    """Load run documents from outputs/{run_id}, audit, and write derived outputs."""

    run_dir = Path(outputs_dir) / run_id
    documents = load_run_documents(run_dir)
    conflicts, summary = audit_similarity(
        documents,
        run_id=run_id,
        provider=provider or embedding_provider_from_config(config_path),
        top_k=top_k,
        threshold=threshold,
    )
    write_similarity_audit(conflicts=conflicts, summary=summary, output_dir=run_dir)
    return conflicts, summary


def load_run_documents(run_dir: str | Path) -> list[NarrativeDocument]:
    path = Path(run_dir)
    documents_path = path / "documents.jsonl"
    if documents_path.exists():
        return [
            NarrativeDocument.model_validate(json.loads(line))
            for line in documents_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    raise FileNotFoundError(f"Missing documents.jsonl in run directory: {path}")


def load_similarity_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("similarity audit config must be a JSON object")
    return payload


def embedding_provider_from_config(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> EmbeddingProvider:
    config = load_similarity_config(config_path)
    embedding_config = (
        config.get("embedding", {}) if isinstance(config.get("embedding"), dict) else {}
    )
    provider_name = str(embedding_config.get("provider", "local"))
    cache_enabled = bool(embedding_config.get("cache_enabled", True))
    cache_dir = Path(embedding_config.get("cache_dir", DEFAULT_EMBEDDING_CACHE_DIR))

    if provider_name == "openai":
        model = embedding_config.get("openai_model")
        if not model:
            raise ValueError("embedding.openai_model must be configured for OpenAI embeddings")
        provider: EmbeddingProvider = OpenAIEmbeddingProvider(model=str(model))
        provider_id = f"openai_{model}"
    else:
        dimensions = int(embedding_config.get("dimensions", DEFAULT_EMBEDDING_DIMENSIONS))
        provider = LocalHashEmbeddingProvider(dimensions=dimensions)
        provider_id = f"local_hash_{dimensions}"

    if not cache_enabled:
        return provider
    return CachedEmbeddingProvider(provider, provider_id=provider_id, cache_dir=cache_dir)


def contextual_embedding_text(unit: NarrativeUnit, all_units: list[NarrativeUnit]) -> str:
    previous_unit = _neighbor(unit, all_units, offset=-1)
    next_unit = _neighbor(unit, all_units, offset=1)
    parts = []
    if previous_unit:
        parts.append(previous_unit.normalized_text)
    parts.append(unit.normalized_text)
    if next_unit:
        parts.append(next_unit.normalized_text)
    return " ".join(parts)


def cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    if not vector_a or not vector_b:
        return 0.0
    dot = sum(a * b for a, b in zip(vector_a, vector_b, strict=False))
    norm_a = math.sqrt(sum(a * a for a in vector_a))
    norm_b = math.sqrt(sum(b * b for b in vector_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def label_distance(unit_a: NarrativeUnit, unit_b: NarrativeUnit) -> float:
    labels_a = {str(function) for function in unit_a.functions}
    labels_b = {str(function) for function in unit_b.functions}
    union = labels_a | labels_b
    if not union:
        return 0.0
    return 1 - (len(labels_a & labels_b) / len(union))


def compute_notation_distance(unit_a: NarrativeUnit, unit_b: NarrativeUnit) -> float:
    distances = [
        label_distance(unit_a, unit_b),
        0.0 if str(unit_a.primary_function) == str(unit_b.primary_function) else 1.0,
        0.0 if str(unit_a.certainty) == str(unit_b.certainty) else 1.0,
        0.0 if str(unit_a.emotion_expressed) == str(unit_b.emotion_expressed) else 1.0,
        0.0 if str(unit_a.stance) == str(unit_b.stance) else 1.0,
    ]
    return sum(distances) / len(distances)


def differing_notation_fields(unit_a: NarrativeUnit, unit_b: NarrativeUnit) -> list[str]:
    fields: list[str] = []
    functions_a = {str(function) for function in unit_a.functions}
    functions_b = {str(function) for function in unit_b.functions}
    if functions_a != functions_b:
        fields.append("functions")
    if str(unit_a.primary_function) != str(unit_b.primary_function):
        fields.append("primary_function")
    if str(unit_a.certainty) != str(unit_b.certainty):
        fields.append("certainty")
    if str(unit_a.emotion_expressed) != str(unit_b.emotion_expressed):
        fields.append("emotion_expressed")
    if str(unit_a.stance) != str(unit_b.stance):
        fields.append("stance")
    mentioned_a = {str(emotion) for emotion in unit_a.emotions_mentioned}
    mentioned_b = {str(emotion) for emotion in unit_b.emotions_mentioned}
    if mentioned_a != mentioned_b:
        fields.append("emotions_mentioned")
    return fields


def explain_conflict(
    unit_a: NarrativeUnit,
    unit_b: NarrativeUnit,
    *,
    all_units: list[NarrativeUnit],
    differing_fields: list[str],
) -> tuple[ConflictExplanationType, str, bool]:
    if _viewer_call_only_difference(unit_a, unit_b):
        return (
            ConflictExplanationType.ALLOWED_BY_TAXONOMY,
            "Difference is only viewer-call V and is supported by direct address.",
            False,
        )
    if _ry_context_explains_difference(unit_a, unit_b, all_units):
        return (
            ConflictExplanationType.CONTEXT_EXPLAINS_DIFFERENCE,
            "R/Y difference is explained by a nearby question anchor for one unit.",
            False,
        )
    if _differs_within_group(unit_a, unit_b, {"A", "K", "O"}):
        return (
            ConflictExplanationType.LIKELY_INCONSISTENCY,
            "Very similar units differ across A/K/O boundary.",
            True,
        )
    if "emotion_expressed" in differing_fields or "emotions_mentioned" in differing_fields:
        return (
            ConflictExplanationType.NEEDS_HUMAN_REVIEW,
            "Possible confusion between expressed and mentioned emotion.",
            True,
        )
    return (
        ConflictExplanationType.NEEDS_HUMAN_REVIEW,
        "Similar units have materially different notation fields.",
        True,
    )


def _summary(
    *,
    run_id: str,
    total_units: int,
    pairs: int,
    conflicts: list[SimilarityConflict],
    top_k: int,
    threshold: float,
) -> SimilarityAuditSummary:
    by_type: dict[str, int] = {}
    for conflict in conflicts:
        key = str(conflict.conflict_explanation_type)
        by_type[key] = by_type.get(key, 0) + 1
    return SimilarityAuditSummary(
        run_id=run_id,
        total_units=total_units,
        total_pairs_considered=pairs,
        total_conflicts=len(conflicts),
        threshold=threshold,
        top_k=top_k,
        conflicts_by_type=by_type,
        taxonomy_version_effective=DEFAULT_TAXONOMY_VERSION,
        prompt_version_effective=DEFAULT_PROMPT_VERSION,
        validator_version_effective=DEFAULT_VALIDATOR_VERSION,
    )


def _viewer_call_only_difference(unit_a: NarrativeUnit, unit_b: NarrativeUnit) -> bool:
    labels_a = {str(function) for function in unit_a.functions}
    labels_b = {str(function) for function in unit_b.functions}
    if labels_a == labels_b:
        return False
    if labels_a ^ labels_b != {"V"}:
        return False
    return bool(
        VIEWER_ADDRESS_RE.search(_fold(unit_a.text)) or VIEWER_ADDRESS_RE.search(_fold(unit_b.text))
    )


def _ry_context_explains_difference(
    unit_a: NarrativeUnit,
    unit_b: NarrativeUnit,
    all_units: list[NarrativeUnit],
) -> bool:
    labels_a = {str(function) for function in unit_a.functions}
    labels_b = {str(function) for function in unit_b.functions}
    if not ({"R", "Y"} & labels_a and {"R", "Y"} & labels_b):
        return False
    if "R" not in (labels_a | labels_b) or "Y" not in (labels_a | labels_b):
        return False
    return _has_question_anchor(unit_a, all_units) != _has_question_anchor(unit_b, all_units)


def _differs_within_group(unit_a: NarrativeUnit, unit_b: NarrativeUnit, group: set[str]) -> bool:
    labels_a = {str(function) for function in unit_a.functions}
    labels_b = {str(function) for function in unit_b.functions}
    intersection_a = labels_a & group
    intersection_b = labels_b & group
    return bool(intersection_a and intersection_b and intersection_a != intersection_b)


def _has_question_anchor(unit: NarrativeUnit, all_units: list[NarrativeUnit]) -> bool:
    previous_unit = _neighbor(unit, all_units, offset=-1)
    return text_has_question_anchor(
        unit.text,
        previous_text=previous_unit.text if previous_unit else None,
    )


def _neighbor(
    unit: NarrativeUnit, all_units: list[NarrativeUnit], *, offset: int
) -> NarrativeUnit | None:
    target_index = unit.sequence_index + offset
    for candidate in all_units:
        if candidate.document_id == unit.document_id and candidate.sequence_index == target_index:
            return candidate
    return None


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(_fold(text))


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _conflict_id(run_id: str, unit_a: NarrativeUnit, unit_b: NarrativeUnit) -> str:
    pair = "::".join(sorted([unit_a.unit_id, unit_b.unit_id]))
    return f"sim_{hashlib.sha256(f'{run_id}::{pair}'.encode()).hexdigest()[:16]}"
