"""Conservative adjudication entry points."""

from __future__ import annotations

import json
from collections.abc import Mapping
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from pydantic import Field

from narrative_dna.heuristic_candidates import extract_heuristic_candidates
from narrative_dna.llm_client import LLMCallResult, OpenAIStructuredClient
from narrative_dna.models import (
    Certainty,
    EmotionCode,
    EvidenceSpan,
    FunctionCode,
    NarrativeDocument,
    NarrativeUnit,
    RejectedLabel,
    Stance,
    StrictBaseModel,
    ValidatorFlag,
)
from narrative_dna.notation import derive_final_notation, normalize_function_codes
from narrative_dna.timing import TimingRecorder, json_size_chars
from narrative_dna.validators import ValidationContext, normalize_and_validate_unit

DEFAULT_TAXONOMY_VERSION = "v1_0"
DEFAULT_PROMPT_VERSION = "v1_0"
DEFAULT_VALIDATOR_VERSION = "v1_0"
DEFAULT_PROMPT_PATH = Path("prompts/adjudicator.md")
DEFAULT_DECISION_TREES_PATH = Path("annotation_guidelines/decision_trees_v1_0.md")
DEFAULT_MINIMAL_PAIRS_PATH = Path("annotation_guidelines/minimal_pairs_v1_0.jsonl")
CONFUSION_GROUPS: tuple[tuple[str, ...], ...] = (
    ("A", "K", "O"),
    ("R", "Y"),
    ("E", "H", "G"),
    ("S", "I", "U"),
    ("C", "B", "X"),
)
HIGH_RISK_FLAGS = {
    "D_without_evidence",
    "R_without_question_anchor",
    "possible_overlabeling",
}


class AdjudicatedClassification(StrictBaseModel):
    final_functions: list[FunctionCode] = Field(min_length=1)
    final_primary_function: FunctionCode
    final_secondary_functions: list[FunctionCode] = Field(default_factory=list)
    final_certainty: Certainty
    final_emotion_expressed: EmotionCode
    final_emotion_intensity: int = Field(ge=0, le=3)
    final_emotions_mentioned: list[EmotionCode] = Field(default_factory=list)
    final_stance: Stance
    final_target: str | None = None
    final_speech_act: str | None = None
    final_logic: dict[str, Any] | None = None
    final_evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    final_rejected_labels: list[RejectedLabel] = Field(default_factory=list)
    final_confidence: float = Field(ge=0, le=1)
    final_needs_review: bool
    adjudication_reason_summary: str = Field(min_length=1)
    changed_fields: list[str] = Field(default_factory=list)


class AdjudicationContext(StrictBaseModel):
    unit: dict[str, Any]
    previous_units: list[dict[str, Any]] = Field(default_factory=list)
    next_units: list[dict[str, Any]] = Field(default_factory=list)
    initial_classification: dict[str, Any]
    heuristics: dict[str, Any]
    validator_flags: list[dict[str, Any]]
    risk_reasons: list[str]
    confusable_labels: list[str]
    minimal_pairs_relevant: list[dict[str, Any]] = Field(default_factory=list)
    decision_tree_relevant: str


