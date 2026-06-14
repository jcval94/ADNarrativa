from __future__ import annotations

from pathlib import Path
from typing import Any

from narrative_dna.adjudicator import (
    AdjudicatedClassification,
    ConservativeAdjudicator,
    adjudication_risk_reasons,
    should_adjudicate,
)
from narrative_dna.llm_client import LLMCallResult
from narrative_dna.loader import load_document
from narrative_dna.models import NarrativeDocument, NarrativeUnit
from narrative_dna.notation import derive_final_notation


class FakeAdjudicatorClient:
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
            cache_key=f"adjudicator_{len(self.calls)}",
            attempts=1,
            parsed=parsed,
            usage={"input_tokens": 12, "output_tokens": 6},
        )


def adjudicated_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "final_functions": ["A"],
        "final_primary_function": "A",
        "final_secondary_functions": [],
        "final_certainty": "none",
        "final_emotion_expressed": "N",
        "final_emotion_intensity": 0,
        "final_emotions_mentioned": [],
        "final_stance": "neutral",
        "final_target": None,
        "final_speech_act": None,
        "final_logic": None,
        "final_evidence_spans": [{"text": "unidad", "source": "adjudicator"}],
        "final_rejected_labels": [
            {"label": "K", "reason": "No thesis after adjudication.", "confidence": 0.7}
        ],
        "final_confidence": 0.82,
        "final_needs_review": False,
        "adjudication_reason_summary": "Reduced to the best supported label.",
        "changed_fields": ["functions"],
    }
    payload.update(overrides)
    return payload


def document_with_unit(tmp_path: Path, text: str, **unit_overrides: Any) -> NarrativeDocument:
    path = tmp_path / "speech.txt"
    path.write_text(text, encoding="utf-8")
    document = load_document(path)
    payload = document.units[0].model_dump(mode="json")
    payload.update(unit_overrides)
    payload.setdefault("confidence", 0.8)
    payload["final_notation"] = derive_final_notation(payload)
    unit = NarrativeUnit.model_validate(payload)
    doc_payload = document.model_dump(mode="json")
    doc_payload["units"] = [unit.model_dump(mode="json")]
    return NarrativeDocument.model_validate(doc_payload)


def rule_ids(unit: NarrativeUnit) -> set[str]:
    return {flag.rule_id for flag in unit.validator_flags}


def test_overlabeling_reduced_to_clear_primary(tmp_path: Path) -> None:
    document = document_with_unit(
        tmp_path,
        "Esto demuestra que el problema ocurre porque faltan datos.",
        functions=["K", "Y", "D", "Q", "E", "V"],
        primary_function="K",
        secondary_functions=["Y", "D", "Q", "E", "V"],
        confidence=0.66,
        needs_review=True,
        review_status="needs_review",
        validator_flags=[
            {
                "rule_id": "possible_overlabeling",
                "severity": "warning",
                "message": "Too many functions.",
                "field": "functions",
            }
        ],
    )
    fake = FakeAdjudicatorClient(
        [
            adjudicated_payload(
                final_functions=["K", "Y"],
                final_primary_function="K",
                final_secondary_functions=["Y"],
                final_rejected_labels=[
                    {"label": "D", "reason": "No concrete data span is retained."}
                ],
            )
        ]
    )

    unit = ConservativeAdjudicator(llm_client=fake).adjudicate_document(document).units[0]

    assert unit.functions == ["K", "Y"]
    assert unit.primary_function == "K"
    assert unit.method == "adjudicated"
    assert "possible_overlabeling" not in rule_ids(unit)
    assert fake.calls[0]["response_model"] is AdjudicatedClassification


def test_d_removed_when_evidence_missing(tmp_path: Path) -> None:
    document = document_with_unit(
        tmp_path,
        "Esto confirma la idea central.",
        functions=["D"],
        primary_function="D",
        confidence=0.74,
        needs_review=True,
        review_status="needs_review",
        validator_flags=[
            {
                "rule_id": "D_without_evidence",
                "severity": "warning",
                "message": "D requires evidence.",
                "field": "evidence_spans",
            }
        ],
    )
    fake = FakeAdjudicatorClient(
        [adjudicated_payload(final_functions=["A"], final_primary_function="A")]
    )

    unit = ConservativeAdjudicator(llm_client=fake).adjudicate_document(document).units[0]

    assert unit.functions == ["A"]
    assert "D_without_evidence" not in rule_ids(unit)
    assert unit.final_notation == "A_N0{0}"


def test_r_without_question_changed_to_y(tmp_path: Path) -> None:
    document = document_with_unit(
        tmp_path,
        "La respuesta es que falta evidencia.",
        functions=["R"],
        primary_function="R",
        confidence=0.72,
        needs_review=True,
        review_status="needs_review",
        validator_flags=[
            {
                "rule_id": "R_without_question_anchor",
                "severity": "warning",
                "message": "R requires question anchor.",
                "field": "functions",
            }
        ],
    )
    fake = FakeAdjudicatorClient(
        [
            adjudicated_payload(
                final_functions=["Y"],
                final_primary_function="Y",
                final_evidence_spans=[{"text": "porque falta evidencia"}],
            )
        ]
    )

    unit = ConservativeAdjudicator(llm_client=fake).adjudicate_document(document).units[0]

    assert unit.functions == ["Y"]
    assert "R_without_question_anchor" not in rule_ids(unit)


def test_high_emotion_is_degraded_when_only_mentioned(tmp_path: Path) -> None:
    document = document_with_unit(
        tmp_path,
        "La gente siente miedo cuando faltan datos.",
        functions=["A"],
        primary_function="A",
        emotion_expressed="M",
        emotion_intensity=3,
        emotions_mentioned=["M"],
        confidence=0.8,
    )
    fake = FakeAdjudicatorClient(
        [
            adjudicated_payload(
                final_functions=["A"],
                final_primary_function="A",
                final_emotion_expressed="N",
                final_emotion_intensity=0,
                final_emotions_mentioned=["M"],
                changed_fields=["emotion_expressed", "emotion_intensity"],
            )
        ]
    )

    unit = ConservativeAdjudicator(llm_client=fake).adjudicate_document(document).units[0]

    assert unit.emotion_expressed == "N"
    assert unit.emotion_intensity == 0
    assert unit.emotions_mentioned == ["M"]


def test_k_vs_a_resolved_with_k_inheriting_a(tmp_path: Path) -> None:
    document = document_with_unit(
        tmp_path,
        "Esto demuestra que el flujo no escala.",
        functions=["A"],
        primary_function="A",
        confidence=0.82,
    )
    fake = FakeAdjudicatorClient(
        [
            adjudicated_payload(
                final_functions=["K"],
                final_primary_function="K",
                final_rejected_labels=[
                    {"label": "A", "reason": "The unit states a disputable thesis."}
                ],
            )
        ]
    )

    unit = ConservativeAdjudicator(llm_client=fake).adjudicate_document(document).units[0]

    assert unit.functions == ["K"]
    assert unit.inherited_functions[0].function == "A"
    assert unit.final_notation == "K_N0{0}"


def test_risk_detection_includes_locked_heuristic_conflict(tmp_path: Path) -> None:
    document = document_with_unit(
        tmp_path,
        "Por que importa?",
        functions=["A"],
        primary_function="A",
        heuristic_candidates=[
            {"label": "P", "confidence": 0.95, "reason": "Locked deterministic heuristic signal."}
        ],
    )
    unit = document.units[0]

    assert should_adjudicate(unit) is True
    assert "locked_heuristic_llm_conflict" in adjudication_risk_reasons(unit)


def test_classifier_infrastructure_failure_skips_adjudicator_call(tmp_path: Path) -> None:
    document = document_with_unit(
        tmp_path,
        "Por que importa?",
        functions=["P"],
        primary_function="P",
        confidence=0.0,
        method="heuristic",
        needs_review=True,
        review_status="needs_review",
        review_reasons=["llm_classification_failed"],
    )
    fake = FakeAdjudicatorClient([])

    unit = ConservativeAdjudicator(llm_client=fake).adjudicate_document(document).units[0]

    assert fake.calls == []
    assert unit.review_reasons == ["llm_classification_failed"]


def test_actionable_low_confidence_validator_flag_still_adjudicates(tmp_path: Path) -> None:
    document = document_with_unit(
        tmp_path,
        "Esto confirma la idea central.",
        functions=["D"],
        primary_function="D",
        confidence=0.4,
        needs_review=True,
        review_status="needs_review",
        validator_flags=[
            {
                "rule_id": "D_without_evidence",
                "severity": "warning",
                "message": "D requires evidence.",
                "field": "evidence_spans",
            }
        ],
    )
    fake = FakeAdjudicatorClient(
        [adjudicated_payload(final_functions=["A"], final_primary_function="A")]
    )

    unit = ConservativeAdjudicator(llm_client=fake).adjudicate_document(document).units[0]

    assert len(fake.calls) == 1
    assert unit.functions == ["A"]
