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

    question_match = _question_match(text, folded)
    if question_match:
        _add_signal("P", "function:P.question_mark", question_match, text, locked, fired, evidence)

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


def _question_match(text: str, folded: str) -> re.Match[str] | None:
    if "?" not in text and "¿" not in text and "?" not in folded:
        return None
    return re.search(r"[?¿]", folded) or re.search(r".", folded)


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
    match: re.Match[str],
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
    match: re.Match[str],
    original_text: str,
    fired: list[str],
    evidence: list[EvidenceSpan],
) -> None:
    fired.append(rule_id)
    start, end = match.span()
    span_text = original_text[start:end] if end <= len(original_text) else match.group(0)
    if not span_text.strip():
        span_text = match.group(0)
    evidence.append(
        EvidenceSpan(
            text=span_text,
            char_start=start,
            char_end=end,
            source=rule_id,
        )
    )


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
