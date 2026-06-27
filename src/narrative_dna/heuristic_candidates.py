"""Conservative deterministic heuristic candidate extraction."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from narrative_dna.models import (
    Certainty,
    EmotionCode,
    EvidenceSpan,
    FunctionCode,
    HeuristicCandidate,
    NarrativeDocument,
    NarrativeUnit,
    Stance,
    StrictBaseModel,
)
from narrative_dna.normalizer import normalize_text
from narrative_dna.notation import normalize_function_codes
from narrative_dna.question_detection import find_question_anchor_span
from narrative_dna.validators import ValidationContext, normalize_and_validate_unit

PROMOTABLE_CANDIDATE_MIN_CONFIDENCE = 0.76
NON_PROMOTABLE_CANDIDATE_FUNCTIONS = {"V"}


class HeuristicExtraction(StrictBaseModel):
    locked_functions: list[FunctionCode] = []
    candidate_functions: list[FunctionCode] = []
    candidate_certainty: Certainty | None = None
    candidate_emotion_expressed: EmotionCode | None = None
    candidate_emotions_mentioned: list[EmotionCode] = []
    candidate_stance: Stance | None = None
    heuristics_fired: list[str] = []
    evidence_spans: list[EvidenceSpan] = []


@dataclass(frozen=True)
class FunctionRule:
    code: str
    rule_id: str
    patterns: tuple[str, ...]
    confidence: float
    skip_patterns: tuple[str, ...] = ()


FUNCTION_RULES: tuple[FunctionRule, ...] = (
    FunctionRule(
        "D",
        "function:D.evidence_marker",
        (
            r"\d",
            r"%",
            r"\bsegun\b",
            r"\bestudio\b",
            r"\bencuesta\b",
            r"\bdatos?\b",
            r"\breporte\b",
            r"\binforme\b",
        ),
        0.82,
    ),
    FunctionRule(
        "Y",
        "function:Y.causal_marker",
        (r"\bporque\b", r"\bdebido a\b", r"\bla razon es\b", r"\bpor eso\b"),
        0.78,
    ),
    FunctionRule(
        "E",
        "function:E.example_marker",
        (r"\bpor ejemplo\b", r"\bimagina\b", r"\bsupongamos\b"),
        0.8,
    ),
    FunctionRule(
        "H", "function:H.story_marker", (r"\buna vez\b", r"\bme paso\b", r"\brecuerdo que\b"), 0.78
    ),
    FunctionRule(
        "G",
        "function:G.analogy_marker",
        (r"\bes como\b", r"\bfunciona como\b", r"\bparecido a\b"),
        0.78,
    ),
    FunctionRule(
        "C",
        "function:C.contrast_marker",
        (r"\bpero\b", r"\bsin embargo\b", r"\baunque\b", r"\ben cambio\b"),
        0.72,
        (r"\bpero bueno\b",),
    ),
    FunctionRule(
        "B",
        "function:B.objection_marker",
        (r"\balguien podria decir\b", r"\bse podria objetar\b", r"\bpodrian objetar\b"),
        0.84,
    ),
    FunctionRule(
        "X",
        "function:X.risk_marker",
        (r"\bcuidado\b", r"\bojo\b", r"\briesgo\b", r"\bpeligro\b"),
        0.82,
    ),
    FunctionRule(
        "S",
        "function:S.solution_marker",
        (r"\bte recomiendo\b", r"\bconviene\b", r"\bdeberias\b"),
        0.78,
    ),
    FunctionRule(
        "I",
        "function:I.clear_imperative",
        (r"^(haz|prueba|usa|evita|mide|elige|cambia|anota|recuerda|compara|revisa)\b",),
        0.76,
    ),
    FunctionRule(
        "U",
        "function:U.utility_marker",
        (r"\bla leccion\b", r"\baprendizaje\b", r"\btakeaway\b"),
        0.78,
    ),
    FunctionRule(
        "V",
        "function:V.viewer_address",
        (r"\btu caso\b", r"\bpreguntate\b", r"\btu\b", r"\bte\b", r"\bustedes\b"),
        0.7,
    ),
    FunctionRule(
        "O", "function:O.opinion_marker", (r"\bcreo\b", r"\bpienso\b", r"\bme parece\b"), 0.8
    ),
    FunctionRule(
        "F",
        "function:F.definition_marker",
        (r"\bsignifica\b", r"\bse define\b", r"\bes decir\b"),
        0.8,
    ),
    FunctionRule(
        "L", "function:L.list_marker", (r"\bprimero\b", r"\bsegundo\b", r"\btercero\b"), 0.76
    ),
    FunctionRule(
        "M",
        "function:M.metacommentary_marker",
        (r"\bvoy a explicar\b", r"\bdejame explicar\b", r"\bte explico\b"),
        0.78,
    ),
    FunctionRule(
        "Q", "function:Q.explicit_quote", (r'"[^"]+"', r"\bdijo:\b", r"\bcito\b", r"\bcita\b"), 0.82
    ),
)

CONCLUSION_PATTERNS = (
    r"\ben resumen\b",
    r"\ben conclusion\b",
    r"\bpara cerrar\b",
)
CERTAINTY_PATTERNS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "strong",
        "certainty:strong.marker",
        (r"\bsin duda\b", r"\bclaramente\b", r"\bdefinitivamente\b"),
    ),
    (
        "tentative",
        "certainty:tentative.marker",
        (r"\bquizas\b", r"\btal vez\b", r"\bprobablemente\b"),
    ),
    ("uncertain", "certainty:uncertain.marker", (r"\bno se\b", r"\bes incierto\b", r"\bdudo\b")),
)
STANCE_PATTERNS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "positive",
        "stance:positive.marker",
        (r"\bes valioso\b", r"\bfunciona bien\b", r"\bes mejor\b"),
    ),
    (
        "negative",
        "stance:negative.marker",
        (r"\bfalla\b", r"\bproblema grave\b", r"\bes peligroso\b"),
    ),
)
EMOTION_WORDS = {
    "alegria": "A",
    "entusiasmo": "A",
    "amor": "L",
    "admiracion": "L",
    "calma": "C",
    "confianza": "C",
    "sorpresa": "S",
    "asombro": "S",
    "enojo": "E",
    "indignacion": "E",
    "miedo": "M",
    "ansiedad": "M",
    "tristeza": "T",
    "decepcion": "T",
    "disgusto": "D",
    "desprecio": "D",
    "frustracion": "F",
    "resignacion": "F",
    "ironia": "I",
    "sarcasmo": "I",
}
EMOTION_EXPRESSION_PATTERNS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "A",
        "emotion_expressed:A.marker",
        (r"\bme alegra\b", r"\bestoy feliz\b", r"\bme entusiasma\b"),
    ),
    ("L", "emotion_expressed:L.marker", (r"\badmiro\b", r"\bme encanta\b")),
    (
        "C",
        "emotion_expressed:C.marker",
        (r"\bconfio\b", r"\bme da calma\b", r"\bestoy tranquilo\b"),
    ),
    ("S", "emotion_expressed:S.marker", (r"\bme sorprende\b", r"\bque sorpresa\b")),
    ("E", "emotion_expressed:E.marker", (r"\bme indigna\b", r"\bme enoja\b", r"\bestoy furioso\b")),
    (
        "M",
        "emotion_expressed:M.marker",
        (r"\bme preocupa\b", r"\btengo miedo\b", r"\bme da miedo\b"),
    ),
    ("T", "emotion_expressed:T.marker", (r"\bme entristece\b", r"\bque triste\b")),
    ("D", "emotion_expressed:D.marker", (r"\bme da asco\b", r"\bdesprecio\b")),
    ("F", "emotion_expressed:F.marker", (r"\bme frustra\b", r"\bestoy resignado\b")),
    ("I", "emotion_expressed:I.marker", (r"\bclaro, como si\b", r"\bsarcasmo\b")),
)
MENTION_CONTEXT_RE = re.compile(
    r"\b(gente|personas|usuarios|ellos|alguien|menciona|habla de|siente|sienten|sentir)\b"
)


def extract_heuristic_candidates(
    unit: NarrativeUnit,
    *,
    total_units: int | None = None,
) -> HeuristicExtraction:
    """Extract conservative heuristic signals for a single narrative unit."""

    text = unit.text
    folded = _fold(text)
    locked: list[str] = []
    candidates: list[str] = []
    fired: list[str] = []
    evidence: list[EvidenceSpan] = []

    question_span = find_question_anchor_span(text)
    if question_span:
        _add_signal("P", "function:P.question_mark", question_span, text, locked, fired, evidence)

    for pattern in CONCLUSION_PATTERNS:
        match = re.search(pattern, folded)
        if match:
            target = locked if _is_near_document_end(unit, total_units) else candidates
            _add_signal("Z", "function:Z.conclusion_marker", match, text, target, fired, evidence)
            break

    for rule in FUNCTION_RULES:
        match = _match_rule(rule, folded)
        if match:
            _add_signal(rule.code, rule.rule_id, match, text, candidates, fired, evidence)

    certainty, certainty_rule, certainty_match = _first_typed_match(CERTAINTY_PATTERNS, folded)
    stance, stance_rule, stance_match = _first_typed_match(STANCE_PATTERNS, folded)
    emotion_expressed, emotion_rule, emotion_match = _candidate_emotion_expressed(folded)
    emotions_mentioned, mention_rules, mention_spans = _candidate_emotions_mentioned(folded)

    if certainty and certainty_match:
        _add_evidence(certainty_rule, certainty_match, text, fired, evidence)
    if stance and stance_match:
        _add_evidence(stance_rule, stance_match, text, fired, evidence)
    if emotion_expressed and emotion_match:
        _add_evidence(emotion_rule, emotion_match, text, fired, evidence)
    for rule_id, match in zip(mention_rules, mention_spans, strict=True):
        _add_evidence(rule_id, match, text, fired, evidence)

    locked = normalize_function_codes(locked)
    candidates = [code for code in normalize_function_codes(candidates) if code not in locked]
    return HeuristicExtraction.model_validate(
        {
            "locked_functions": locked,
            "candidate_functions": candidates,
            "candidate_certainty": certainty,
            "candidate_emotion_expressed": emotion_expressed,
            "candidate_emotions_mentioned": _dedupe(emotions_mentioned),
            "candidate_stance": stance,
            "heuristics_fired": _dedupe(fired),
            "evidence_spans": [span.model_dump(mode="json") for span in evidence],
        }
    )


def annotate_unit_with_heuristics(
    unit: NarrativeUnit,
    *,
    total_units: int | None = None,
) -> NarrativeUnit:
    """Attach heuristic candidates to a unit without changing final labels."""

    extraction = extract_heuristic_candidates(unit, total_units=total_units)
    candidates = _heuristic_candidates_from_extraction(extraction)
    payload = unit.model_dump(mode="json")
    payload["heuristic_candidates"] = candidates
    payload["evidence_spans"] = [span.model_dump(mode="json") for span in extraction.evidence_spans]
    return NarrativeUnit.model_validate(payload)


def annotate_document_with_heuristics(document: NarrativeDocument) -> NarrativeDocument:
    """Attach heuristic candidates to all units in a document."""

    units = [
        annotate_unit_with_heuristics(unit, total_units=len(document.units))
        for unit in document.units
    ]
    audit_summary = dict(document.audit_summary)
    audit_summary["heuristic_candidate_unit_count"] = sum(
        1 for unit in units if unit.heuristic_candidates
    )
    payload = document.model_dump(mode="json")
    payload["units"] = [unit.model_dump(mode="json") for unit in units]
    payload["audit_summary"] = audit_summary
    return NarrativeDocument.model_validate(payload)


def apply_heuristic_baseline_to_unit(
    unit: NarrativeUnit,
    *,
    total_units: int | None = None,
    previous_text: str | None = None,
    next_text: str | None = None,
    failure_reason: str | None = None,
) -> NarrativeUnit:
    """Promote high-confidence heuristic signals into a conservative final baseline."""

    extraction = extract_heuristic_candidates(unit, total_units=total_units)
    candidate_records = _heuristic_candidates_from_extraction(extraction)
    promoted_functions, candidate_derived = _promoted_function_labels(candidate_records)
    payload = unit.model_dump(mode="json")
    payload["heuristic_candidates"] = candidate_records
    payload["evidence_spans"] = [span.model_dump(mode="json") for span in extraction.evidence_spans]

    changed = False
    review_reasons = list(payload.get("review_reasons", []))
    if promoted_functions:
        payload["functions"] = promoted_functions
        payload["primary_function"] = promoted_functions[0]
        payload["secondary_functions"] = promoted_functions[1:]
        changed = True
    if extraction.candidate_certainty:
        payload["certainty"] = str(extraction.candidate_certainty)
        changed = True
        review_reasons = _append_unique(review_reasons, "heuristic_certainty_candidate")
    if extraction.candidate_emotion_expressed:
        payload["emotion_expressed"] = str(extraction.candidate_emotion_expressed)
        payload["emotion_intensity"] = max(int(payload.get("emotion_intensity") or 0), 1)
        changed = True
        review_reasons = _append_unique(review_reasons, "heuristic_emotion_candidate")
    if extraction.candidate_emotions_mentioned:
        payload["emotions_mentioned"] = _dedupe(
            [
                *[str(emotion) for emotion in payload.get("emotions_mentioned", [])],
                *[str(emotion) for emotion in extraction.candidate_emotions_mentioned],
            ]
        )
        changed = True
        review_reasons = _append_unique(review_reasons, "heuristic_emotion_mention_candidate")
    if extraction.candidate_stance:
        payload["stance"] = str(extraction.candidate_stance)
        changed = True
        review_reasons = _append_unique(review_reasons, "heuristic_stance_candidate")

    if changed:
        payload["method"] = "heuristic"
        payload["confidence"] = _heuristic_baseline_confidence(
            candidate_records,
            promoted_functions,
            has_non_function_signal=bool(
                extraction.candidate_certainty
                or extraction.candidate_emotion_expressed
                or extraction.candidate_emotions_mentioned
                or extraction.candidate_stance
            ),
        )
    if candidate_derived:
        payload["needs_review"] = True
        review_reasons = _append_unique(review_reasons, "heuristic_candidate_promoted")
    if len(promoted_functions) > 1:
        payload["needs_review"] = True
        review_reasons = _append_unique(review_reasons, "heuristic_multilabel")
    if failure_reason:
        payload["needs_review"] = True
        review_reasons = _append_unique(review_reasons, failure_reason)
    if payload.get("needs_review"):
        payload["review_status"] = "needs_review"
    elif changed:
        payload["review_status"] = "accepted"
    payload["review_reasons"] = review_reasons

    return normalize_and_validate_unit(
        payload,
        context=ValidationContext(previous_text=previous_text, next_text=next_text),
    )


def apply_heuristic_baseline_to_document(document: NarrativeDocument) -> NarrativeDocument:
    """Apply the no-LLM conservative baseline to all units in a document."""

    units = []
    for index, unit in enumerate(document.units):
        units.append(
            apply_heuristic_baseline_to_unit(
                unit,
                total_units=len(document.units),
                previous_text=document.units[index - 1].text if index > 0 else None,
                next_text=(
                    document.units[index + 1].text if index + 1 < len(document.units) else None
                ),
            )
        )
    audit_summary = dict(document.audit_summary)
    audit_summary["heuristic_baseline_unit_count"] = sum(
        1 for unit in units if unit.method == "heuristic"
    )
    payload = document.model_dump(mode="json")
    payload["units"] = [unit.model_dump(mode="json") for unit in units]
    payload["audit_summary"] = audit_summary
    return NarrativeDocument.model_validate(payload)


def _heuristic_candidates_from_extraction(extraction: HeuristicExtraction) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for code in extraction.locked_functions:
        records.append(
            HeuristicCandidate(
                label=code,
                confidence=0.95,
                reason="Locked deterministic heuristic signal.",
            ).model_dump(mode="json")
        )
    for code in extraction.candidate_functions:
        confidence = next((rule.confidence for rule in FUNCTION_RULES if rule.code == code), 0.78)
        records.append(
            HeuristicCandidate(
                label=code,
                confidence=confidence,
                reason="Conservative deterministic heuristic candidate.",
            ).model_dump(mode="json")
        )
    return records


def _match_rule(rule: FunctionRule, folded: str) -> re.Match[str] | None:
    if any(re.search(pattern, folded) for pattern in rule.skip_patterns):
        return None
    for pattern in rule.patterns:
        match = re.search(pattern, folded)
        if match:
            return match
    return None


def _is_near_document_end(unit: NarrativeUnit, total_units: int | None) -> bool:
    if total_units is None or total_units <= 0:
        return False
    return unit.sequence_index >= max(0, total_units - 3)


def _first_typed_match(
    typed_patterns: Iterable[tuple[str, str, tuple[str, ...]]],
    folded: str,
) -> tuple[str | None, str, re.Match[str] | None]:
    for value, rule_id, patterns in typed_patterns:
        for pattern in patterns:
            match = re.search(pattern, folded)
            if match:
                return value, rule_id, match
    return None, "", None


def _candidate_emotion_expressed(
    folded: str,
) -> tuple[str | None, str, re.Match[str] | None]:
    return _first_typed_match(EMOTION_EXPRESSION_PATTERNS, folded)


def _candidate_emotions_mentioned(folded: str) -> tuple[list[str], list[str], list[re.Match[str]]]:
    emotions: list[str] = []
    rules: list[str] = []
    spans: list[re.Match[str]] = []
    for word, code in EMOTION_WORDS.items():
        for match in re.finditer(rf"\b{re.escape(word)}\b", folded):
            context_start = max(0, match.start() - 45)
            context_end = min(len(folded), match.end() + 20)
            context = folded[context_start:context_end]
            if MENTION_CONTEXT_RE.search(context):
                emotions.append(code)
                rules.append(f"emotion_mentioned:{code}.lexical_context")
                spans.append(match)
                break
    return emotions, rules, spans


def _add_signal(
    code: str,
    rule_id: str,
    match: re.Match[str] | tuple[int, int],
    original_text: str,
    target: list[str],
    fired: list[str],
    evidence: list[EvidenceSpan],
) -> None:
    if code not in target:
        target.append(code)
    _add_evidence(rule_id, match, original_text, fired, evidence)


def _add_evidence(
    rule_id: str,
    match: re.Match[str] | tuple[int, int],
    original_text: str,
    fired: list[str],
    evidence: list[EvidenceSpan],
) -> None:
    fired.append(rule_id)
    start, end = _span_bounds(match)
    span_text = original_text[start:end] if end <= len(original_text) else _span_text(match)
    if not span_text.strip():
        span_text = _span_text(match)
    evidence.append(
        EvidenceSpan(
            text=span_text,
            char_start=start,
            char_end=end,
            source=rule_id,
        )
    )


def _span_bounds(match: re.Match[str] | tuple[int, int]) -> tuple[int, int]:
    return match if isinstance(match, tuple) else match.span()


def _span_text(match: re.Match[str] | tuple[int, int]) -> str:
    return "" if isinstance(match, tuple) else match.group(0)


def _promoted_function_labels(
    candidate_records: list[dict[str, Any]],
) -> tuple[list[str], bool]:
    labels: list[str] = []
    candidate_derived = False
    for candidate in candidate_records:
        label = str(candidate["label"])
        confidence = float(candidate["confidence"])
        locked = confidence >= 0.95 or "Locked deterministic" in str(candidate.get("reason", ""))
        promotable_candidate = (
            confidence >= PROMOTABLE_CANDIDATE_MIN_CONFIDENCE
            and label not in NON_PROMOTABLE_CANDIDATE_FUNCTIONS
        )
        if not (locked or promotable_candidate):
            continue
        labels.append(label)
        candidate_derived = candidate_derived or not locked
    return normalize_function_codes(labels), candidate_derived


def _heuristic_baseline_confidence(
    candidate_records: list[dict[str, Any]],
    promoted_functions: list[str],
    *,
    has_non_function_signal: bool,
) -> float:
    if not promoted_functions:
        return 0.7 if has_non_function_signal else 0.0
    by_label = {
        str(candidate["label"]): float(candidate["confidence"]) for candidate in candidate_records
    }
    promoted_confidences = [by_label[label] for label in promoted_functions if label in by_label]
    if not promoted_confidences:
        return 0.7
    return round(min(promoted_confidences), 4)


def _fold(text: str) -> str:
    normalized = normalize_text(text).lower()
    decomposed = unicodedata.normalize("NFKD", normalized)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _append_unique(values: list[str], value: str) -> list[str]:
    return values if value in values else [*values, value]
