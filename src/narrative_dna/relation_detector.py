"""Auditable deterministic relation detection entry points."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from narrative_dna.models import (
    EvidenceSpan,
    Method,
    NarrativeDocument,
    NarrativeRelation,
    NarrativeUnit,
    RelationType,
    ValidatorFlag,
)
from narrative_dna.similarity_auditor import load_run_documents

DEFAULT_TAXONOMY_VERSION = "v1_0"
DEFAULT_PROMPT_VERSION = "v1_0"
DEFAULT_VALIDATOR_VERSION = "v1_0"
DEFAULT_MAX_DISTANCE = 3
DEFAULT_MIN_CONFIDENCE = 0.58
CAUSAL_MARKERS = (
    "porque",
    "por eso",
    "debido",
    "se debe",
    "provoca",
    "causa",
    "cuando",
)
QUESTION_MARKERS = ("?", "¿", "por qué", "para qué", "qué ", "cómo ", "cuándo ")
CONTRAST_MARKERS = ("pero", "sin embargo", "aunque", "en cambio", "mientras")
REFUTATION_MARKERS = ("no es cierto", "refuta", "desmiente", "falso", "en realidad")
RISK_MARKERS = ("riesgo", "peligro", "podría fallar", "puede romper", "amenaza")
SOLUTION_MARKERS = ("solución", "recomiendo", "conviene", "deberíamos", "propongo")
CONDITION_MARKERS = ("si ", "en caso de", "siempre que", "a condición")


def detect_relations_for_document(
    document: NarrativeDocument,
    *,
    run_id: str = "run_unknown",
    max_distance: int = DEFAULT_MAX_DISTANCE,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> NarrativeDocument:
    """Return a document with deterministic relation candidates attached."""

    relations = detect_relations(
        document.units,
        run_id=run_id,
        max_distance=max_distance,
        min_confidence=min_confidence,
    )
    payload = document.model_dump(mode="json")
    payload["relations"] = [relation.model_dump(mode="json") for relation in relations]
    payload["audit_summary"] = {
        **document.audit_summary,
        "relation_count": len(relations),
        "relations_by_type": dict(Counter(str(relation.relation_type) for relation in relations)),
        "taxonomy_version_effective": DEFAULT_TAXONOMY_VERSION,
        "prompt_version_effective": DEFAULT_PROMPT_VERSION,
        "validator_version_effective": DEFAULT_VALIDATOR_VERSION,
    }
    return NarrativeDocument.model_validate(payload)


def detect_relations(
    units: list[NarrativeUnit],
    *,
    run_id: str = "run_unknown",
    max_distance: int = DEFAULT_MAX_DISTANCE,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> list[NarrativeRelation]:
    """Detect auditable relations among nearby units."""

    relations: list[NarrativeRelation] = []
    seen: set[tuple[str, str, str]] = set()
    ordered = sorted(units, key=lambda unit: unit.sequence_index)
    for index, source_candidate in enumerate(ordered):
        for target_candidate in ordered[index + 1 : index + 1 + max_distance]:
            for relation in pair_relations(
                source_candidate,
                target_candidate,
                run_id=run_id,
                min_confidence=min_confidence,
            ):
                key = (
                    relation.source_unit_id,
                    relation.target_unit_id,
                    str(relation.relation_type),
                )
                if key in seen:
                    continue
                seen.add(key)
                relations.append(relation)
    return relations


def pair_relations(
    first: NarrativeUnit,
    second: NarrativeUnit,
    *,
    run_id: str,
    min_confidence: float,
) -> list[NarrativeRelation]:
    """Apply deterministic rules to one ordered pair."""

    if first.document_id != second.document_id:
        return []
    candidates: list[NarrativeRelation] = []
    distance = max(1, second.sequence_index - first.sequence_index)

    if is_question(first) and (has_function(second, "R") or answer_like(second)):
        candidates.append(
            build_relation(
                run_id=run_id,
                source=first,
                target=second,
                relation_type=RelationType.ANS,
                confidence=confidence(0.92, distance),
                rule_id="ANS_question_answer_anchor",
                evidence_text=second.text,
                rejected=[RelationType.EXPL],
            )
        )

    if has_function(second, "Y") and has_any_function(first, {"A", "K", "O", "R"}):
        relation_type = (
            RelationType.CAUSE if has_marker(second, CAUSAL_MARKERS) else RelationType.EXPL
        )
        candidates.append(
            build_relation(
                run_id=run_id,
                source=second,
                target=first,
                relation_type=relation_type,
                confidence=confidence(
                    0.82 if relation_type == RelationType.CAUSE else 0.74, distance
                ),
                rule_id="Y_explains_previous_claim",
                evidence_text=second.text,
                rejected=[RelationType.SUP],
            )
        )

    if has_any_function(second, {"D", "Q"}) and has_any_function(first, {"A", "K", "O", "Y"}):
        candidates.append(
            build_relation(
                run_id=run_id,
                source=second,
                target=first,
                relation_type=RelationType.SUP,
                confidence=confidence(0.86, distance),
                rule_id="evidence_supports_prior_claim",
                evidence_text=second.text,
                rejected=[RelationType.CAUSE, RelationType.EXPL],
            )
        )

    if has_function(second, "E") and has_any_function(first, {"A", "K", "F", "Y", "S"}):
        candidates.append(
            build_relation(
                run_id=run_id,
                source=second,
                target=first,
                relation_type=RelationType.EXMP,
                confidence=confidence(0.82, distance),
                rule_id="example_illustrates_previous_unit",
                evidence_text=second.text,
                rejected=[RelationType.ELAB],
            )
        )

    if has_function(second, "G") and has_any_function(first, {"A", "K", "F", "Y"}):
        candidates.append(
            build_relation(
                run_id=run_id,
                source=second,
                target=first,
                relation_type=RelationType.ANLG,
                confidence=confidence(0.84, distance),
                rule_id="analogy_maps_to_previous_unit",
                evidence_text=second.text,
                rejected=[RelationType.EXMP],
            )
        )

    if has_function(second, "C") or has_marker(second, CONTRAST_MARKERS):
        candidates.append(
            build_relation(
                run_id=run_id,
                source=second,
                target=first,
                relation_type=RelationType.CONTR,
                confidence=confidence(0.78, distance),
                rule_id="contrast_with_previous_unit",
                evidence_text=second.text,
                rejected=[RelationType.ELAB],
            )
        )

    if has_function(second, "B") or has_marker(second, REFUTATION_MARKERS):
        candidates.append(
            build_relation(
                run_id=run_id,
                source=second,
                target=first,
                relation_type=RelationType.REFUT,
                confidence=confidence(0.84, distance),
                rule_id="refutation_targets_previous_unit",
                evidence_text=second.text,
                rejected=[RelationType.CONTR],
            )
        )

    if has_function(second, "X") or has_marker(second, RISK_MARKERS):
        candidates.append(
            build_relation(
                run_id=run_id,
                source=second,
                target=first,
                relation_type=RelationType.RISK,
                confidence=confidence(0.8, distance),
                rule_id="risk_attaches_to_previous_unit",
                evidence_text=second.text,
                rejected=[RelationType.CONTR],
            )
        )

    if (has_function(second, "S") or has_marker(second, SOLUTION_MARKERS)) and (
        has_function(first, "X") or has_marker(first, RISK_MARKERS)
    ):
        candidates.append(
            build_relation(
                run_id=run_id,
                source=second,
                target=first,
                relation_type=RelationType.SOLV,
                confidence=confidence(0.86, distance),
                rule_id="solution_addresses_prior_risk",
                evidence_text=second.text,
                rejected=[RelationType.CALL],
            )
        )

    if has_function(second, "V"):
        candidates.append(
            build_relation(
                run_id=run_id,
                source=second,
                target=first,
                relation_type=RelationType.CALL,
                confidence=confidence(0.72, distance),
                rule_id="viewer_call_attaches_to_previous_unit",
                evidence_text=second.text,
                rejected=[RelationType.SEQ],
            )
        )

    if has_function(second, "Z") and has_any_function(first, {"A", "K", "Y", "S", "L"}):
        candidates.append(
            build_relation(
                run_id=run_id,
                source=second,
                target=first,
                relation_type=RelationType.SUM,
                confidence=confidence(0.76, distance),
                rule_id="conclusion_summarizes_previous_unit",
                evidence_text=second.text,
                rejected=[RelationType.SEQ],
            )
        )

    if has_marker(second, CONDITION_MARKERS):
        candidates.append(
            build_relation(
                run_id=run_id,
                source=second,
                target=first,
                relation_type=RelationType.COND,
                confidence=confidence(0.76, distance),
                rule_id="condition_modifies_previous_unit",
                evidence_text=second.text,
                rejected=[RelationType.CAUSE],
            )
        )

    if not candidates and adjacent(first, second) and elaborates(first, second):
        candidates.append(
            build_relation(
                run_id=run_id,
                source=second,
                target=first,
                relation_type=RelationType.ELAB,
                confidence=0.62,
                rule_id="adjacent_elaboration",
                evidence_text=second.text,
                rejected=[RelationType.SEQ],
            )
        )

    if not candidates and adjacent(first, second) and structural_sequence(first, second):
        candidates.append(
            build_relation(
                run_id=run_id,
                source=first,
                target=second,
                relation_type=RelationType.SEQ,
                confidence=0.6,
                rule_id="adjacent_structural_sequence",
                evidence_text=second.text,
                rejected=[RelationType.ELAB],
            )
        )

    return [relation for relation in candidates if relation.confidence >= min_confidence]


def build_relation(
    *,
    run_id: str,
    source: NarrativeUnit,
    target: NarrativeUnit,
    relation_type: RelationType,
    confidence: float,
    rule_id: str,
    evidence_text: str,
    rejected: list[RelationType],
) -> NarrativeRelation:
    needs_review = confidence < 0.7 or len(rejected) > 1
    flags = []
    if needs_review:
        flags.append(
            ValidatorFlag(
                rule_id="relation_needs_review",
                severity="warning",
                message="Relation is plausible but below high-confidence threshold.",
                field="relation_type",
            )
        )
    return NarrativeRelation(
        run_id=run_id,
        relation_id=relation_id(run_id, source, target, relation_type, rule_id),
        document_id=source.document_id,
        source_unit_id=source.unit_id,
        target_unit_id=target.unit_id,
        relation_type=relation_type,
        confidence=round(confidence, 4),
        method=Method.HEURISTIC,
        evidence_spans=[
            EvidenceSpan(
                text=evidence_text,
                source=f"relation_detector:{rule_id}",
            )
        ],
        rejected_relation_types=rejected,
        validator_flags=flags,
        needs_review=needs_review,
        taxonomy_version_effective=DEFAULT_TAXONOMY_VERSION,
        prompt_version_effective=DEFAULT_PROMPT_VERSION,
        validator_version_effective=DEFAULT_VALIDATOR_VERSION,
    )


def detect_relations_for_run(
    *,
    run_id: str,
    outputs_dir: str | Path = "outputs",
    max_distance: int = DEFAULT_MAX_DISTANCE,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> tuple[list[NarrativeDocument], list[NarrativeRelation]]:
    """Load run documents, detect relations, and write derived outputs."""

    run_dir = Path(outputs_dir) / run_id
    documents = [
        detect_relations_for_document(
            document,
            run_id=run_id,
            max_distance=max_distance,
            min_confidence=min_confidence,
        )
        for document in load_run_documents(run_dir)
    ]
    relations = [relation for document in documents for relation in document.relations]
    write_relation_outputs(run_dir, documents, relations)
    return documents, relations


def write_relation_outputs(
    run_dir: str | Path,
    documents: list[NarrativeDocument],
    relations: list[NarrativeRelation],
) -> tuple[Path, Path]:
    """Write updated documents and relations JSONL as derived outputs."""

    destination = Path(run_dir)
    documents_path = destination / "documents.jsonl"
    relations_path = destination / "relations.jsonl"
    documents_path.write_text(
        "\n".join(
            json.dumps(document.model_dump(mode="json"), ensure_ascii=False)
            for document in documents
        )
        + ("\n" if documents else ""),
        encoding="utf-8",
    )
    relations_path.write_text(
        "\n".join(
            json.dumps(relation.model_dump(mode="json"), ensure_ascii=False)
            for relation in relations
        )
        + ("\n" if relations else ""),
        encoding="utf-8",
    )
    return documents_path, relations_path


def relation_id(
    run_id: str,
    source: NarrativeUnit,
    target: NarrativeUnit,
    relation_type: RelationType,
    rule_id: str,
) -> str:
    text = f"{run_id}::{source.unit_id}::{target.unit_id}::{relation_type}::{rule_id}"
    return f"rel_{hashlib.sha256(text.encode()).hexdigest()[:16]}"


def has_function(unit: NarrativeUnit, function: str) -> bool:
    return function in functions(unit)


def has_any_function(unit: NarrativeUnit, selected: set[str]) -> bool:
    return bool(set(functions(unit)) & selected)


def functions(unit: NarrativeUnit) -> list[str]:
    return [str(function) for function in unit.functions]


def has_marker(unit: NarrativeUnit, markers: tuple[str, ...]) -> bool:
    text = f"{unit.text} {unit.normalized_text}".lower()
    return any(marker in text for marker in markers)


def is_question(unit: NarrativeUnit) -> bool:
    return has_function(unit, "P") or has_marker(unit, QUESTION_MARKERS)


def answer_like(unit: NarrativeUnit) -> bool:
    text = unit.normalized_text.lower()
    return text.startswith(("la respuesta", "respuesta:", "porque", "es que"))


def adjacent(first: NarrativeUnit, second: NarrativeUnit) -> bool:
    return second.sequence_index - first.sequence_index == 1


def elaborates(first: NarrativeUnit, second: NarrativeUnit) -> bool:
    return has_any_function(first, {"A", "K", "F", "M"}) and has_any_function(
        second, {"A", "F", "M", "U"}
    )


def structural_sequence(first: NarrativeUnit, second: NarrativeUnit) -> bool:
    return has_any_function(first, {"T", "M", "L"}) or has_any_function(second, {"T", "M", "L"})


def confidence(base: float, distance: int) -> float:
    penalty = max(0, distance - 1) * 0.08
    return max(0.0, min(1.0, base - penalty))


def relation_summary(relations: list[NarrativeRelation]) -> dict[str, Any]:
    return {
        "relation_count": len(relations),
        "relations_by_type": dict(Counter(str(relation.relation_type) for relation in relations)),
        "needs_review_count": sum(1 for relation in relations if relation.needs_review),
        "taxonomy_version_effective": DEFAULT_TAXONOMY_VERSION,
        "prompt_version_effective": DEFAULT_PROMPT_VERSION,
        "validator_version_effective": DEFAULT_VALIDATOR_VERSION,
    }
