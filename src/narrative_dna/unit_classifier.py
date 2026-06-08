"""JSON-first unit classification entry points."""

from __future__ import annotations

import json
from collections.abc import Mapping
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from pydantic import Field

from narrative_dna.heuristic_candidates import (
    HeuristicExtraction,
    annotate_unit_with_heuristics,
    extract_heuristic_candidates,
)
from narrative_dna.llm_client import LLMCallResult, OpenAIStructuredClient
from narrative_dna.models import (
    Certainty,
    EmotionCode,
    EvidenceSpan,
    FunctionCode,
    NarrativeDocument,
    NarrativeUnit,
    RejectedLabel,
    ReviewStatus,
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
DEFAULT_PROMPT_PATH = Path("prompts/unit_classifier.md")
DEFAULT_TAXONOMY_PATH = Path("annotation_guidelines/taxonomy_v1_0.json")
DEFAULT_DECISION_TREES_PATH = Path("annotation_guidelines/decision_trees_v1_0.md")
DEFAULT_MINIMAL_PAIRS_PATH = Path("annotation_guidelines/minimal_pairs_v1_0.jsonl")
CONFUSION_GROUPS = [
    {"A", "K", "O"},
    {"P", "R", "Y"},
    {"D", "A", "K", "Q"},
    {"E", "H", "G"},
    {"S", "I", "U"},
    {"C", "B", "X"},
    {"T", "M", "L", "Z"},
]


class NarrativeUnitPartialClassification(StrictBaseModel):
    functions: list[FunctionCode] = Field(min_length=1)
    primary_function: FunctionCode
    secondary_functions: list[FunctionCode] = Field(default_factory=list)
    certainty: Certainty
    emotion_expressed: EmotionCode
    emotion_intensity: int = Field(ge=0, le=3)
    emotions_mentioned: list[EmotionCode] = Field(default_factory=list)
    stance: Stance
    target: str | None = None
    speech_act: str | None = None
    logic: dict[str, Any] | None = None
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    rejected_labels: list[RejectedLabel] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    needs_review: bool
    review_reasons: list[str] = Field(default_factory=list)


class ClassificationContext(StrictBaseModel):
    taxonomy_version: str = Field(min_length=1)
    unit: dict[str, Any]
    previous_units: list[dict[str, Any]] = Field(default_factory=list)
    next_units: list[dict[str, Any]] = Field(default_factory=list)
    heuristic_candidates: dict[str, Any]
    taxonomy_excerpt: dict[str, Any]
    decision_trees_excerpt: str
    minimal_pairs_excerpt: list[dict[str, Any]] = Field(default_factory=list)


class UnitClassifier:
    """Classify narrative units through the structured OpenAI client boundary."""

    def __init__(
        self,
        *,
        llm_client: Any | None = None,
        profile_name: str = "main_classifier",
        prompt_path: str | Path = DEFAULT_PROMPT_PATH,
        taxonomy_path: str | Path = DEFAULT_TAXONOMY_PATH,
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
        self.taxonomy_path = Path(taxonomy_path)
        self.decision_trees_path = Path(decision_trees_path)
        self.minimal_pairs_path = Path(minimal_pairs_path)
        self.taxonomy_version = taxonomy_version
        self.prompt_version = prompt_version
        self.validator_version = validator_version
        self.dry_run = dry_run
        self.system_prompt = self._read_text(self.prompt_path)
        self.taxonomy_excerpt = self._load_taxonomy_excerpt()
        self.decision_trees_excerpt = self._read_text(self.decision_trees_path)
        self.minimal_pairs = self._load_minimal_pairs()

    def classify_document(self, document: NarrativeDocument) -> NarrativeDocument:
        """Classify all units in a document without calling the adjudicator."""

        with self._timing_span(
            "classifier.document",
            document_id=document.document_id,
            unit_count=len(document.units),
            profile_name=self.profile_name,
        ) as timing:
            units: list[NarrativeUnit] = []
            for index, _unit in enumerate(document.units):
                units.append(self.classify_unit(document, index))
            payload = document.model_dump(mode="json")
            payload["units"] = [unit.model_dump(mode="json") for unit in units]
            payload["audit_summary"] = {
                **document.audit_summary,
                "classified_unit_count": len(units),
                "llm_profile": self.profile_name,
                "taxonomy_version_effective": self.taxonomy_version,
                "prompt_version_effective": self.prompt_version,
                "validator_version_effective": self.validator_version,
            }
            timing["classified_unit_count"] = len(units)
            return NarrativeDocument.model_validate(payload)

    def classify_unit(self, document: NarrativeDocument, unit_index: int) -> NarrativeUnit:
        """Classify one unit with local context and deterministic postprocessing."""

        unit = document.units[unit_index]
        with self._timing_span(
            "classifier.unit",
            document_id=document.document_id,
            unit_id=unit.unit_id,
            unit_index=unit_index,
            unit_chars=len(unit.text),
            profile_name=self.profile_name,
        ) as timing:
            heuristics = extract_heuristic_candidates(unit, total_units=len(document.units))
            minimal_pairs = self._minimal_pairs_for_unit(unit, heuristics)
            with self._timing_span(
                "classifier.build_context",
                document_id=document.document_id,
                unit_id=unit.unit_id,
                unit_index=unit_index,
                minimal_pairs=len(minimal_pairs),
            ) as context_timing:
                context = build_classification_context(
                    document=document,
                    unit_index=unit_index,
                    heuristics=heuristics,
                    taxonomy_excerpt=self.taxonomy_excerpt,
                    decision_trees_excerpt=self.decision_trees_excerpt,
                    minimal_pairs_excerpt=minimal_pairs,
                    taxonomy_version=self.taxonomy_version,
                )
                context_payload = context.model_dump(mode="json")
                context_timing["payload_chars"] = json_size_chars(context_payload)
            timing.update(
                {
                    "locked_functions": len(heuristics.locked_functions),
                    "candidate_functions": len(heuristics.candidate_functions),
                    "payload_chars": json_size_chars(context_payload),
                }
            )
            result = self.llm_client.request_structured(
                profile_name=self.profile_name,
                input_payload=context_payload,
                response_model=NarrativeUnitPartialClassification,
                taxonomy_version=self.taxonomy_version,
                prompt_version=self.prompt_version,
                validator_version=self.validator_version,
                system_prompt=self.system_prompt,
                dry_run=self.dry_run,
            )
            timing.update(
                {
                    "llm_ok": result.ok,
                    "cache_hit": result.cache_hit,
                    "attempts": result.attempts,
                    "error_type": result.error_type,
                }
            )
            if not result.ok or not result.parsed:
                timing["fallback"] = True
                fallback_unit = self._fallback_unit(unit, heuristics, result)
                timing.update(_unit_timing_outcome(fallback_unit))
                return fallback_unit
            partial = NarrativeUnitPartialClassification.model_validate(result.parsed)
            timing["fallback"] = False
            classified_unit = merge_partial_classification(
                unit=unit,
                partial=partial,
                heuristics=heuristics,
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
            timing.update(_unit_timing_outcome(classified_unit))
            return classified_unit

    def _fallback_unit(
        self,
        unit: NarrativeUnit,
        heuristics: HeuristicExtraction,
        result: LLMCallResult,
    ) -> NarrativeUnit:
        annotated = annotate_unit_with_heuristics(unit)
        payload = annotated.model_dump(mode="json")
        if heuristics.locked_functions:
            payload["functions"] = [str(function) for function in heuristics.locked_functions]
            payload["primary_function"] = payload["functions"][0]
            payload["secondary_functions"] = payload["functions"][1:]
            payload["method"] = "heuristic"
            payload["confidence"] = 0.6
        payload["needs_review"] = True
        payload["review_status"] = "needs_review"
        payload["review_reasons"] = _append_unique(
            payload.get("review_reasons", []), "llm_classification_failed"
        )
        payload["validator_flags"] = _append_flag(
            payload.get("validator_flags", []),
            rule_id="llm_classification_failed",
            severity="warning",
            message=result.error or "Structured LLM classification failed.",
            field="llm_votes",
        )
        payload["final_notation"] = derive_final_notation(payload)
        return normalize_and_validate_unit(payload)

    def _load_taxonomy_excerpt(self) -> dict[str, Any]:
        if not self.taxonomy_path.exists():
            return {"taxonomy_version": self.taxonomy_version, "functions": []}
        payload = json.loads(self.taxonomy_path.read_text(encoding="utf-8"))
        functions = []
        for item in payload.get("functions", []):
            functions.append(
                {
                    "code": item.get("code"),
                    "name": item.get("name"),
                    "definition": item.get("definition"),
                    "confusable_with": item.get("confusable_with", []),
                    "boundary_rules": item.get("boundary_rules", [])[:2],
                }
            )
        return {
            "taxonomy_version": payload.get("taxonomy_version", self.taxonomy_version),
            "function_codes": payload.get("function_codes", []),
            "functions": functions,
            "confusion_groups": [sorted(group) for group in CONFUSION_GROUPS],
        }

    def _load_minimal_pairs(self, limit: int = 40) -> list[dict[str, Any]]:
        if not self.minimal_pairs_path.exists():
            return []
        pairs: list[dict[str, Any]] = []
        for line in self.minimal_pairs_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            pairs.append(json.loads(line))
            if len(pairs) >= limit:
                break
        return pairs

    def _minimal_pairs_for_unit(
        self,
        unit: NarrativeUnit,
        heuristics: HeuristicExtraction,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        labels = {
            str(label) for label in heuristics.locked_functions + heuristics.candidate_functions
        }
        if not labels:
            return self.minimal_pairs[:limit]
        selected: list[dict[str, Any]] = []
        for pair in self.minimal_pairs:
            confusable = set(pair.get("confusable_labels", []))
            if labels & confusable:
                selected.append(pair)
            if len(selected) >= limit:
                return selected
        return self.minimal_pairs[:limit]

    def _read_text(self, path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _timing_span(self, stage: str, **metadata: Any):
        if self.timing_recorder is None:
            return nullcontext({})
        return self.timing_recorder.span(stage, **metadata)


def build_classification_context(
    *,
    document: NarrativeDocument,
    unit_index: int,
    heuristics: HeuristicExtraction,
    taxonomy_excerpt: Mapping[str, Any],
    decision_trees_excerpt: str,
    minimal_pairs_excerpt: list[dict[str, Any]],
    taxonomy_version: str,
) -> ClassificationContext:
    unit = document.units[unit_index]
    previous_units = document.units[max(0, unit_index - 2) : unit_index]
    next_units = document.units[unit_index + 1 : unit_index + 3]
    return ClassificationContext.model_validate(
        {
            "taxonomy_version": taxonomy_version,
            "unit": _unit_context(unit),
            "previous_units": [_unit_context(previous) for previous in previous_units],
            "next_units": [_unit_context(next_unit) for next_unit in next_units],
            "heuristic_candidates": heuristics.model_dump(mode="json"),
            "taxonomy_excerpt": dict(taxonomy_excerpt),
            "decision_trees_excerpt": decision_trees_excerpt,
            "minimal_pairs_excerpt": minimal_pairs_excerpt,
        }
    )


def merge_partial_classification(
    *,
    unit: NarrativeUnit,
    partial: NarrativeUnitPartialClassification,
    heuristics: HeuristicExtraction,
    llm_result: LLMCallResult,
    previous_text: str | None,
    next_text: str | None,
    taxonomy_version: str = DEFAULT_TAXONOMY_VERSION,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    validator_version: str = DEFAULT_VALIDATOR_VERSION,
) -> NarrativeUnit:
    """Merge structured LLM output with heuristic locks, then validate."""

    payload = unit.model_dump(mode="json")
    partial_payload = partial.model_dump(mode="json")
    locked = [str(function) for function in heuristics.locked_functions]
    llm_functions = [str(function) for function in partial_payload["functions"]]
    merged_functions = normalize_function_codes([*locked, *llm_functions])
    if not merged_functions:
        merged_functions = ["N"]

    primary = str(partial_payload["primary_function"])
    if locked:
        primary = locked[0]
    elif primary not in merged_functions:
        primary = merged_functions[0]

    payload.update(
        {
            "functions": merged_functions,
            "primary_function": primary,
            "secondary_functions": [
                function
                for function in normalize_function_codes(
                    [*partial_payload.get("secondary_functions", []), *merged_functions]
                )
                if function != primary
            ],
            "certainty": partial_payload["certainty"],
            "emotion_expressed": _merge_emotion_expressed(partial_payload, heuristics),
            "emotion_intensity": partial_payload["emotion_intensity"],
            "emotions_mentioned": _merge_emotions_mentioned(partial_payload, heuristics),
            "stance": _merge_stance(partial_payload, heuristics),
            "target": partial_payload.get("target"),
            "speech_act": partial_payload.get("speech_act"),
            "logic": partial_payload.get("logic"),
            "evidence_spans": _merge_evidence_spans(
                partial_payload.get("evidence_spans", []),
                heuristics.evidence_spans,
            ),
            "rejected_labels": partial_payload.get("rejected_labels", []),
            "heuristic_candidates": _heuristic_candidate_records(heuristics),
            "llm_votes": [],
            "confidence": partial_payload["confidence"],
            "method": "llm",
            "needs_review": partial_payload["needs_review"],
            "review_reasons": list(partial_payload.get("review_reasons", [])),
            "review_status": (
                ReviewStatus.NEEDS_REVIEW
                if partial_payload["needs_review"]
                else ReviewStatus.ACCEPTED
            ),
            "taxonomy_version": taxonomy_version,
            "prompt_version": prompt_version,
            "validator_version": validator_version,
        }
    )

    payload["review_reasons"] = _append_conflict_reviews(
        payload["review_reasons"],
        locked=locked,
        llm_functions=llm_functions,
    )
    if payload["review_reasons"]:
        payload["needs_review"] = True
        payload["review_status"] = "needs_review"

    payload["final_notation"] = derive_final_notation(payload)
    validated = normalize_and_validate_unit(
        payload,
        context=ValidationContext(previous_text=previous_text, next_text=next_text),
    )
    return _attach_llm_usage_flags(validated, llm_result)


def classify_unit(
    document: NarrativeDocument,
    unit_index: int,
    *,
    classifier: UnitClassifier | None = None,
) -> NarrativeUnit:
    return (classifier or UnitClassifier()).classify_unit(document, unit_index)


def classify_document(
    document: NarrativeDocument,
    *,
    classifier: UnitClassifier | None = None,
) -> NarrativeDocument:
    return (classifier or UnitClassifier()).classify_document(document)


def _unit_context(unit: NarrativeUnit) -> dict[str, Any]:
    return {
        "unit_id": unit.unit_id,
        "sequence_index": unit.sequence_index,
        "text": unit.text,
        "normalized_text": unit.normalized_text,
        "start_ms": unit.start_ms,
        "end_ms": unit.end_ms,
        "char_start": unit.char_start,
        "char_end": unit.char_end,
        "previous_unit_id": unit.previous_unit_id,
        "next_unit_id": unit.next_unit_id,
        "heuristic_candidates": [
            candidate.model_dump(mode="json") for candidate in unit.heuristic_candidates
        ],
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


def _heuristic_candidate_records(heuristics: HeuristicExtraction) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for function in heuristics.locked_functions:
        records.append(
            {
                "label": str(function),
                "confidence": 0.95,
                "reason": "Locked deterministic heuristic signal.",
            }
        )
    for function in heuristics.candidate_functions:
        records.append(
            {
                "label": str(function),
                "confidence": 0.75,
                "reason": "Conservative deterministic heuristic candidate.",
            }
        )
    return records


def _merge_emotion_expressed(
    partial_payload: dict[str, Any],
    heuristics: HeuristicExtraction,
) -> str:
    if partial_payload.get("emotion_expressed") != "N":
        return str(partial_payload["emotion_expressed"])
    if heuristics.candidate_emotion_expressed:
        return str(heuristics.candidate_emotion_expressed)
    return "N"


def _merge_emotions_mentioned(
    partial_payload: dict[str, Any],
    heuristics: HeuristicExtraction,
) -> list[str]:
    return _dedupe(
        [str(emotion) for emotion in partial_payload.get("emotions_mentioned", [])]
        + [str(emotion) for emotion in heuristics.candidate_emotions_mentioned]
    )


def _merge_stance(partial_payload: dict[str, Any], heuristics: HeuristicExtraction) -> str:
    if partial_payload.get("stance") != "neutral":
        return str(partial_payload["stance"])
    if heuristics.candidate_stance:
        return str(heuristics.candidate_stance)
    return "neutral"


def _merge_evidence_spans(
    partial_spans: list[dict[str, Any]],
    heuristic_spans: list[EvidenceSpan],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, int | None, int | None, str | None]] = set()
    for span in [*partial_spans, *[item.model_dump(mode="json") for item in heuristic_spans]]:
        key = (
            span.get("text", ""),
            span.get("char_start"),
            span.get("char_end"),
            span.get("source"),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(span)
    return merged


def _append_conflict_reviews(
    reasons: list[str],
    *,
    locked: list[str],
    llm_functions: list[str],
) -> list[str]:
    if locked and not set(locked).issubset(set(llm_functions)):
        return _append_unique(reasons, "locked_heuristic_llm_conflict")
    return reasons


def _attach_llm_usage_flags(unit: NarrativeUnit, llm_result: LLMCallResult) -> NarrativeUnit:
    if not llm_result.usage and not llm_result.cache_hit:
        return unit
    payload = unit.model_dump(mode="json")
    if llm_result.cache_hit:
        payload["validator_flags"] = _append_flag(
            payload.get("validator_flags", []),
            rule_id="llm_cache_hit",
            severity="info",
            message="Classification loaded from structured LLM cache.",
            field="llm_votes",
        )
    if llm_result.usage:
        payload["logic"] = payload.get("logic") or {}
        payload["logic"]["llm_usage"] = llm_result.usage
    return NarrativeUnit.model_validate(payload)


def _append_flag(
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


def _append_unique(values: list[str], value: str) -> list[str]:
    return values if value in values else [*values, value]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped
