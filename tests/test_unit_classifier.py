from __future__ import annotations

from pathlib import Path
from typing import Any

from narrative_dna.heuristic_candidates import extract_heuristic_candidates
from narrative_dna.llm_client import LLMCallResult
from narrative_dna.loader import load_document
from narrative_dna.unit_classifier import (
    NarrativeUnitPartialClassification,
    UnitClassifier,
    build_classification_context,
)


class FakeLLMClient:
    def __init__(self, parsed_outputs: list[dict[str, Any]]) -> None:
        self.parsed_outputs = list(parsed_outputs)
        self.calls: list[dict[str, Any]] = []

    def request_structured(self, **kwargs: Any) -> LLMCallResult:
        self.calls.append(kwargs)
        parsed = self.parsed_outputs.pop(0)
        return LLMCallResult(
            ok=True,
            profile_name=kwargs["profile_name"],
            model="gpt-5.5",
            cache_key=f"fake_{len(self.calls)}",
            attempts=1,
            parsed=parsed,
            usage={"input_tokens": 10, "output_tokens": 5},
        )


class FailingLLMClient:
    def request_structured(self, **kwargs: Any) -> LLMCallResult:
        return LLMCallResult(
            ok=False,
            profile_name=kwargs["profile_name"],
            model="gpt-5.5",
            cache_key="failed",
            attempts=1,
            error_type="mock_failure",
            error="mock failure",
            fallback_allowed=True,
        )


def partial_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "functions": ["A"],
        "primary_function": "A",
        "secondary_functions": [],
        "certainty": "none",
        "emotion_expressed": "N",
        "emotion_intensity": 0,
        "emotions_mentioned": [],
        "stance": "neutral",
        "target": None,
        "speech_act": None,
        "logic": None,
        "evidence_spans": [],
        "rejected_labels": [
            {"label": "K", "reason": "No disputable thesis in this unit.", "confidence": 0.7}
        ],
        "confidence": 0.84,
        "needs_review": False,
        "review_reasons": [],
    }
    payload.update(overrides)
    return payload


def document_from_text(tmp_path: Path, text: str):
    path = tmp_path / "speech.txt"
    path.write_text(text, encoding="utf-8")
    return load_document(path)


def classifier_with(fake_client: Any) -> UnitClassifier:
    return UnitClassifier(llm_client=fake_client)


def test_partial_classification_schema_is_strict() -> None:
    parsed = NarrativeUnitPartialClassification.model_validate(partial_payload(functions=["P"]))

    assert parsed.functions == ["P"]


def test_classifies_question_as_p_plus_viewer_call_without_editing_notation_manually(
    tmp_path: Path,
) -> None:
    document = document_from_text(tmp_path, "Preguntate por que importa?")
    fake = FakeLLMClient(
        [
            partial_payload(
                functions=["V"],
                primary_function="V",
                secondary_functions=[],
                speech_act="question",
                confidence=0.81,
            )
        ]
    )

    classified = classifier_with(fake).classify_document(document)
    unit = classified.units[0]

    assert unit.functions == ["P", "V"]
    assert unit.primary_function == "P"
    assert unit.final_notation == "(P+V)_N0{0}"
    assert unit.method == "llm"
    assert fake.calls[0]["response_model"] is NarrativeUnitPartialClassification


def test_k_inherits_a_after_validator_postprocess(tmp_path: Path) -> None:
    document = document_from_text(tmp_path, "Esto demuestra que el flujo no escala.")
    fake = FakeLLMClient(
        [
            partial_payload(
                functions=["A", "K"],
                primary_function="K",
                rejected_labels=[
                    {"label": "O", "reason": "It is not framed as subjective opinion."}
                ],
            )
        ]
    )

    unit = classifier_with(fake).classify_document(document).units[0]

    assert unit.functions == ["K"]
    assert unit.primary_function == "K"
    assert unit.inherited_functions[0].function == "A"
    assert unit.final_notation == "K_N0{0}"


def test_emotion_mentioned_not_promoted_to_expressed(tmp_path: Path) -> None:
    document = document_from_text(tmp_path, "La gente siente miedo cuando faltan datos.")
    fake = FakeLLMClient(
        [
            partial_payload(
                functions=["A"],
                primary_function="A",
                emotion_expressed="N",
                emotions_mentioned=["M"],
                evidence_spans=[{"text": "datos"}],
            )
        ]
    )

    unit = classifier_with(fake).classify_document(document).units[0]

    assert unit.emotion_expressed == "N"
    assert unit.emotions_mentioned == ["M"]
    assert unit.final_notation == "A_N0{0}"


def test_r_without_question_anchor_marks_review(tmp_path: Path) -> None:
    document = document_from_text(tmp_path, "La respuesta es que falta evidencia.")
    fake = FakeLLMClient([partial_payload(functions=["R"], primary_function="R")])

    unit = classifier_with(fake).classify_document(document).units[0]
    rule_ids = {flag.rule_id for flag in unit.validator_flags}

    assert unit.needs_review is True
    assert "R_without_question_anchor" in rule_ids


def test_d_without_evidence_marks_review(tmp_path: Path) -> None:
    document = document_from_text(tmp_path, "Esto confirma la idea central.")
    fake = FakeLLMClient([partial_payload(functions=["D"], primary_function="D")])

    unit = classifier_with(fake).classify_document(document).units[0]
    rule_ids = {flag.rule_id for flag in unit.validator_flags}

    assert unit.needs_review is True
    assert "D_without_evidence" in rule_ids


def test_failed_llm_falls_back_to_locked_heuristics_with_review(tmp_path: Path) -> None:
    document = document_from_text(tmp_path, "Por que importa?")

    unit = classifier_with(FailingLLMClient()).classify_document(document).units[0]

    assert unit.functions == ["P"]
    assert unit.method == "heuristic"
    assert unit.needs_review is True
    assert "llm_classification_failed" in unit.review_reasons


def test_classification_context_includes_two_neighbors_and_heuristics(tmp_path: Path) -> None:
    document = document_from_text(
        tmp_path,
        "Primera idea. Segunda idea. Por que importa? Cuarta idea. Quinta idea.",
    )
    heuristics = extract_heuristic_candidates(document.units[2], total_units=len(document.units))

    context = build_classification_context(
        document=document,
        unit_index=2,
        heuristics=heuristics,
        taxonomy_excerpt={},
        decision_trees_excerpt="DT",
        minimal_pairs_excerpt=[],
        taxonomy_version="v1_0",
    )

    assert len(context.previous_units) == 2
    assert len(context.next_units) == 2
    assert context.heuristic_candidates["locked_functions"] == ["P"]