class ConservativeAdjudicator:
    """Resolve high-risk classifications with a conservative structured adjudicator."""

    def __init__(
        self,
        *,
        llm_client: Any | None = None,
        profile_name: str = "adjudicator",
        prompt_path: str | Path = DEFAULT_PROMPT_PATH,
        decision_trees_path: str | Path = DEFAULT_DECISION_TREES_PATH,
        minimal_pairs_path: str | Path = DEFAULT_MINIMAL_PAIRS_PATH,
        taxonomy_version: str = DEFAULT_TAXONOMY_VERSION,
        prompt_version: str = DEFAULT_PROMPT_VERSION,
        validator_version: str = DEFAULT_VALIDATOR_VERSION,
        dry_run: bool = False,
        timing_recorder: TimingRecorder | None = None,
        log_timings: bool | None = None,
    ) -> None:
        self.llm_client = llm_client or OpenAIStructuredClient(
            timing_recorder=timing_recorder,
            log_timings=log_timings,
        )
        self.timing_recorder = timing_recorder or getattr(self.llm_client, "timing_recorder", None)
        self.profile_name = profile_name
        self.prompt_path = Path(prompt_path)
        self.decision_trees_path = Path(decision_trees_path)
        self.minimal_pairs_path = Path(minimal_pairs_path)
        self.taxonomy_version = taxonomy_version
        self.prompt_version = prompt_version
        self.validator_version = validator_version
        self.dry_run = dry_run
        self.system_prompt = self._read_text(self.prompt_path)
        self.decision_trees = self._read_text(self.decision_trees_path)
        self.minimal_pairs = self._load_minimal_pairs()

    def adjudicate_document(
        self,
        document: NarrativeDocument,
        *,
        high_similarity_conflict_unit_ids: set[str] | None = None,
    ) -> NarrativeDocument:
        with self._timing_span(
            "adjudicator.document",
            document_id=document.document_id,
            unit_count=len(document.units),
            profile_name=self.profile_name,
        ) as timing:
            conflict_ids = high_similarity_conflict_unit_ids or set()
            units = [
                self.adjudicate_unit(
                    document,
                    index,
                    high_similarity_conflict=document.units[index].unit_id in conflict_ids,
                )
                for index in range(len(document.units))
            ]
            adjudicated_count = sum(1 for unit in units if unit.method == "adjudicated")
            payload = document.model_dump(mode="json")
            payload["units"] = [unit.model_dump(mode="json") for unit in units]
            payload["audit_summary"] = {
                **document.audit_summary,
                "adjudicated_unit_count": adjudicated_count,
                "adjudicator_profile": self.profile_name,
                "taxonomy_version_effective": self.taxonomy_version,
                "prompt_version_effective": self.prompt_version,
                "validator_version_effective": self.validator_version,
            }
            timing["adjudicated_unit_count"] = adjudicated_count
            timing["skipped_unit_count"] = len(units) - adjudicated_count
            return NarrativeDocument.model_validate(payload)

    def adjudicate_unit(
        self,
        document: NarrativeDocument,
        unit_index: int,
        *,
        high_similarity_conflict: bool = False,
    ) -> NarrativeUnit:
        unit = document.units[unit_index]
        with self._timing_span(
            "adjudicator.unit",
            document_id=document.document_id,
            unit_id=unit.unit_id,
            unit_index=unit_index,
            unit_chars=len(unit.text),
            profile_name=self.profile_name,
        ) as timing:
            risk_reasons = adjudication_risk_reasons(
                unit,
                high_similarity_conflict=high_similarity_conflict,
            )
            timing["risk_reasons"] = risk_reasons
            if not risk_reasons:
                timing["skipped"] = True
                timing.update(_unit_timing_outcome(unit))
                return unit

            with self._timing_span(
                "adjudicator.build_context",
                document_id=document.document_id,
                unit_id=unit.unit_id,
                unit_index=unit_index,
                risk_reasons=risk_reasons,
            ) as context_timing:
                context = build_adjudication_context(
                    document=document,
                    unit_index=unit_index,
                    risk_reasons=risk_reasons,
                    decision_trees=self.decision_trees,
                    minimal_pairs=self.minimal_pairs,
                )
                context_payload = context.model_dump(mode="json")
                context_timing["payload_chars"] = json_size_chars(context_payload)
            timing["payload_chars"] = json_size_chars(context_payload)
            result = self.llm_client.request_structured(
                profile_name=self.profile_name,
                input_payload=context_payload,
                response_model=AdjudicatedClassification,
                taxonomy_version=self.taxonomy_version,
                prompt_version=self.prompt_version,
                validator_version=self.validator_version,
                system_prompt=self.system_prompt,
                dry_run=self.dry_run,
            )
            timing.update(
                {
                    "skipped": False,
                    "llm_ok": result.ok,
                    "cache_hit": result.cache_hit,
                    "attempts": result.attempts,
                    "error_type": result.error_type,
                }
            )
            if not result.ok or not result.parsed:
                timing["fallback"] = True
                failed_unit = mark_adjudication_failed(unit, result)
                timing.update(_unit_timing_outcome(failed_unit))
                return failed_unit
            adjudicated = AdjudicatedClassification.model_validate(result.parsed)
            timing["fallback"] = False
            adjudicated_unit = apply_adjudication(
                unit=unit,
                adjudicated=adjudicated,
                llm_result=result,
                previous_text=document.units[unit_index - 1].text if unit_index > 0 else None,
                next_text=(
                    document.units[unit_index + 1].text
                    if unit_index + 1 < len(document.units)
                    else None
                ),
                taxonomy_version=self.taxonomy_version,
                prompt_version=self.prompt_version,
                validator_version=self.validator_version,
            )
            timing.update(_unit_timing_outcome(adjudicated_unit))
            return adjudicated_unit

    def _load_minimal_pairs(self, limit: int = 80) -> list[dict[str, Any]]:
        if not self.minimal_pairs_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.minimal_pairs_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rows.append(json.loads(line))
            if len(rows) >= limit:
                break
        return rows

    def _read_text(self, path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _timing_span(self, stage: str, **metadata: Any):
        if self.timing_recorder is None:
            return nullcontext({})
        return self.timing_recorder.span(stage, **metadata)


def adjudication_risk_reasons(
    unit: NarrativeUnit,
    *,
    high_similarity_conflict: bool = False,
) -> list[str]:
    reasons: list[str] = []
    flag_ids = {flag.rule_id for flag in unit.validator_flags}
    functions = [str(function) for function in unit.functions]
    locked = locked_functions_from_unit(unit)

    if unit.confidence < 0.70:
        reasons.append("low_confidence")
    for rule_id in sorted(flag_ids & HIGH_RISK_FLAGS):
        reasons.append(rule_id)
    if unit.emotion_intensity >= 3:
        reasons.append("high_emotion_intensity")
    if locked and not set(locked).issubset(set(functions)):
        reasons.append("locked_heuristic_llm_conflict")
    if len(functions) > 4:
        reasons.append("too_many_functions")
    if str(unit.primary_function) in confusable_primary_codes():
        reasons.append("confusable_primary_function")
    if high_similarity_conflict:
        reasons.append("high_similarity_conflict")
    return dedupe(reasons)


def should_adjudicate(
    unit: NarrativeUnit,
    *,
    high_similarity_conflict: bool = False,
) -> bool:
    return bool(adjudication_risk_reasons(unit, high_similarity_conflict=high_similarity_conflict))


def build_adjudication_context(
    *,
    document: NarrativeDocument,
    unit_index: int,
    risk_reasons: list[str],
    decision_trees: str,
    minimal_pairs: list[dict[str, Any]],
) -> AdjudicationContext:
    unit = document.units[unit_index]
    heuristics = extract_heuristic_candidates(unit, total_units=len(document.units))
    confusable = relevant_confusable_labels(unit)
    return AdjudicationContext.model_validate(
        {
            "unit": unit_context(unit),
            "previous_units": [
                unit_context(previous)
                for previous in document.units[max(0, unit_index - 3) : unit_index]
            ],
            "next_units": [
                unit_context(next_unit)
                for next_unit in document.units[unit_index + 1 : unit_index + 4]
            ],
            "initial_classification": initial_classification(unit),
            "heuristics": heuristics.model_dump(mode="json"),
            "validator_flags": [flag.model_dump(mode="json") for flag in unit.validator_flags],
            "risk_reasons": risk_reasons,
            "confusable_labels": confusable,
            "minimal_pairs_relevant": select_minimal_pairs(minimal_pairs, confusable),
            "decision_tree_relevant": select_decision_tree(decision_trees, confusable),
        }
    )


def apply_adjudication(
    *,
    unit: NarrativeUnit,
    adjudicated: AdjudicatedClassification,
    llm_result: LLMCallResult,
    previous_text: str | None = None,
    next_text: str | None = None,
    taxonomy_version: str = DEFAULT_TAXONOMY_VERSION,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    validator_version: str = DEFAULT_VALIDATOR_VERSION,
) -> NarrativeUnit:
    """Apply conservative adjudication and re-run deterministic validators."""

    payload = unit.model_dump(mode="json")
    adjudicated_payload = adjudicated.model_dump(mode="json")
    final_functions = conservative_final_functions(unit, adjudicated)
    primary = str(adjudicated_payload["final_primary_function"])
    if primary not in final_functions:
        primary = final_functions[0]

    payload.update(
        {
            "functions": final_functions,
            "primary_function": primary,
            "secondary_functions": [
                function
                for function in normalize_function_codes(
                    [*adjudicated_payload.get("final_secondary_functions", []), *final_functions]
                )
                if function != primary
            ],
            "certainty": adjudicated_payload["final_certainty"],
            "emotion_expressed": adjudicated_payload["final_emotion_expressed"],
            "emotion_intensity": adjudicated_payload["final_emotion_intensity"],
            "emotions_mentioned": adjudicated_payload["final_emotions_mentioned"],
            "stance": adjudicated_payload["final_stance"],
            "target": adjudicated_payload.get("final_target"),
            "speech_act": adjudicated_payload.get("final_speech_act"),
            "logic": adjudication_logic(unit, adjudicated, llm_result),
            "evidence_spans": adjudicated_payload.get("final_evidence_spans", []),
            "rejected_labels": adjudicated_payload.get("final_rejected_labels", []),
            "confidence": adjudicated_payload["final_confidence"],
            "method": "adjudicated",
            "needs_review": adjudicated_payload["final_needs_review"],
            "review_status": (
                "needs_review" if adjudicated_payload["final_needs_review"] else "accepted"
            ),
            "review_reasons": adjudication_review_reasons(unit, adjudicated),
            "taxonomy_version": taxonomy_version,
            "prompt_version": prompt_version,
            "validator_version": validator_version,
        }
    )
    payload["validator_flags"] = clear_resolved_high_risk_flags(payload)
    payload["validator_flags"] = append_flag(
        payload.get("validator_flags", []),
        rule_id="adjudication_applied",
        severity="info",
        message=adjudicated.adjudication_reason_summary,
        field="functions",
    )
    payload["final_notation"] = derive_final_notation(payload)
    return normalize_and_validate_unit(
        payload,
        context=ValidationContext(previous_text=previous_text, next_text=next_text),
    )


def mark_adjudication_failed(unit: NarrativeUnit, result: LLMCallResult) -> NarrativeUnit:
    payload = unit.model_dump(mode="json")
    payload["needs_review"] = True
    payload["review_status"] = "needs_review"
    payload["review_reasons"] = append_unique(
        payload.get("review_reasons", []), "adjudication_failed"
    )
    payload["validator_flags"] = append_flag(
        payload.get("validator_flags", []),
        rule_id="adjudication_failed",
        severity="warning",
        message=result.error or "Structured adjudication failed.",
        field="llm_votes",
    )
    payload["final_notation"] = derive_final_notation(payload)
    return NarrativeUnit.model_validate(payload)


def clear_resolved_high_risk_flags(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    functions = set(payload.get("functions", []))
    flags = list(payload.get("validator_flags", []))
    cleared: list[dict[str, Any]] = []
    for flag in flags:
        rule_id = flag.get("rule_id")
        if rule_id == "D_without_evidence" and "D" not in functions:
            continue
        if rule_id == "R_without_question_anchor" and "R" not in functions:
            continue
        if rule_id == "possible_overlabeling" and len(functions) <= 5:
            continue
        cleared.append(flag)
    return cleared


def adjudicate_document(
    document: NarrativeDocument,
    *,
    adjudicator: ConservativeAdjudicator | None = None,
) -> NarrativeDocument:
    return (adjudicator or ConservativeAdjudicator()).adjudicate_document(document)


def adjudicate_unit(
    document: NarrativeDocument,
    unit_index: int,
    *,
    adjudicator: ConservativeAdjudicator | None = None,
) -> NarrativeUnit:
    return (adjudicator or ConservativeAdjudicator()).adjudicate_unit(document, unit_index)


def conservative_final_functions(
    unit: NarrativeUnit,
    adjudicated: AdjudicatedClassification,
) -> list[str]:
    proposed = normalize_function_codes([str(function) for function in adjudicated.final_functions])
    if len(proposed) <= len(unit.functions):
        return proposed
    if adjudicated.final_evidence_spans:
        return proposed
    return normalize_function_codes([str(function) for function in unit.functions])


def adjudication_logic(
    unit: NarrativeUnit,
    adjudicated: AdjudicatedClassification,
    llm_result: LLMCallResult,
) -> dict[str, Any]:
    logic = dict(unit.logic or {})
    if adjudicated.final_logic:
        logic.update(adjudicated.final_logic)
    logic["adjudication"] = {
        "reason_summary": adjudicated.adjudication_reason_summary,
        "changed_fields": adjudicated.changed_fields,
        "cache_hit": llm_result.cache_hit,
        "usage": llm_result.usage,
    }
    return logic


def adjudication_review_reasons(
    unit: NarrativeUnit,
    adjudicated: AdjudicatedClassification,
) -> list[str]:
    reasons = list(unit.review_reasons)
    if adjudicated.final_needs_review:
        reasons = append_unique(reasons, "adjudicator_kept_review")
    return reasons


def locked_functions_from_unit(unit: NarrativeUnit) -> list[str]:
    locked: list[str] = []
    for candidate in unit.heuristic_candidates:
        if candidate.confidence >= 0.95 or "Locked deterministic" in candidate.reason:
            locked.append(str(candidate.label))
    return normalize_function_codes(locked)


def relevant_confusable_labels(unit: NarrativeUnit) -> list[str]:
    labels = {str(unit.primary_function), *[str(function) for function in unit.functions]}
    selected: set[str] = set()
    for group in CONFUSION_GROUPS:
        if labels & set(group):
            selected.update(group)
    return sorted(selected)


def select_minimal_pairs(
    minimal_pairs: list[dict[str, Any]],
    confusable_labels: list[str],
    limit: int = 6,
) -> list[dict[str, Any]]:
    labels = set(confusable_labels)
    selected: list[dict[str, Any]] = []
    for pair in minimal_pairs:
        if labels & set(pair.get("confusable_labels", [])):
            selected.append(pair)
        if len(selected) >= limit:
            return selected
    return minimal_pairs[:limit]


def select_decision_tree(decision_trees: str, confusable_labels: list[str]) -> str:
    section_ids = decision_tree_ids_for_labels(confusable_labels)
    if not decision_trees or not section_ids:
        return decision_trees
    sections = decision_trees.split("\n## ")
    selected: list[str] = []
    for section in sections:
        for section_id in section_ids:
            if section.startswith(section_id) or f"## {section_id}" in section:
                selected.append(section if section.startswith("#") else f"## {section}")
                break
    return "\n\n".join(selected) if selected else decision_trees


def decision_tree_ids_for_labels(labels: list[str]) -> list[str]:
    label_set = set(labels)
    mapping = {
        "DT_A_K_O": {"A", "K", "O"},
        "DT_P_R_Y": {"P", "R", "Y"},
        "DT_D_A_K_Q": {"D", "A", "K", "Q"},
        "DT_E_H_G": {"E", "H", "G"},
        "DT_S_I_U": {"S", "I", "U"},
        "DT_C_B_X": {"C", "B", "X"},
        "DT_T_M_L_Z": {"T", "M", "L", "Z"},
        "DT_EMOTION_EXPRESSED_MENTIONED": set(),
    }
    return [tree_id for tree_id, tree_labels in mapping.items() if label_set & tree_labels]


def initial_classification(unit: NarrativeUnit) -> dict[str, Any]:
    return {
        "functions": [str(function) for function in unit.functions],
        "primary_function": str(unit.primary_function),
        "secondary_functions": [str(function) for function in unit.secondary_functions],
        "certainty": str(unit.certainty),
        "emotion_expressed": str(unit.emotion_expressed),
        "emotion_intensity": unit.emotion_intensity,
        "emotions_mentioned": [str(emotion) for emotion in unit.emotions_mentioned],
        "stance": str(unit.stance),
        "confidence": unit.confidence,
        "needs_review": unit.needs_review,
        "review_reasons": unit.review_reasons,
        "final_notation": unit.final_notation,
    }


def unit_context(unit: NarrativeUnit) -> dict[str, Any]:
    return {
        "unit_id": unit.unit_id,
        "sequence_index": unit.sequence_index,
        "text": unit.text,
        "normalized_text": unit.normalized_text,
        "previous_unit_id": unit.previous_unit_id,
        "next_unit_id": unit.next_unit_id,
    }


def _unit_timing_outcome(unit: NarrativeUnit) -> dict[str, Any]:
    return {
        "output_functions": [str(function) for function in unit.functions],
        "output_primary_function": str(unit.primary_function),
        "output_final_notation": unit.final_notation,
        "output_confidence": unit.confidence,
        "output_needs_review": unit.needs_review,
        "output_method": str(unit.method),
    }


def confusable_primary_codes() -> set[str]:
    return {label for group in CONFUSION_GROUPS for label in group}


def append_flag(
    flags: list[dict[str, Any]],
    *,
    rule_id: str,
    severity: str,
    message: str,
    field: str,
) -> list[dict[str, Any]]:
    if any(flag.get("rule_id") == rule_id for flag in flags):
        return flags
    return [
        *flags,
        ValidatorFlag(
            rule_id=rule_id,
            severity=severity,
            message=message,
            field=field,
        ).model_dump(mode="json"),
    ]


def append_unique(values: list[str], value: str) -> list[str]:
    return values if value in values else [*values, value]


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped
