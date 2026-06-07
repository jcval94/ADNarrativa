"""Auditable deterministic narrative chain detection entry points."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from narrative_dna.models import (
    EvidenceSpan,
    NarrativeChain,
    NarrativeDocument,
    NarrativeRelation,
    NarrativeUnit,
    ValidatorFlag,
)
from narrative_dna.similarity_auditor import load_run_documents

DEFAULT_TAXONOMY_VERSION = "v1_0"
DEFAULT_PROMPT_VERSION = "v1_0"
DEFAULT_VALIDATOR_VERSION = "v1_0"
DEFAULT_MIN_SCORE = 0.58
DEFAULT_MAX_CHAIN_LENGTH = 6
RELATION_PATTERN_DEFINITIONS = {
    "question_answer": {
        "relations": ("ANS",),
        "score": 0.9,
        "narrative_function": "resuelve una pregunta explícita con una respuesta cercana",
    },
    "claim_support_explanation": {
        "relations": ("SUP", "EXPL", "CAUSE"),
        "score": 0.82,
        "narrative_function": "sostiene o explica un claim con evidencia o causalidad",
    },
    "risk_solution": {
        "relations": ("RISK", "SOLV"),
        "score": 0.88,
        "narrative_function": "presenta un riesgo y lo conecta con una solución",
    },
    "contrast_resolution": {
        "relations": ("CONTR", "REFUT", "SOLV", "SUM"),
        "score": 0.78,
        "narrative_function": "contrasta u objeta una idea y ofrece cierre o resolución",
    },
    "example_or_analogy": {
        "relations": ("EXMP", "ANLG", "ELAB"),
        "score": 0.72,
        "narrative_function": "desarrolla una idea mediante ejemplo, analogía o elaboración",
    },
}
SEQUENCE_PATTERN_DEFINITIONS = {
    "problem_solution_call_sequence": {
        "required_steps": ({"X"}, {"S", "I", "U"}, {"V"}),
        "score": 0.78,
        "narrative_function": "mueve del riesgo a una recomendación y una llamada al espectador",
    },
    "claim_evidence_explanation_sequence": {
        "required_steps": ({"A", "K", "O"}, {"D", "Q"}, {"Y", "E"}),
        "score": 0.76,
        "narrative_function": "conecta claim, soporte y explicación o ejemplo",
    },
    "contrast_resolution_sequence": {
        "required_steps": ({"A", "K", "O"}, {"C", "B"}, {"S", "Z"}),
        "score": 0.74,
        "narrative_function": "marca tensión narrativa y la cierra con solución o conclusión",
    },
    "procedural_sequence": {
        "required_steps": ({"L", "T"}, {"I"}, {"U", "S", "Z"}),
        "score": 0.7,
        "narrative_function": "ordena pasos o lista hacia utilidad, solución o cierre",
    },
}


def detect_chains_for_document(
    document: NarrativeDocument,
    *,
    run_id: str = "run_unknown",
    min_score: float = DEFAULT_MIN_SCORE,
    max_chain_length: int = DEFAULT_MAX_CHAIN_LENGTH,
) -> NarrativeDocument:
    """Return a document with deterministic narrative chains attached."""

    chains = detect_chains(
        document.units,
        document.relations,
        run_id=run_id,
        min_score=min_score,
        max_chain_length=max_chain_length,
    )
    payload = document.model_dump(mode="json")
    payload["chains"] = [chain.model_dump(mode="json") for chain in chains]
    payload["audit_summary"] = {
        **document.audit_summary,
        "chain_count": len(chains),
        "chains_by_type": dict(Counter(chain.chain_type for chain in chains)),
        "taxonomy_version_effective": DEFAULT_TAXONOMY_VERSION,
        "prompt_version_effective": DEFAULT_PROMPT_VERSION,
        "validator_version_effective": DEFAULT_VALIDATOR_VERSION,
    }
    return NarrativeDocument.model_validate(payload)


def detect_chains(
    units: list[NarrativeUnit],
    relations: list[NarrativeRelation],
    *,
    run_id: str = "run_unknown",
    min_score: float = DEFAULT_MIN_SCORE,
    max_chain_length: int = DEFAULT_MAX_CHAIN_LENGTH,
) -> list[NarrativeChain]:
    """Detect conservative chains from relation graph and contiguous unit sequences."""

    unit_by_id = {unit.unit_id: unit for unit in units}
    ordered_units = sorted(units, key=lambda unit: unit.sequence_index)
    candidates = [
        *relation_based_chains(
            ordered_units,
            relations,
            unit_by_id=unit_by_id,
            run_id=run_id,
            max_chain_length=max_chain_length,
        ),
        *sequence_based_chains(
            ordered_units,
            run_id=run_id,
            max_chain_length=max_chain_length,
        ),
    ]
    deduped: dict[tuple[str, tuple[str, ...], tuple[str, ...]], NarrativeChain] = {}
    for chain in candidates:
        if chain.score < min_score:
            continue
        key = (chain.chain_type, tuple(chain.unit_ids), tuple(chain.relation_ids))
        existing = deduped.get(key)
        if existing is None or chain.score > existing.score:
            deduped[key] = chain
    return sorted(
        deduped.values(),
        key=lambda chain: (
            unit_by_id[chain.start_unit_id].sequence_index
            if chain.start_unit_id in unit_by_id
            else 0,
            chain.chain_type,
        ),
    )


def relation_based_chains(
    units: list[NarrativeUnit],
    relations: list[NarrativeRelation],
    *,
    unit_by_id: dict[str, NarrativeUnit],
    run_id: str,
    max_chain_length: int,
) -> list[NarrativeChain]:
    chains: list[NarrativeChain] = []
    relations_by_target: dict[str, list[NarrativeRelation]] = {}
    relations_by_source: dict[str, list[NarrativeRelation]] = {}
    for relation in relations:
        relations_by_target.setdefault(relation.target_unit_id, []).append(relation)
        relations_by_source.setdefault(relation.source_unit_id, []).append(relation)

    for chain_type, definition in RELATION_PATTERN_DEFINITIONS.items():
        relation_types = set(definition["relations"])
        for anchor in units:
            matching = [
                relation
                for relation in relations_by_target.get(anchor.unit_id, [])
                + relations_by_source.get(anchor.unit_id, [])
                if str(relation.relation_type) in relation_types
            ]
            if not matching:
                continue
            selected = select_compact_relations(matching, max_chain_length=max_chain_length)
            unit_ids = ordered_unit_ids_from_relations(selected, unit_by_id)
            if len(unit_ids) < 2:
                continue
            chains.append(
                build_chain(
                    run_id=run_id,
                    chain_type=chain_type,
                    units=[unit_by_id[unit_id] for unit_id in unit_ids],
                    relation_ids=[relation.relation_id for relation in selected],
                    score=relation_chain_score(float(definition["score"]), selected),
                    narrative_function=str(definition["narrative_function"]),
                    evidence_summary=relation_evidence_summary(selected),
                    evidence_source=f"chain_detector:{chain_type}",
                )
            )
    return chains


def sequence_based_chains(
    units: list[NarrativeUnit],
    *,
    run_id: str,
    max_chain_length: int,
) -> list[NarrativeChain]:
    chains: list[NarrativeChain] = []
    for chain_type, definition in SEQUENCE_PATTERN_DEFINITIONS.items():
        required_steps = definition["required_steps"]
        for index in range(len(units)):
            selected = match_sequence_pattern(
                units[index : index + max_chain_length],
                required_steps=required_steps,
            )
            if len(selected) != len(required_steps):
                continue
            chains.append(
                build_chain(
                    run_id=run_id,
                    chain_type=chain_type,
                    units=selected,
                    relation_ids=[],
                    score=float(definition["score"]),
                    narrative_function=str(definition["narrative_function"]),
                    evidence_summary=" -> ".join(unit.final_notation for unit in selected),
                    evidence_source=f"chain_detector:{chain_type}",
                )
            )
    return chains


def build_chain(
    *,
    run_id: str,
    chain_type: str,
    units: list[NarrativeUnit],
    relation_ids: list[str],
    score: float,
    narrative_function: str,
    evidence_summary: str,
    evidence_source: str,
) -> NarrativeChain:
    ordered = sorted(units, key=lambda unit: unit.sequence_index)
    unit_ids = [unit.unit_id for unit in ordered]
    needs_review = score < 0.72 or (len(unit_ids) < 3 and not relation_ids)
    flags = []
    if needs_review:
        flags.append(
            ValidatorFlag(
                rule_id="chain_needs_review",
                severity="warning",
                message="Chain is plausible but below high-confidence structure threshold.",
                field="chain_type",
            )
        )
    return NarrativeChain(
        run_id=run_id,
        chain_id=chain_id(run_id, chain_type, unit_ids, relation_ids),
        document_id=ordered[0].document_id,
        chain_type=chain_type,
        unit_ids=unit_ids,
        relation_ids=relation_ids,
        notation_sequence=[unit.final_notation for unit in ordered],
        start_unit_id=unit_ids[0],
        end_unit_id=unit_ids[-1],
        score=round(score, 4),
        narrative_function=narrative_function,
        evidence_spans=[
            EvidenceSpan(
                text=evidence_summary,
                source=evidence_source,
            )
        ],
        evidence_summary=evidence_summary,
        validator_flags=flags,
        needs_review=needs_review,
        taxonomy_version_effective=DEFAULT_TAXONOMY_VERSION,
        prompt_version_effective=DEFAULT_PROMPT_VERSION,
        validator_version_effective=DEFAULT_VALIDATOR_VERSION,
    )


def detect_chains_for_run(
    *,
    run_id: str,
    outputs_dir: str | Path = "outputs",
    min_score: float = DEFAULT_MIN_SCORE,
    max_chain_length: int = DEFAULT_MAX_CHAIN_LENGTH,
) -> tuple[list[NarrativeDocument], list[NarrativeChain]]:
    """Load run documents, attach relations if needed, detect chains, and write outputs."""

    run_dir = Path(outputs_dir) / run_id
    relations_from_file = load_run_relations(run_dir)
    documents = [
        detect_chains_for_document(
            document_with_relations(document, relations_from_file),
            run_id=run_id,
            min_score=min_score,
            max_chain_length=max_chain_length,
        )
        for document in load_run_documents(run_dir)
    ]
    chains = [chain for document in documents for chain in document.chains]
    write_chain_outputs(run_dir, documents, chains)
    return documents, chains


def write_chain_outputs(
    run_dir: str | Path,
    documents: list[NarrativeDocument],
    chains: list[NarrativeChain],
) -> tuple[Path, Path]:
    """Write updated documents and chains JSONL as derived outputs."""

    destination = Path(run_dir)
    documents_path = destination / "documents.jsonl"
    chains_path = destination / "chains.jsonl"
    documents_path.write_text(
        "\n".join(
            json.dumps(document.model_dump(mode="json"), ensure_ascii=False)
            for document in documents
        )
        + ("\n" if documents else ""),
        encoding="utf-8",
    )
    chains_path.write_text(
        "\n".join(json.dumps(chain.model_dump(mode="json"), ensure_ascii=False) for chain in chains)
        + ("\n" if chains else ""),
        encoding="utf-8",
    )
    return documents_path, chains_path


def load_run_relations(run_dir: str | Path) -> list[NarrativeRelation]:
    path = Path(run_dir) / "relations.jsonl"
    if not path.exists():
        return []
    return [
        NarrativeRelation.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def document_with_relations(
    document: NarrativeDocument, relations: list[NarrativeRelation]
) -> NarrativeDocument:
    if document.relations:
        return document
    related = [relation for relation in relations if relation.document_id == document.document_id]
    if not related:
        return document
    payload = document.model_dump(mode="json")
    payload["relations"] = [relation.model_dump(mode="json") for relation in related]
    return NarrativeDocument.model_validate(payload)


def select_compact_relations(
    relations: list[NarrativeRelation], *, max_chain_length: int
) -> list[NarrativeRelation]:
    selected = sorted(
        relations,
        key=lambda relation: (relation.confidence, relation.relation_id),
        reverse=True,
    )[: max(1, max_chain_length - 1)]
    return sorted(selected, key=lambda relation: relation.relation_id)


def ordered_unit_ids_from_relations(
    relations: list[NarrativeRelation],
    unit_by_id: dict[str, NarrativeUnit],
) -> list[str]:
    unit_ids = {relation.source_unit_id for relation in relations} | {
        relation.target_unit_id for relation in relations
    }
    known = [unit_by_id[unit_id] for unit_id in unit_ids if unit_id in unit_by_id]
    return [unit.unit_id for unit in sorted(known, key=lambda unit: unit.sequence_index)]


def relation_chain_score(base: float, relations: list[NarrativeRelation]) -> float:
    if not relations:
        return base
    average_confidence = sum(relation.confidence for relation in relations) / len(relations)
    review_penalty = 0.08 if any(relation.needs_review for relation in relations) else 0.0
    return max(0.0, min(1.0, (base + average_confidence) / 2 - review_penalty))


def relation_evidence_summary(relations: list[NarrativeRelation]) -> str:
    parts = [
        f"{relation.relation_type}:{relation.source_unit_id}->{relation.target_unit_id}"
        for relation in relations
    ]
    return "; ".join(parts)


def match_sequence_pattern(
    units: list[NarrativeUnit],
    *,
    required_steps: tuple[set[str], ...],
) -> list[NarrativeUnit]:
    selected: list[NarrativeUnit] = []
    step_index = 0
    last_sequence_index: int | None = None
    for unit in units:
        if step_index >= len(required_steps):
            break
        if last_sequence_index is not None and unit.sequence_index - last_sequence_index > 2:
            break
        if unit_matches_step(unit, required_steps[step_index]):
            selected.append(unit)
            step_index += 1
            last_sequence_index = unit.sequence_index
    return selected


def unit_matches_step(unit: NarrativeUnit, accepted_functions: set[str]) -> bool:
    return bool({str(function) for function in unit.functions} & accepted_functions)


def chain_summary(chains: list[NarrativeChain]) -> dict[str, Any]:
    return {
        "chain_count": len(chains),
        "chains_by_type": dict(Counter(chain.chain_type for chain in chains)),
        "needs_review_count": sum(1 for chain in chains if chain.needs_review),
        "taxonomy_version_effective": DEFAULT_TAXONOMY_VERSION,
        "prompt_version_effective": DEFAULT_PROMPT_VERSION,
        "validator_version_effective": DEFAULT_VALIDATOR_VERSION,
    }


def chain_id(
    run_id: str,
    chain_type: str,
    unit_ids: list[str],
    relation_ids: list[str],
) -> str:
    text = f"{run_id}::{chain_type}::{'|'.join(unit_ids)}::{'|'.join(relation_ids)}"
    return f"chain_{hashlib.sha256(text.encode()).hexdigest()[:16]}"
