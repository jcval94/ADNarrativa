from __future__ import annotations

import pytest

from narrative_dna.heuristic_candidates import (
    annotate_document_with_heuristics,
    annotate_unit_with_heuristics,
    apply_heuristic_baseline_to_unit,
    extract_heuristic_candidates,
)
from narrative_dna.loader import load_document
from narrative_dna.models import NarrativeUnit
from narrative_dna.segmenter import segment_transcript


def unit(text: str, *, sequence_index: int = 0) -> NarrativeUnit:
    candidate = segment_transcript(document_id="doc_h", text=text)[0]
    if sequence_index == candidate.sequence_index:
        return candidate
    payload = candidate.model_dump(mode="json")
    payload["sequence_index"] = sequence_index
    payload["unit_id"] = f"doc_h_u{sequence_index:05d}"
    return NarrativeUnit.model_validate(payload)


def all_function_signals(text: str, *, sequence_index: int = 0, total_units: int | None = None):
    extraction = extract_heuristic_candidates(
        unit(text, sequence_index=sequence_index),
        total_units=total_units,
    )
    return set(extraction.locked_functions) | set(extraction.candidate_functions)


@pytest.mark.parametrize(
    ("code", "text", "sequence_index", "total_units"),
    [
        ("P", "Por que pasa esto?", 0, None),
        ("Z", "En resumen, esta es la idea central.", 8, 10),
        ("D", "Segun la encuesta, 42% cambio su habito.", 0, None),
        ("Y", "Esto ocurre porque nadie mide bien.", 0, None),
        ("E", "Por ejemplo, imagina una caja negra.", 0, None),
        ("H", "Recuerdo que una vez me paso algo parecido.", 0, None),
        ("G", "Esto es como una caja negra narrativa.", 0, None),
        ("C", "La idea funciona, pero tiene un limite.", 0, None),
        ("B", "Alguien podria decir que esto es exagerado.", 0, None),
        ("X", "Ojo, hay un riesgo importante.", 0, None),
        ("S", "Te recomiendo medirlo cada semana.", 0, None),
        ("I", "Haz una lista antes de decidir.", 0, None),
        ("U", "La leccion es que lo simple se sostiene.", 0, None),
        ("V", "Preguntate que pasaria en tu caso.", 0, None),
        ("O", "Creo que esta lectura es mas estable.", 0, None),
        ("F", "Esto significa que la senal no es final.", 0, None),
        ("L", "Primero, limpiamos el texto.", 0, None),
        ("M", "Voy a explicar por que importa.", 0, None),
        ("Q", 'El autor dijo: "esto cambia todo".', 0, None),
    ],
)
def test_positive_function_heuristics(code, text, sequence_index, total_units) -> None:
    assert code in all_function_signals(
        text,
        sequence_index=sequence_index,
        total_units=total_units,
    )


def test_question_marker_is_locked_not_final_classification() -> None:
    source_unit = unit("Por que importa?")
    extraction = extract_heuristic_candidates(source_unit)
    annotated = annotate_unit_with_heuristics(source_unit)

    assert extraction.locked_functions == ["P"]
    assert annotated.functions == ["N"]
    assert annotated.final_notation == "N_N0{0}"
    assert annotated.heuristic_candidates[0].label == "P"


def test_embedded_replacement_question_mark_is_not_question_signal() -> None:
    extraction = extract_heuristic_candidates(
        unit("Imagina un hospital peque?o con una br?jula operativa.")
    )

    assert "P" not in extraction.locked_functions
    assert "P" not in extraction.candidate_functions


def test_real_question_mark_still_locks_question_signal() -> None:
    assert "P" in all_function_signals("Que aprendiste este año?")
    assert "P" in all_function_signals("¿A quién ayuda este sistema?")


def test_heuristic_baseline_promotes_high_confidence_candidates() -> None:
    baseline = apply_heuristic_baseline_to_unit(
        unit("Pero hay un riesgo serio porque faltan datos.")
    )

    assert baseline.method == "heuristic"
    assert baseline.final_notation != "N_N0{0}"
    assert "D" in baseline.functions
    assert "Y" in baseline.functions
    assert baseline.needs_review is True


def test_conclusion_only_locks_near_document_end() -> None:
    early = extract_heuristic_candidates(
        unit("En resumen, abrimos el tema.", sequence_index=1), total_units=10
    )
    late = extract_heuristic_candidates(
        unit("En resumen, cerramos el tema.", sequence_index=9), total_units=10
    )

    assert "Z" in early.candidate_functions
    assert "Z" not in early.locked_functions
    assert "Z" in late.locked_functions


def test_controlled_false_positive_pero_bueno_is_not_strong_contrast() -> None:
    extraction = extract_heuristic_candidates(unit("Pero bueno, sigamos con el tema."))

    assert "C" not in extraction.candidate_functions
    assert "function:C.contrast_marker" not in extraction.heuristics_fired


def test_emotion_mentioned_is_not_emotion_expressed() -> None:
    extraction = extract_heuristic_candidates(unit("La gente siente miedo cuando faltan datos."))

    assert extraction.candidate_emotions_mentioned == ["M"]
    assert extraction.candidate_emotion_expressed is None


def test_emotion_expressed_uses_first_person_signal() -> None:
    extraction = extract_heuristic_candidates(unit("Me preocupa que nadie revise los datos."))

    assert extraction.candidate_emotion_expressed == "M"
    assert extraction.candidate_emotions_mentioned == []


def test_certainty_and_stance_candidates_are_separate_from_functions() -> None:
    extraction = extract_heuristic_candidates(
        unit("Claramente es valioso medirlo, aunque todavia falta contexto.")
    )

    assert extraction.candidate_certainty == "strong"
    assert extraction.candidate_stance == "positive"
    assert "C" in extraction.candidate_functions


def test_heuristics_include_auditable_evidence_spans() -> None:
    extraction = extract_heuristic_candidates(unit("Segun los datos, 42 casos cambiaron."))

    assert extraction.evidence_spans
    assert all(span.source for span in extraction.evidence_spans)


def test_annotates_document_without_changing_json_truth(tmp_path) -> None:
    transcript = tmp_path / "speech.txt"
    transcript.write_text("Por que importa? Porque cambia decisiones.", encoding="utf-8")
    document = load_document(transcript)

    annotated = annotate_document_with_heuristics(document)

    assert annotated.units[0].functions == ["N"]
    assert annotated.units[0].heuristic_candidates[0].label == "P"
    assert annotated.audit_summary["heuristic_candidate_unit_count"] >= 1
