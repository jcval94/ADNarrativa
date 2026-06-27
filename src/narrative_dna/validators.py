"""Deterministic validators for stable JSON-first annotations."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from narrative_dna.models import NarrativeUnit
from narrative_dna.notation import derive_final_notation, normalize_function_codes
from narrative_dna.question_detection import has_question_anchor as text_has_question_anchor


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
CERTAINTY_SIGNAL_PATTERNS: dict[str, tuple[str, ...]] = {
    "strong": (
        r"\bsin duda\b",
        r"\bclaramente\b",
        r"\bdefinitivamente\b",
        r"\bes claro\b",
        r"\bno hay duda\b",
        r"\bclearly\b",
        r"\bdefinitely\b",
        r"\bcertainly\b",
        r"\bno doubt\b",
        r"\bwill\b",
        r"\bmust\b",
    ),
    "tentative": (
        r"\bquizas\b",
        r"\btal vez\b",
        r"\bprobablemente\b",
        r"\bpodria\b",
        r"\bpuede que\b",
        r"\bmaybe\b",
        r"\bperhaps\b",
        r"\bprobably\b",
        r"\bmight\b",
        r"\bcould\b",
    ),
    "uncertain": (
        r"\bno se\b",
        r"\bno sabemos\b",
        r"\bes incierto\b",
        r"\bdudo\b",
        r"\bduda\b",
        r"\buncertain\b",
        r"\bunclear\b",
        r"\bnot sure\b",
        r"\bdon't know\b",
    ),
}
FUNCTION_SIGNAL_PATTERNS: dict[str, tuple[str, ...]] = {
    "C": (
        r"\bpero\b",
        r"\bsin embargo\b",
        r"\baunque\b",
        r"\ben cambio\b",
        r"\bcontrasta?\b",
        r"\bhowever\b",
        r"\bbut\b",
        r"\bwhereas\b",
    ),
    "B": (
        r"\bno es cierto\b",
        r"\bes falso\b",
        r"\brefuta\b",
        r"\bobjeta\b",
        r"\bse podria objetar\b",
        r"\balguien podria decir\b",
        r"\bnot true\b",
        r"\bwrong\b",
        r"\brefutes?\b",
        r"\bobjection\b",
    ),
    "X": (
        r"\briesgo\b",
        r"\bpeligro\b",
        r"\bcuidado\b",
        r"\bojo\b",
        r"\bfalla\b",
        r"\bfallo\b",
        r"\brisk\b",
        r"\bdanger\b",
        r"\bfailure\b",
        r"\bif not\b",
    ),
    "E": (
        r"\bpor ejemplo\b",
        r"\bimagina\b",
        r"\bsupongamos\b",
        r"\bcaso\b",
        r"\bexample\b",
        r"\bsuppose\b",
    ),
    "H": (
        r"\buna vez\b",
        r"\bme paso\b",
        r"\brecuerdo\b",
        r"\bhistoria\b",
        r"\bstory\b",
        r"\bhappened\b",
        r"\bwhen i\b",
    ),
    "G": (
        r"\bes como\b",
        r"\bcomo una\b",
        r"\bcomo un\b",
        r"\bfunciona como\b",
        r"\banalog",
        r"\bparecido a\b",
        r"\bworks like\b",
        r"\bis like\b",
    ),
    "T": (
        r"\bahora\b",
        r"\bpasemos\b",
        r"\bpor otro lado\b",
        r"\bcambiemos\b",
        r"\bvolvamos\b",
        r"\bnext\b",
        r"\bnow\b",
        r"\bmoving on\b",
    ),
    "M": (
        r"\bvoy a explicar\b",
        r"\bdejame explicar\b",
        r"\bte explico\b",
        r"\ben este video\b",
        r"\bhablemos\b",
        r"\blet me explain\b",
        r"\bi will explain\b",
    ),
    "L": (
        r"\bprimero\b",
        r"\bsegundo\b",
        r"\btercero\b",
        r"\blista\b",
        r"\benumer",
        r"\bfirst\b",
        r"\bsecond\b",
        r"\bthird\b",
    ),
    "Z": (
        r"\ben resumen\b",
        r"\ben conclusion\b",
        r"\bpara cerrar\b",
        r"\bfinalmente\b",
        r"\bin summary\b",
        r"\bto conclude\b",
        r"\bfinally\b",
    ),
}
ILLUSTRATIVE_FUNCTIONS = {"E", "H", "G"}
STRUCTURAL_FUNCTIONS = {"T", "M", "L", "Z"}
CONTRAST_FUNCTIONS = {"C", "B", "X"}


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
    return text_has_question_anchor(
        text,
        previous_text=previous,
        relation_types=context.candidate_relation_types,
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


def _text_blob(payload: dict[str, Any]) -> str:
    return f"{payload.get('text', '')} {payload.get('normalized_text', '')}"


def _fold_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _logic_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Mapping):
        return " ".join(f"{key} {_logic_text(item)}" for key, item in value.items())
    if isinstance(value, Sequence) and not isinstance(value, str):
        return " ".join(_logic_text(item) for item in value)
    return str(value)


def _evidence_text(payload: dict[str, Any]) -> str:
    spans = payload.get("evidence_spans") or []
    parts: list[str] = []
    for span in spans:
        if isinstance(span, Mapping):
            parts.append(str(span.get("text") or ""))
            parts.append(str(span.get("source") or ""))
    return " ".join(parts)


def _folded_search_space(payload: dict[str, Any]) -> str:
    return _fold_text(
        " ".join(
            [
                _text_blob(payload),
                _logic_text(payload.get("logic")),
                _evidence_text(payload),
            ]
        )
    )


def _matches_any_pattern(text: str, patterns: Sequence[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _logic_declares(payload: dict[str, Any], field_name: str, expected_value: str | None) -> bool:
    logic = payload.get("logic")
    if not isinstance(logic, Mapping):
        return False
    folded = _fold_text(_logic_text(logic))
    field = _fold_text(field_name)
    if field not in folded:
        return False
    return expected_value is None or _fold_text(expected_value) in folded


def _has_certainty_signal(payload: dict[str, Any]) -> bool:
    certainty = str(_value(payload.get("certainty", "none")))
    if certainty == "none":
        return True
    search_space = _folded_search_space(payload)
    return _matches_any_pattern(
        search_space, CERTAINTY_SIGNAL_PATTERNS.get(certainty, ())
    ) or _logic_declares(payload, "certainty", certainty)


def _has_recoverable_target(payload: dict[str, Any]) -> bool:
    target = payload.get("target")
    if isinstance(target, str) and target.strip():
        return True
    return any(
        _logic_declares(payload, field_name, None)
        for field_name in ("target", "proposition", "claim", "risk_target", "affected")
    )


def _has_function_signal(payload: dict[str, Any], function: str) -> bool:
    search_space = _folded_search_space(payload)
    if f"function:{function.lower()}" in search_space:
        return True
    return _matches_any_pattern(search_space, FUNCTION_SIGNAL_PATTERNS.get(function, ()))


def _active_group(functions: Sequence[str], group: set[str]) -> list[str]:
    return [function for function in functions if function in group]


def _flag_missing_function_signals(
    payload: dict[str, Any],
    active_functions: Sequence[str],
    *,
    rule_id: str,
    message: str,
) -> None:
    missing = [
        function for function in active_functions if not _has_function_signal(payload, function)
    ]
    if not missing:
        return
    _append_flag(
        payload,
        rule_id,
        f"{message} Missing deterministic signal for: {', '.join(missing)}.",
        "functions",
    )
    _mark_review(payload, rule_id)


def _flag_group_primary_priority(
    payload: dict[str, Any],
    active_functions: Sequence[str],
    *,
    rule_id: str,
    message: str,
) -> None:
    if len(active_functions) < 2:
        return
    primary = str(_value(payload.get("primary_function")))
    signaled = [
        function for function in active_functions if _has_function_signal(payload, function)
    ]
    dominant = signaled[0] if len(signaled) == 1 else None
    if primary in active_functions and (dominant is None or primary == dominant):
        return
    _append_flag(payload, rule_id, message, "primary_function")
    _mark_review(payload, rule_id)


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

    if not _has_certainty_signal(payload):
        _append_flag(
            payload,
            "certainty_epistemic_not_intensity",
            "Non-neutral certainty requires explicit epistemic evidence.",
            "certainty",
        )
        _mark_review(payload, "certainty_epistemic_not_intensity")

    if str(_value(payload.get("stance", "neutral"))) != "neutral" and not _has_recoverable_target(
        payload
    ):
        _append_flag(
            payload,
            "stance_requires_target_when_non_neutral",
            "Non-neutral stance requires a recoverable target.",
            "target",
        )
        _mark_review(payload, "stance_requires_target_when_non_neutral")

    contrast_functions = _active_group(payload["functions"], CONTRAST_FUNCTIONS)
    if contrast_functions:
        _flag_missing_function_signals(
            payload,
            contrast_functions,
            rule_id="contrast_boundary_required",
            message="C/B/X require contrast, refutation, or risk evidence.",
        )
        if not _has_recoverable_target(payload):
            _append_flag(
                payload,
                "contrast_refutation_risk_target",
                "C/B/X require a target or affected proposition.",
                "target",
            )
            _mark_review(payload, "contrast_refutation_risk_target")

    illustrative_functions = _active_group(payload["functions"], ILLUSTRATIVE_FUNCTIONS)
    if illustrative_functions:
        _flag_missing_function_signals(
            payload,
            illustrative_functions,
            rule_id="illustrative_boundary_required",
            message="E/H/G require example, story, or analogy evidence.",
        )
        _flag_group_primary_priority(
            payload,
            illustrative_functions,
            rule_id="dominant_illustrative_unit",
            message="E/H/G multilabel units require coherent illustrative primary priority.",
        )

    structural_functions = _active_group(payload["functions"], STRUCTURAL_FUNCTIONS)
    if structural_functions:
        _flag_missing_function_signals(
            payload,
            structural_functions,
            rule_id="structural_boundary_required",
            message="T/M/L/Z require transition, metacommentary, list, or conclusion evidence.",
        )
        _flag_group_primary_priority(
            payload,
            structural_functions,
            rule_id="structural_primary_priority",
            message="T/M/L/Z multilabel units require coherent structural primary priority.",
        )

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
