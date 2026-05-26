from __future__ import annotations

from narrative_dna.validators import ValidationContext, normalize_and_validate_unit, validate_units


def unit_payload(**overrides):
    payload = {
        "document_id": "doc_001",
        "unit_id": "unit_001",
        "sequence_index": 0,
        "text": "Esto demuestra que el sistema falla.",
        "normalized_text": "esto demuestra que el sistema falla.",
        "functions": ["K"],
        "primary_function": "K",
        "secondary_functions": [],
        "inherited_functions": [],
        "certainty": "none",
        "emotion_expressed": "N",
        "emotion_intensity": 0,
        "emotions_mentioned": [],
        "stance": "neutral",
        "target": None,
        "speech_act": None,
        "logic": None,
        "evidence_spans": [],
        "rejected_labels": [],
        "validator_flags": [],
        "heuristic_candidates": [],
        "llm_votes": [],
        "confidence": 0.8,
        "method": "heuristic",
        "needs_review": False,
        "review_reasons": [],
        "review_status": "accepted",
        "final_notation": "MANUAL_SHOULD_BE_IGNORED",
        "taxonomy_version": "v1_0",
        "prompt_version": "v1_0",
        "validator_version": "v1_0",
    }
    payload.update(overrides)
    return payload


def rule_ids(unit) -> set[str]:
    return {flag.rule_id for flag in unit.validator_flags}


def test_n_exclusive_removes_n_and_derives_notation() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(
            functions=["N", "P", "V"],
            primary_function="N",
            emotion_expressed="S",
            emotion_intensity=1,
        )
    )

    assert unit.functions == ["P", "V"]
    assert unit.primary_function == "P"
    assert "N_exclusive" in rule_ids(unit)
    assert "notation_derivation" in rule_ids(unit)
    assert unit.final_notation == "(P+V)_S1{0}"


def test_k_inherits_a_and_removes_active_a() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(functions=["A", "K", "Y"], primary_function="K")
    )

    assert unit.functions == ["K", "Y"]
    assert unit.inherited_functions[0].function == "A"
    assert unit.inherited_functions[0].inherited_from == "K"
    assert unit.inherited_functions[0].reason == "K_subclass_of_A"
    assert "K_inherits_A" in rule_ids(unit)
    assert unit.final_notation == "(K+Y)_N0{0}"


def test_d_without_evidence_marks_review() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(
            text="Esto es evidencia clara.",
            normalized_text="esto es evidencia clara.",
            functions=["D"],
            primary_function="D",
        )
    )

    assert unit.needs_review is True
    assert "D_without_evidence" in rule_ids(unit)
    assert "D_without_evidence" in unit.review_reasons


def test_d_with_textual_evidence_signal_passes_without_review() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(
            text="El reporte registra 42 casos.",
            normalized_text="el reporte registra 42 casos.",
            functions=["D"],
            primary_function="D",
        )
    )

    assert unit.needs_review is False
    assert "D_without_evidence" not in rule_ids(unit)


def test_r_without_question_anchor_marks_review() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(
            text="La respuesta es que falta evidencia.",
            normalized_text="la respuesta es que falta evidencia.",
            functions=["R"],
            primary_function="R",
        )
    )

    assert unit.needs_review is True
    assert "R_without_question_anchor" in rule_ids(unit)


def test_r_with_previous_question_anchor_passes() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(
            text="La respuesta es que falta evidencia.",
            normalized_text="la respuesta es que falta evidencia.",
            functions=["R"],
            primary_function="R",
        ),
        context=ValidationContext(previous_text="¿Por qué falla?"),
    )

    assert unit.needs_review is False
    assert "R_without_question_anchor" not in rule_ids(unit)


def test_emotion_mentioned_vs_expressed_flags_confusion() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(
            text="El informe menciona miedo en usuarios.",
            normalized_text="el informe menciona miedo en usuarios.",
            functions=["A"],
            primary_function="A",
            emotion_expressed="M",
            emotion_intensity=2,
            emotions_mentioned=["M"],
        )
    )

    assert unit.needs_review is True
    assert "possible_emotion_confusion" in rule_ids(unit)


def test_overlabeling_marks_review() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(
            functions=["K", "Y", "D", "Q", "E", "V"],
            primary_function="K",
            evidence_spans=[{"text": "El reporte registra 42 casos."}],
        )
    )

    assert unit.needs_review is True
    assert "possible_overlabeling" in rule_ids(unit)


def test_primary_function_required_is_repaired() -> None:
    unit = normalize_and_validate_unit(unit_payload(functions=["P", "V"], primary_function="K"))

    assert unit.primary_function == "P"
    assert "primary_function_required" in rule_ids(unit)


def test_validate_units_uses_neighbor_context() -> None:
    question = unit_payload(
        unit_id="u1",
        sequence_index=0,
        text="¿Por qué falla?",
        normalized_text="¿por qué falla?",
        functions=["P"],
        primary_function="P",
    )
    answer = unit_payload(
        unit_id="u2",
        sequence_index=1,
        text="La respuesta es que falta evidencia.",
        normalized_text="la respuesta es que falta evidencia.",
        functions=["R"],
        primary_function="R",
    )

    validated = validate_units([question, answer])

    assert "R_without_question_anchor" not in rule_ids(validated[1])
