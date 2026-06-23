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


def test_certainty_requires_epistemic_signal() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(
            text="Me indigna esta decision del equipo.",
            normalized_text="me indigna esta decision del equipo.",
            certainty="strong",
            emotion_expressed="E",
            emotion_intensity=2,
        )
    )

    assert unit.needs_review is True
    assert "certainty_epistemic_not_intensity" in rule_ids(unit)


def test_certainty_epistemic_signal_passes() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(
            text="Claramente esto demuestra que el sistema falla.",
            normalized_text="claramente esto demuestra que el sistema falla.",
            certainty="strong",
        )
    )

    assert unit.needs_review is False
    assert "certainty_epistemic_not_intensity" not in rule_ids(unit)


def test_non_neutral_stance_requires_target() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(
            text="Esto funciona bien.",
            normalized_text="esto funciona bien.",
            stance="positive",
        )
    )

    assert unit.needs_review is True
    assert "stance_requires_target_when_non_neutral" in rule_ids(unit)


def test_non_neutral_stance_with_target_passes() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(
            text="La regla funciona bien para el equipo.",
            normalized_text="la regla funciona bien para el equipo.",
            stance="positive",
            target="equipo",
        )
    )

    assert unit.needs_review is False
    assert "stance_requires_target_when_non_neutral" not in rule_ids(unit)


def test_contrast_group_requires_boundary_signal() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(
            text="Esto sigue el tema general.",
            normalized_text="esto sigue el tema general.",
            functions=["C"],
            primary_function="C",
            target="propuesta",
        )
    )

    assert unit.needs_review is True
    assert "contrast_boundary_required" in rule_ids(unit)


def test_contrast_group_requires_target_or_proposition() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(
            text="Hay un riesgo serio si faltan datos.",
            normalized_text="hay un riesgo serio si faltan datos.",
            functions=["X"],
            primary_function="X",
        )
    )

    assert unit.needs_review is True
    assert "contrast_refutation_risk_target" in rule_ids(unit)
    assert "contrast_boundary_required" not in rule_ids(unit)


def test_contrast_group_with_signal_and_target_passes() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(
            text="Pero la propuesta tiene un limite claro.",
            normalized_text="pero la propuesta tiene un limite claro.",
            functions=["C"],
            primary_function="C",
            target="propuesta",
        )
    )

    assert unit.needs_review is False
    assert "contrast_boundary_required" not in rule_ids(unit)
    assert "contrast_refutation_risk_target" not in rule_ids(unit)


def test_illustrative_group_requires_boundary_signal() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(
            text="Esto desarrolla la idea principal.",
            normalized_text="esto desarrolla la idea principal.",
            functions=["G"],
            primary_function="G",
        )
    )

    assert unit.needs_review is True
    assert "illustrative_boundary_required" in rule_ids(unit)


def test_illustrative_group_with_signal_passes() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(
            text="Funciona como una caja negra del avion.",
            normalized_text="funciona como una caja negra del avion.",
            functions=["G"],
            primary_function="G",
        )
    )

    assert unit.needs_review is False
    assert "illustrative_boundary_required" not in rule_ids(unit)


def test_illustrative_multilabel_primary_priority_conflict_marks_review() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(
            text="Por ejemplo, revisa este caso concreto.",
            normalized_text="por ejemplo, revisa este caso concreto.",
            functions=["E", "G"],
            primary_function="G",
        )
    )

    assert unit.needs_review is True
    assert "dominant_illustrative_unit" in rule_ids(unit)


def test_structural_group_requires_boundary_signal() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(
            text="Esto importa mucho para decidir.",
            normalized_text="esto importa mucho para decidir.",
            functions=["M"],
            primary_function="M",
        )
    )

    assert unit.needs_review is True
    assert "structural_boundary_required" in rule_ids(unit)


def test_structural_group_with_signal_passes() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(
            text="En resumen, esta es la idea central.",
            normalized_text="en resumen, esta es la idea central.",
            functions=["Z"],
            primary_function="Z",
        )
    )

    assert unit.needs_review is False
    assert "structural_boundary_required" not in rule_ids(unit)


def test_structural_multilabel_primary_priority_conflict_marks_review() -> None:
    unit = normalize_and_validate_unit(
        unit_payload(
            text="Primero, limpia el texto antes de clasificar.",
            normalized_text="primero, limpia el texto antes de clasificar.",
            functions=["L", "Z"],
            primary_function="Z",
        )
    )

    assert unit.needs_review is True
    assert "structural_primary_priority" in rule_ids(unit)


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
