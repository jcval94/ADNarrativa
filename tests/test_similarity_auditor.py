from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from narrative_dna.models import NarrativeDocument, NarrativeUnit
from narrative_dna.notation import derive_final_notation
from narrative_dna.similarity_auditor import (
    CachedEmbeddingProvider,
    LocalHashEmbeddingProvider,
    audit_similarity,
    build_similarity_conflict,
    contextual_embedding_text,
    embedding_provider_from_config,
    label_distance,
    write_similarity_audit,
)


class StaticEmbeddingProvider:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _text in texts]


def unit_payload(
    *,
    document_id: str,
    unit_id: str,
    sequence_index: int,
    text: str,
    functions: list[str],
    primary_function: str,
    confidence: float = 0.9,
    previous_unit_id: str | None = None,
    next_unit_id: str | None = None,
    emotions_mentioned: list[str] | None = None,
    emotion_expressed: str = "N",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "document_id": document_id,
        "unit_id": unit_id,
        "sequence_index": sequence_index,
        "text": text,
        "normalized_text": text.lower(),
        "previous_unit_id": previous_unit_id,
        "next_unit_id": next_unit_id,
        "functions": functions,
        "primary_function": primary_function,
        "secondary_functions": [function for function in functions if function != primary_function],
        "inherited_functions": [],
        "certainty": "none",
        "emotion_expressed": emotion_expressed,
        "emotion_intensity": 0 if emotion_expressed == "N" else 1,
        "emotions_mentioned": emotions_mentioned or [],
        "stance": "neutral",
        "target": None,
        "speech_act": None,
        "logic": None,
        "evidence_spans": [{"text": text}],
        "rejected_labels": [],
        "validator_flags": [],
        "heuristic_candidates": [],
        "llm_votes": [],
        "confidence": confidence,
        "method": "adjudicated",
        "needs_review": False,
        "review_reasons": [],
        "review_status": "accepted",
        "final_notation": "",
        "taxonomy_version": "v1_0",
        "prompt_version": "v1_0",
        "validator_version": "v1_0",
    }
    payload["final_notation"] = derive_final_notation(payload)
    return payload


def unit(**kwargs: Any) -> NarrativeUnit:
    return NarrativeUnit.model_validate(unit_payload(**kwargs))


def document(document_id: str, units: list[NarrativeUnit]) -> NarrativeDocument:
    return NarrativeDocument.model_validate(
        {
            "document_id": document_id,
            "source_path": f"{document_id}.txt",
            "source_type": "txt",
            "language": "es",
            "metadata": {},
            "segmentation": {"strategy": "test", "unit_count": len(units), "notes": []},
            "units": [item.model_dump(mode="json") for item in units],
            "relations": [],
            "chains": [],
            "document_metrics": {},
            "audit_summary": {},
        }
    )


def test_detects_likely_inconsistency_for_similar_a_k_units() -> None:
    doc_a = document(
        "doc_a",
        [
            unit(
                document_id="doc_a",
                unit_id="a1",
                sequence_index=0,
                text="El flujo actual no escala.",
                functions=["A"],
                primary_function="A",
            )
        ],
    )
    doc_b = document(
        "doc_b",
        [
            unit(
                document_id="doc_b",
                unit_id="b1",
                sequence_index=0,
                text="El flujo actual no escala.",
                functions=["K"],
                primary_function="K",
            )
        ],
    )

    conflicts, summary = audit_similarity(
        [doc_a, doc_b],
        run_id="run_test",
        provider=StaticEmbeddingProvider(),
        threshold=0.9,
    )

    assert len(conflicts) == 1
    assert conflicts[0].conflict_explanation_type == "likely_inconsistency"
    assert conflicts[0].conflict_score > 0
    assert "primary_function" in conflicts[0].differing_fields
    assert summary.conflicts_by_type["likely_inconsistency"] == 1


def test_context_explains_r_y_difference() -> None:
    question = unit(
        document_id="doc_r",
        unit_id="r0",
        sequence_index=0,
        text="Por que falla?",
        functions=["P"],
        primary_function="P",
        next_unit_id="r1",
    )
    answer = unit(
        document_id="doc_r",
        unit_id="r1",
        sequence_index=1,
        text="Falla porque nadie mide.",
        functions=["R"],
        primary_function="R",
        previous_unit_id="r0",
    )
    cause = unit(
        document_id="doc_y",
        unit_id="y1",
        sequence_index=0,
        text="Falla porque nadie mide.",
        functions=["Y"],
        primary_function="Y",
    )

    conflicts, _summary = audit_similarity(
        [document("doc_r", [question, answer]), document("doc_y", [cause])],
        run_id="run_context",
        provider=StaticEmbeddingProvider(),
        threshold=0.9,
    )

    conflict = next(item for item in conflicts if {item.unit_id_a, item.unit_id_b} == {"r1", "y1"})
    assert conflict.conflict_explanation_type == "context_explains_difference"
    assert conflict.needs_review is False


