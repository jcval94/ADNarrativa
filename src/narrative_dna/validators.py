"""Deterministic validators for stable JSON-first annotations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from narrative_dna.models import NarrativeUnit
from narrative_dna.notation import derive_final_notation, normalize_function_codes


@dataclass(frozen=True)
class ValidationContext:
    """Optional local context used by deterministic validators."""

    previous_text: str | None = None
    next_text: str | None = None
    candidate_relation_types: list[str] = field(default_factory=list)


EVIDENCE_MARKERS = (
    "%",
    "según",
    "reporte",
    "informe",
    "dato",
    "medimos",
    "muestra",
    "registr",
    "encuesta",
    "tabla",
    "log",
)
EMOTION_WORDS = {
    "alegría": "A",
    "entusiasmo": "A",
    "amor": "L",
    "admiración": "L",
    "calma": "C",
    "confianza": "C",
    "sorpresa": "S",
    "asombro": "S",
    "enojo": "E",
    "indignación": "E",
    "miedo": "M",
    "ansiedad": "M",
    "tristeza": "T",
    "decepción": "T",
    "disgusto": "D",
    "desprecio": "D",
    "frustración": "F",
    "resignación": "F",
    "ironía": "I",
    "sarcasmo": "I",
}


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _as_payload(unit: NarrativeUnit | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(unit, NarrativeUnit):
        return unit.model_dump(mode="json")
    return deepcopy(dict(unit))


def _codes(values: Sequence[Any]) -> list[str]:
    return [str(_value(value)) for value in values]


def _append_flag(payload: dict[str, Any], rule_id: str, message: str, field_name: str) -> None:
    flags = payload.setdefault("validator_flags", [])
    if any(flag.get("rule_id") == rule_id for flag in flags):
        return
    flags.append(
        {
            "rule_id": rule_id,
            "severity": "warning",
            "message": message,
            "field": field_name,
        }
    )


def _mark_review(payload: dict[str, Any], reason: str) -> None:
    payload["needs_review"] = True
    reasons = payload.setdefault("review_reasons", [])
    if reason not in reasons:
        reasons.append(reason)
    if payload.get("review_status") == "accepted":
        payload["review_status"] = "needs_review"


def _add_inherited_a(payload: dict[str, Any]) -> None:
    inherited = payload.setdefault("inherited_functions", [])
    if not any(
        item.get("function") == "A" and item.get("inherited_from") == "K" for item in inherited
    ):
        inherited.append(
            {
                "function": "A",
                "inherited_from": "K",
                "reason": "K_subclass_of_A",
            }
        )


def _has_evidence_signal(payload: dict[str, Any]) -> bool:
    if payload.get("evidence_spans"):
        return True
    text = f"{payload.get('text', '')} {payload.get('normalized_text', '')}".lower()
    return any(marker in text for marker in EVIDENCE_MARKERS) or any(
        char.isdigit() for char in text
    )


def _has_question_anchor(payload: dict[str, Any], context: ValidationContext) -> bool:
    text = f"{payload.get('text', '')} {payload.get('normalized_text', '')}".lower()
    previous = (context.previous_text or "").lower()
    relation_types = {relation.upper() for relation in context.candidate_relation_types}
    return (
        "?" in text or "¿" in text or "?" in previous or "¿" in previous or "ANS" in relation_types
    )


def _mentions_emotion_without_expression(payload: dict[str, Any]) -> bool:
    emotion = str(_value(payload.get("emotion_expressed", "N")))
    intensity = int(payload.get("emotion_intensity") or 0)
    if emotion == "N" or intensity < 2:
        return False
    text = f"{payload.get('text', '')} {payload.get('normalized_text', '')}".lower()
    mentioned_codes = _codes(payload.get("emotions_mentioned", []))
    matched_codes = {code for word, code in EMOTION_WORDS.items() if word in text}
    return emotion in mentioned_codes or emotion in matched_codes


def normalize_and_validate_unit(
    unit: NarrativeUnit | Mapping[str, Any],
    *,
    context: ValidationContext | None = None,
    always_parentheses: bool = False,
) -> NarrativeUnit:
    """Apply deterministic validators and return a strict NarrativeUnit."""

    context = context or ValidationContext()
    payload = _as_payload(unit)
    functions = normalize_function_codes(_codes(payload.get("functions", [])))

    if "N" in functions and len(functions) > 1:
        functions = [function for function in functions if function != "N"]
        _append_flag(
            payload, "N_exclusive", "Removed N because other functions were present.", "functions"
        )

    if "K" in functions:
        if "A" in functions:
            functions = [function for function in functions if function != "A"]
            _append_flag(
                payload,
                "K_inherits_A",
                "Moved A from functions to inherited_functions because K inherits A.",
                "functions",
            )
        _add_inherited_a(payload)

    payload["functions"] = normalize_function_codes(functions)
    if payload.get("primary_function") not in payload["functions"]:
        if payload["functions"] == ["N"]:
            payload["primary_function"] = "N"
        elif payload["functions"]:
            payload["primary_function"] = payload["functions"][0]
            _append_flag(
                payload,
                "primary_function_required",
                "Set primary_function to the first taxonomy-ordered function.",
                "primary_function",
            )
            _mark_review(payload, "primary_function_required")

    payload["secondary_functions"] = [
        function
        for function in normalize_function_codes(_codes(payload.get("secondary_functions", [])))
        if function in payload["functions"] and function != payload.get("primary_function")
    ]

    if "D" in payload["functions"] and not _has_evidence_signal(payload):
        _append_flag(
            payload,
            "D_without_evidence",
            "D requires evidence_spans or strong textual evidence markers.",
            "evidence_spans",
        )
        _mark_review(payload, "D_without_evidence")

    if "R" in payload["functions"] and not _has_question_anchor(payload, context):
        _append_flag(
            payload,
            "R_without_question_anchor",
            "R requires a nearby question anchor or ANS candidate relation.",
            "functions",
        )
        _mark_review(payload, "R_without_question_anchor")

    if _mentions_emotion_without_expression(payload):
        _append_flag(
            payload,
            "possible_emotion_confusion",
            "Emotion may be mentioned rather than expressed.",
            "emotion_expressed",
        )
        _mark_review(payload, "possible_emotion_confusion")

    if len(payload["functions"]) > 5:
        _append_flag(
            payload,
            "possible_overlabeling",
            "More than five functions are active.",
            "functions",
        )
        _mark_review(payload, "possible_overlabeling")

    previous_notation = payload.get("final_notation")
    derived_notation = derive_final_notation(payload, always_parentheses=always_parentheses)
    if previous_notation and previous_notation != derived_notation:
        _append_flag(
            payload,
            "notation_derivation",
            "Recompiled final_notation from validated JSON fields.",
            "final_notation",
        )
    payload["final_notation"] = derived_notation
    return NarrativeUnit.model_validate(payload)


def validate_units(
    units: Sequence[NarrativeUnit | Mapping[str, Any]],
    *,
    always_parentheses: bool = False,
) -> list[NarrativeUnit]:
    """Validate a sequence of units using neighboring text as local context."""

    validated: list[NarrativeUnit] = []
    payloads = [_as_payload(unit) for unit in units]
    for index, payload in enumerate(payloads):
        context = ValidationContext(
            previous_text=payloads[index - 1].get("text") if index > 0 else None,
            next_text=payloads[index + 1].get("text") if index + 1 < len(payloads) else None,
        )
        validated.append(
            normalize_and_validate_unit(
                payload,
                context=context,
                always_parentheses=always_parentheses,
            )
        )
    return validated
