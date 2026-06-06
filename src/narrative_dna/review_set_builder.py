"""Review set construction entry points."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from narrative_dna.adjudicator import select_decision_tree
from narrative_dna.models import (
    NarrativeDocument,
    NarrativeUnit,
    SimilarityConflict,
    SyntheticReviewItem,
    SyntheticReviewManifest,
)
from narrative_dna.similarity_auditor import load_run_documents

DEFAULT_TAXONOMY_VERSION = "v1_0"
DEFAULT_PROMPT_VERSION = "v1_0"
DEFAULT_VALIDATOR_VERSION = "v1_0"
DEFAULT_MINIMAL_PAIRS_PATH = Path("annotation_guidelines/minimal_pairs_v1_0.jsonl")
DEFAULT_TAXONOMY_PATH = Path("annotation_guidelines/taxonomy_v1_0.json")
DEFAULT_DECISION_TREES_PATH = Path("annotation_guidelines/decision_trees_v1_0.md")
CONFUSION_GROUPS: tuple[tuple[str, ...], ...] = (
    ("A", "K", "O"),
    ("R", "Y"),
    ("D", "Q", "K"),
    ("E", "H", "G"),
    ("S", "I", "U"),
    ("C", "B", "X"),
    ("T", "M", "L", "Z"),
)

ItemType = Literal["unit", "similar_pair", "minimal_pair", "relation", "chain"]
Difficulty = Literal["easy", "medium", "hard", "adversarial"]
ReviewGoal = Literal["validate", "find_alternative", "resolve_confusion", "test_boundary"]
ReviewSetItem = SyntheticReviewItem
ReviewSetManifest = SyntheticReviewManifest


def build_review_set(
    *,
    run_id: str,
    outputs_dir: str | Path = "outputs",
    minimal_pairs_path: str | Path = DEFAULT_MINIMAL_PAIRS_PATH,
    taxonomy_path: str | Path = DEFAULT_TAXONOMY_PATH,
    decision_trees_path: str | Path = DEFAULT_DECISION_TREES_PATH,
    high_confidence_sample_size: int = 10,
) -> tuple[list[ReviewSetItem], ReviewSetManifest]:
    """Build a synthetic-review set from run outputs."""

    run_dir = Path(outputs_dir) / run_id
    documents = load_run_documents(run_dir)
    units = [unit for document in documents for unit in document.units]
    conflicts = load_similarity_conflicts(run_dir)
    minimal_pairs = load_minimal_pairs(minimal_pairs_path)
    taxonomy_rules = load_taxonomy_rules(taxonomy_path)
    decision_trees = read_text(decision_trees_path)
    items: list[ReviewSetItem] = []
    seen: set[str] = set()

    conflict_by_unit = _conflicts_by_unit(conflicts)
    for unit in units:
        reasons = unit_review_reasons(unit, conflict_by_unit.get(unit.unit_id, []))
        if reasons:
            item = build_unit_review_item(
                unit=unit,
                all_units=units,
                reasons=reasons,
                conflicts=conflict_by_unit.get(unit.unit_id, []),
                taxonomy_rules=taxonomy_rules,
                decision_trees=decision_trees,
                minimal_pairs=minimal_pairs,
            )
            add_unique_item(items, seen, item)

    for conflict in conflicts:
        item = build_similarity_pair_item(
            conflict=conflict,
            units_by_id={unit.unit_id: unit for unit in units},
            all_units=units,
            taxonomy_rules=taxonomy_rules,
            decision_trees=decision_trees,
            minimal_pairs=minimal_pairs,
        )
        if item:
            add_unique_item(items, seen, item)

    for unit in high_confidence_units(units, limit=high_confidence_sample_size):
        item = build_unit_review_item(
            unit=unit,
            all_units=units,
            reasons=["high_confidence_quality_control"],
            conflicts=[],
            taxonomy_rules=taxonomy_rules,
            decision_trees=decision_trees,
            minimal_pairs=minimal_pairs,
            expected_difficulty="easy",
            review_goal="validate",
        )
        add_unique_item(items, seen, item)

    for pair in minimal_pairs:
        add_unique_item(items, seen, build_minimal_pair_item(pair, taxonomy_rules, decision_trees))

    manifest = build_manifest(
        run_id=run_id,
        items=items,
        documents=documents,
        conflicts=conflicts,
    )
    return items, manifest


def write_review_set(
    *,
    run_id: str,
    items: list[ReviewSetItem],
    manifest: ReviewSetManifest,
    outputs_dir: str | Path = "outputs",
) -> tuple[Path, Path]:
    review_dir = Path(outputs_dir) / run_id / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    items_path = review_dir / "review_items.jsonl"
    manifest_path = review_dir / "review_manifest.json"
    items_path.write_text(
        "\n".join(json.dumps(item.model_dump(mode="json"), ensure_ascii=False) for item in items)
        + ("\n" if items else ""),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return items_path, manifest_path


def build_and_write_review_set(
    *,
    run_id: str,
    outputs_dir: str | Path = "outputs",
) -> tuple[list[ReviewSetItem], ReviewSetManifest]:
    items, manifest = build_review_set(run_id=run_id, outputs_dir=outputs_dir)
    write_review_set(run_id=run_id, items=items, manifest=manifest, outputs_dir=outputs_dir)
    return items, manifest


def unit_review_reasons(unit: NarrativeUnit, conflicts: list[SimilarityConflict]) -> list[str]:
    reasons: list[str] = []
    if unit.needs_review:
        reasons.append("needs_review")
    if unit.validator_flags:
        reasons.append("validator_flags")
    if conflicts:
        reasons.append("similarity_conflict")
    if confusable_labels(unit):
        reasons.append("confusable_functions")
    if unit.emotion_intensity >= 3:
        reasons.append("intense_emotion")
    if unit.emotions_mentioned:
        reasons.append("emotions_mentioned")
    if len(unit.functions) > 3:
        reasons.append("many_functions")
    if unit.confidence < 0.85:
        reasons.append("low_or_medium_confidence")
    return reasons


def build_unit_review_item(
    *,
    unit: NarrativeUnit,
    all_units: list[NarrativeUnit],
    reasons: list[str],
    conflicts: list[SimilarityConflict],
    taxonomy_rules: dict[str, dict[str, Any]],
    decision_trees: str,
    minimal_pairs: list[dict[str, Any]],
    expected_difficulty: Difficulty | None = None,
    review_goal: ReviewGoal | None = None,
) -> ReviewSetItem:
    labels = sorted({str(function) for function in unit.functions} | set(confusable_labels(unit)))
    conflict_info = conflicts[0].model_dump(mode="json") if conflicts else None
    return ReviewSetItem(
        review_item_id=_review_id("unit", unit.unit_id, ",".join(reasons)),
        item_type="unit",
        document_id=unit.document_id,
        unit_id=unit.unit_id,
        unit_ids=[unit.unit_id],
        text=unit.text,
        context_before=context_texts(unit, all_units, before=True),
        context_after=context_texts(unit, all_units, before=False),
        current_prediction_json=unit.model_dump(mode="json"),
        current_notation=unit.final_notation,
        relevant_taxonomy_rules=rules_for_labels(labels, taxonomy_rules),
        relevant_decision_tree=select_decision_tree(decision_trees, labels),
        relevant_minimal_pairs=select_minimal_pairs(minimal_pairs, labels),
        validator_flags=[flag.model_dump(mode="json") for flag in unit.validator_flags],
        similarity_conflict_info=conflict_info,
        expected_difficulty=expected_difficulty or difficulty_for_reasons(reasons),
        review_goal=review_goal or goal_for_reasons(reasons),
        taxonomy_version_effective=DEFAULT_TAXONOMY_VERSION,
        prompt_version_effective=DEFAULT_PROMPT_VERSION,
        validator_version_effective=DEFAULT_VALIDATOR_VERSION,
    )


def build_similarity_pair_item(
    *,
    conflict: SimilarityConflict,
    units_by_id: dict[str, NarrativeUnit],
    all_units: list[NarrativeUnit],
    taxonomy_rules: dict[str, dict[str, Any]],
    decision_trees: str,
    minimal_pairs: list[dict[str, Any]],
) -> ReviewSetItem | None:
    unit_a = units_by_id.get(conflict.unit_id_a)
    unit_b = units_by_id.get(conflict.unit_id_b)
    if not unit_a or not unit_b:
        return None
    labels = sorted(
        {str(function) for function in unit_a.functions}
        | {str(function) for function in unit_b.functions}
    )
    return ReviewSetItem(
        review_item_id=_review_id("similar_pair", conflict.conflict_id),
        item_type="similar_pair",
        document_id=unit_a.document_id,
        unit_ids=[unit_a.unit_id, unit_b.unit_id],
        text=f"{unit_a.text}\n---\n{unit_b.text}",
        context_before=context_texts(unit_a, all_units, before=True),
        context_after=context_texts(unit_b, all_units, before=False),
        current_prediction_json={
            unit_a.unit_id: unit_a.model_dump(mode="json"),
            unit_b.unit_id: unit_b.model_dump(mode="json"),
        },
        current_notation=f"{unit_a.final_notation} / {unit_b.final_notation}",
        relevant_taxonomy_rules=rules_for_labels(labels, taxonomy_rules),
        relevant_decision_tree=select_decision_tree(decision_trees, labels),
        relevant_minimal_pairs=select_minimal_pairs(minimal_pairs, labels),
        validator_flags=[],
        similarity_conflict_info=conflict.model_dump(mode="json"),
        expected_difficulty="hard",
        review_goal="resolve_confusion",
        taxonomy_version_effective=DEFAULT_TAXONOMY_VERSION,
        prompt_version_effective=DEFAULT_PROMPT_VERSION,
        validator_version_effective=DEFAULT_VALIDATOR_VERSION,
    )


def build_minimal_pair_item(
    pair: dict[str, Any],
    taxonomy_rules: dict[str, dict[str, Any]],
    decision_trees: str,
) -> ReviewSetItem:
    labels = pair.get("confusable_labels", [])
    return ReviewSetItem(
        review_item_id=_review_id("minimal_pair", str(pair.get("pair_id", ""))),
        item_type="minimal_pair",
        document_id="annotation_guidelines",
        unit_ids=[],
        text=f"{pair.get('text_a', '')}\n---\n{pair.get('text_b', '')}",
        context_before=[],
        context_after=[],
        current_prediction_json=pair,
        current_notation=None,
        relevant_taxonomy_rules=rules_for_labels(labels, taxonomy_rules),
        relevant_decision_tree=select_decision_tree(decision_trees, labels),
        relevant_minimal_pairs=[pair],
        validator_flags=[],
        similarity_conflict_info=None,
        expected_difficulty="adversarial",
        review_goal="test_boundary",
        taxonomy_version_effective=DEFAULT_TAXONOMY_VERSION,
        prompt_version_effective=DEFAULT_PROMPT_VERSION,
        validator_version_effective=DEFAULT_VALIDATOR_VERSION,
    )


def load_similarity_conflicts(run_dir: Path) -> list[SimilarityConflict]:
    path = run_dir / "similarity_conflicts.jsonl"
    if not path.exists():
        return []
    return [
        SimilarityConflict.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_minimal_pairs(
    path: str | Path = DEFAULT_MINIMAL_PAIRS_PATH,
    limit: int = 40,
) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    pairs: list[dict[str, Any]] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.strip():
            pairs.append(json.loads(line))
        if len(pairs) >= limit:
            break
    return pairs


def load_taxonomy_rules(path: str | Path = DEFAULT_TAXONOMY_PATH) -> dict[str, dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return {}
    payload = json.loads(source.read_text(encoding="utf-8"))
    return {
        item["code"]: {
            "code": item.get("code"),
            "name": item.get("name"),
            "definition": item.get("definition"),
            "boundary_rules": item.get("boundary_rules", [])[:3],
            "confusable_with": item.get("confusable_with", []),
        }
        for item in payload.get("functions", [])
        if item.get("code")
    }


def read_text(path: str | Path) -> str:
    source = Path(path)
    return source.read_text(encoding="utf-8") if source.exists() else ""


def context_texts(
    unit: NarrativeUnit,
    all_units: list[NarrativeUnit],
    *,
    before: bool,
) -> list[str]:
    offsets = [-2, -1] if before else [1, 2]
    texts: list[str] = []
    for offset in offsets:
        target = unit.sequence_index + offset
        for candidate in all_units:
            if candidate.document_id == unit.document_id and candidate.sequence_index == target:
                texts.append(candidate.text)
                break
    return texts


def confusable_labels(unit: NarrativeUnit) -> list[str]:
    labels = {str(function) for function in unit.functions}
    selected: set[str] = set()
    for group in CONFUSION_GROUPS:
        if labels & set(group):
            selected.update(group)
    return sorted(selected)


def rules_for_labels(
    labels: list[str],
    taxonomy_rules: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [taxonomy_rules[label] for label in labels if label in taxonomy_rules]


def select_minimal_pairs(
    minimal_pairs: list[dict[str, Any]],
    labels: list[str],
    limit: int = 5,
) -> list[dict[str, Any]]:
    label_set = set(labels)
    selected = [
        pair for pair in minimal_pairs if label_set & set(pair.get("confusable_labels", []))
    ]
    return (selected or minimal_pairs)[:limit]


def high_confidence_units(units: list[NarrativeUnit], *, limit: int) -> list[NarrativeUnit]:
    selected = [
        unit
        for unit in units
        if unit.confidence >= 0.85 and not unit.needs_review and not unit.validator_flags
    ]
    return sorted(selected, key=lambda unit: (-unit.confidence, unit.unit_id))[:limit]


def difficulty_for_reasons(reasons: list[str]) -> Difficulty:
    if "similarity_conflict" in reasons or "confusable_functions" in reasons:
        return "hard"
    if "validator_flags" in reasons or "needs_review" in reasons:
        return "medium"
    if "low_or_medium_confidence" in reasons:
        return "medium"
    return "easy"


def goal_for_reasons(reasons: list[str]) -> ReviewGoal:
    if "similarity_conflict" in reasons or "confusable_functions" in reasons:
        return "resolve_confusion"
    if "validator_flags" in reasons or "needs_review" in reasons:
        return "find_alternative"
    return "validate"


def build_manifest(
    *,
    run_id: str,
    items: list[ReviewSetItem],
    documents: list[NarrativeDocument],
    conflicts: list[SimilarityConflict],
) -> ReviewSetManifest:
    return ReviewSetManifest(
        run_id=run_id,
        item_count=len(items),
        counts_by_item_type=count_by(items, "item_type"),
        counts_by_review_goal=count_by(items, "review_goal"),
        source_documents=len(documents),
        source_units=sum(len(document.units) for document in documents),
        source_similarity_conflicts=len(conflicts),
        taxonomy_version_effective=DEFAULT_TAXONOMY_VERSION,
        prompt_version_effective=DEFAULT_PROMPT_VERSION,
        validator_version_effective=DEFAULT_VALIDATOR_VERSION,
    )


def count_by(items: list[ReviewSetItem], field_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = str(getattr(item, field_name))
        counts[key] = counts.get(key, 0) + 1
    return counts


def _conflicts_by_unit(conflicts: list[SimilarityConflict]) -> dict[str, list[SimilarityConflict]]:
    grouped: dict[str, list[SimilarityConflict]] = {}
    for conflict in conflicts:
        grouped.setdefault(conflict.unit_id_a, []).append(conflict)
        grouped.setdefault(conflict.unit_id_b, []).append(conflict)
    return grouped


def add_unique_item(items: list[ReviewSetItem], seen: set[str], item: ReviewSetItem) -> None:
    if item.review_item_id in seen:
        return
    seen.add(item.review_item_id)
    items.append(item)


def _review_id(*parts: str) -> str:
    text = "::".join(parts)
    return f"review_{hashlib.sha256(text.encode()).hexdigest()[:16]}"