def test_viewer_call_only_difference_is_allowed_by_taxonomy() -> None:
    base = unit(
        document_id="doc_a",
        unit_id="a1",
        sequence_index=0,
        text="Esto importa.",
        functions=["A"],
        primary_function="A",
    )
    viewer = unit(
        document_id="doc_b",
        unit_id="b1",
        sequence_index=0,
        text="Esto te importa.",
        functions=["A", "V"],
        primary_function="A",
    )

    conflicts, _summary = audit_similarity(
        [document("doc_a", [base]), document("doc_b", [viewer])],
        run_id="run_allowed",
        provider=StaticEmbeddingProvider(),
        threshold=0.9,
    )

    assert conflicts[0].conflict_explanation_type == "allowed_by_taxonomy"
    assert conflicts[0].needs_review is False


def test_embedding_context_uses_previous_current_and_next() -> None:
    first = unit(
        document_id="doc",
        unit_id="u0",
        sequence_index=0,
        text="Antes.",
        functions=["A"],
        primary_function="A",
    )
    middle = unit(
        document_id="doc",
        unit_id="u1",
        sequence_index=1,
        text="Actual.",
        functions=["A"],
        primary_function="A",
    )
    last = unit(
        document_id="doc",
        unit_id="u2",
        sequence_index=2,
        text="Despues.",
        functions=["A"],
        primary_function="A",
    )

    text = contextual_embedding_text(middle, [first, middle, last])

    assert text == "antes. actual. despues."


def test_writes_similarity_conflicts_and_summary(tmp_path: Path) -> None:
    first = unit(
        document_id="doc_a",
        unit_id="a1",
        sequence_index=0,
        text="El flujo no escala.",
        functions=["A"],
        primary_function="A",
    )
    second = unit(
        document_id="doc_b",
        unit_id="b1",
        sequence_index=0,
        text="El flujo no escala.",
        functions=["K"],
        primary_function="K",
    )
    conflict = build_similarity_conflict(
        run_id="run_write",
        unit_a=first,
        unit_b=second,
        all_units=[first, second],
        similarity=1.0,
    )
    assert conflict is not None

    conflicts_path, summary_path = write_similarity_audit(
        conflicts=[conflict],
        summary=audit_similarity(
            [document("doc_a", [first]), document("doc_b", [second])],
            run_id="run_write",
            provider=StaticEmbeddingProvider(),
        )[1],
        output_dir=tmp_path,
    )

    assert (
        json.loads(conflicts_path.read_text(encoding="utf-8").splitlines()[0])["run_id"]
        == "run_write"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["taxonomy_version_effective"] == "v1_0"


def test_cached_local_embedding_provider_writes_cache(tmp_path: Path) -> None:
    provider = CachedEmbeddingProvider(
        LocalHashEmbeddingProvider(dimensions=16),
        provider_id="local_test",
        cache_dir=tmp_path,
    )

    first = provider.embed_texts(["texto repetido"])
    second = provider.embed_texts(["texto repetido"])

    assert first == second
    assert list((tmp_path / "local_test").glob("*.json"))


def test_embedding_provider_from_config_supports_configured_local_provider(tmp_path: Path) -> None:
    config = tmp_path / "similarity.json"
    config.write_text(
        json.dumps(
            {
                "embedding": {
                    "provider": "local",
                    "dimensions": 8,
                    "cache_enabled": False,
                }
            }
        ),
        encoding="utf-8",
    )

    provider = embedding_provider_from_config(config)
    embeddings = provider.embed_texts(["uno", "dos"])

    assert len(embeddings) == 2
    assert len(embeddings[0]) == 8


def test_label_distance_uses_jaccard_distance() -> None:
    first = unit(
        document_id="doc_a",
        unit_id="a1",
        sequence_index=0,
        text="Texto.",
        functions=["A", "V"],
        primary_function="A",
    )
    second = unit(
        document_id="doc_b",
        unit_id="b1",
        sequence_index=0,
        text="Texto.",
        functions=["A"],
        primary_function="A",
    )

    assert label_distance(first, second) == 0.5
