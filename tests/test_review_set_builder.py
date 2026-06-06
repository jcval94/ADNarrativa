from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from narrative_dna.cli import app
from narrative_dna.models import NarrativeDocument, NarrativeUnit
from narrative_dna.notation import derive_final_notation
from narrative_dna.review_set_builder import (
    build_review_set,
    confusable_labels,
    write_review_set,
)


def unit_payload(
    *,
    document_id: str,
    unit_id: str,
    sequence_index: int,
    text: str,
    functions: list[str],
    primary_function: str,
    confidence: float = 0.9,
    needs_review: bool = False,
    review_reasons: list[str] | None = None,
    validator_flags: list[dict[str, Any]] | None = None,
    emotion_expressed: str = "N",
    emotion_intensity: int = 0,
    emotions_mentioned: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "document_id": document_id,
        "unit_id": unit_id,
        "sequence_index": sequence_index,
        "text": text,
        "normalized_text": text.lower(),
        "functions": functions,
        "primary_function": primary_function,
        "secondary_functions": [function for function in functions if function != primary_function],
        "inherited_functions": [],
        "certainty": "none",
        "emotion_expressed": emotion_expressed,
        "emotion_intensity": emotion_intensity,
        "emotions_mentioned": emotions_mentioned or [],
        "stance": "neutral",
        "target": None,
        "speech_act": None,
        "logic": None,
        "evidence_spans": [{"text": text}],
        "rejected_labels": [],
        "validator_flags": validator_flags or [],
        "heuristic_candidates": [],
        "llm_votes": [],
        "confidence": confidence,
        "method": "adjudicated",
        "needs_review": needs_review,
        "review_reasons": review_reasons or [],
        "review_status": "needs_review" if needs_review else "accepted",
        "final_notation": "",
        "taxonomy_version": "v1_0",
        "prompt_version": "v1_0",
        "validator_version": "v1_0",
    }
    payload["final_notation"] = derive_final_notation(payload)
    return payload


def unit(**kwargs: Any) -> NarrativeUnit:
    return NarrativeUnit.model_validate(unit_payload(**kwargs))


def document(document_id: str, units: list[NarrativeUnit]) -> NarrativeDocument:
    return NarrativeDocument.model_validate(
        {
            "document_id": document_id,
            "source_path": f"{document_id}.txt",
            "source_type": "txt",
            "language": "es",
            "metadata": {},
            "segmentation": {"strategy": "test", "unit_count": len(units), "notes": []},
            "units": [item.model_dump(mode="json") for item in units],
            "relations": [],
            "chains": [],
            "document_metrics": {},
            "audit_summary": {},
        }
    )


def write_run(tmp_path: Path, run_id: str, documents: list[NarrativeDocument]) -> Path:
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "documents.jsonl").write_text(
        "\n".join(json.dumps(document.model_dump(mode="json")) for document in documents) + "\n",
        encoding="utf-8",
    )
    return run_dir


def write_guideline_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    minimal_pairs_path = tmp_path / "minimal_pairs.jsonl"
    minimal_pairs_path.write_text(
        json.dumps(
            {
                "pair_id": "mp_ak_001",
                "text_a": "El documento tiene version.",
                "text_b": "Esto demuestra que el flujo no escala.",
                "confusable_labels": ["A", "K"],
                "decision_rule_id": "DT_A_K_O",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    taxonomy_path = tmp_path / "taxonomy.json"
    taxonomy_path.write_text(
        json.dumps(
            {
                "functions": [
                    {
                        "code": "A",
                        "name": "Assertion",
                        "definition": "Stable statement.",
                        "boundary_rules": ["Use for descriptive assertions."],
                        "confusable_with": ["K", "O"],
                    },
                    {
                        "code": "K",
                        "name": "Claim",
                        "definition": "Argumentative claim.",
                        "boundary_rules": ["Use when disputable and argumentative."],
                        "confusable_with": ["A", "O"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    decision_trees_path = tmp_path / "decision_trees.md"
    decision_trees_path.write_text(
        "# Decision Trees\n\n"
        "## DT_A_K_O\n"
        "Choose A for descriptive claims and K for disputable claims.\n",
        encoding="utf-8",
    )
    return minimal_pairs_path, taxonomy_path, decision_trees_path


def test_build_review_set_prioritizes_difficult_and_boundary_cases(tmp_path: Path) -> None:
    run_id = "run_review"
    flagged_unit = unit(
        document_id="doc",
        unit_id="u0",
        sequence_index=0,
        text="Esto demuestra que el sistema falla.",
        functions=["K"],
        primary_function="K",
        confidence=0.62,
        needs_review=True,
        review_reasons=["ambiguous_claim"],
        validator_flags=[
            {
                "rule_id": "claim_disputability_test",
                "severity": "warning",
                "message": "Claim needs stronger evidence.",
                "field": "functions",
            }
        ],
    )
    intense_unit = unit(
        document_id="doc",
        unit_id="u1",
        sequence_index=1,
        text="Me frustra muchisimo que esto siga fallando.",
        functions=["O"],
        primary_function="O",
        confidence=0.8,
        emotion_expressed="F",
        emotion_intensity=3,
        emotions_mentioned=["F"],
    )
    high_confidence_unit = unit(
        document_id="doc",
        unit_id="u2",
        sequence_index=2,
        text="El documento tiene version.",
        functions=["F"],
        primary_function="F",
        confidence=0.97,
    )
    other_doc_unit = unit(
        document_id="doc_b",
        unit_id="b0",
        sequence_index=0,
        text="Esto demuestra que el sistema falla.",
        functions=["A"],
        primary_function="A",
        confidence=0.93,
    )
    run_dir = write_run(
        tmp_path,
        run_id,
        [
            document("doc", [flagged_unit, intense_unit, high_confidence_unit]),
            document("doc_b", [other_doc_unit]),
        ],
    )
    (run_dir / "similarity_conflicts.jsonl").write_text(
        json.dumps(
            {
                "conflict_id": "conflict_001",
                "run_id": run_id,
                "unit_id_a": "u0",
                "unit_id_b": "b0",
                "similarity": 0.96,
                "notation_distance": 0.4,
                "conflict_score": 0.74,
                "conflict_explanation_type": "likely_inconsistency",
                "differing_fields": ["primary_function", "final_notation"],
                "explanation": "Same text received A/K labels.",
                "needs_review": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    minimal_pairs_path, taxonomy_path, decision_trees_path = write_guideline_files(tmp_path)

    items, manifest = build_review_set(
        run_id=run_id,
        outputs_dir=tmp_path,
        minimal_pairs_path=minimal_pairs_path,
        taxonomy_path=taxonomy_path,
        decision_trees_path=decision_trees_path,
        high_confidence_sample_size=1,
    )

    assert manifest.item_count == len(items)
    assert manifest.source_similarity_conflicts == 1
    assert manifest.taxonomy_version_effective == "v1_0"
    assert any(item.item_type == "similar_pair" for item in items)
    assert any(item.item_type == "minimal_pair" for item in items)
    assert any(item.unit_id == "u0" and item.validator_flags for item in items)
    assert any(item.unit_id == "u1" and item.review_goal == "resolve_confusion" for item in items)
    assert any(
        item.unit_id == "u2"
        and item.review_goal == "validate"
        and item.expected_difficulty == "easy"
        for item in items
    )
    similar_pair = next(item for item in items if item.item_type == "similar_pair")
    assert similar_pair.similarity_conflict_info is not None
    assert similar_pair.unit_ids == ["u0", "b0"]
    assert "DT_A_K_O" in similar_pair.relevant_decision_tree


def test_write_review_set_outputs_jsonl_and_manifest(tmp_path: Path) -> None:
    run_id = "run_write_review"
    review_unit = unit(
        document_id="doc",
        unit_id="u0",
        sequence_index=0,
        text="Esto parece una opinion.",
        functions=["O"],
        primary_function="O",
        confidence=0.7,
    )
    write_run(tmp_path, run_id, [document("doc", [review_unit])])
    minimal_pairs_path, taxonomy_path, decision_trees_path = write_guideline_files(tmp_path)
    items, manifest = build_review_set(
        run_id=run_id,
        outputs_dir=tmp_path,
        minimal_pairs_path=minimal_pairs_path,
        taxonomy_path=taxonomy_path,
        decision_trees_path=decision_trees_path,
    )

    items_path, manifest_path = write_review_set(
        run_id=run_id,
        items=items,
        manifest=manifest,
        outputs_dir=tmp_path,
    )

    first_item = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    written_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert first_item["taxonomy_version_effective"] == "v1_0"
    assert written_manifest["item_count"] == len(items)
    assert items_path.parent.name == "review"


def test_cli_build_review_set_writes_review_directory(tmp_path: Path) -> None:
    run_id = "run_cli_review"
    review_unit = unit(
        document_id="doc",
        unit_id="u0",
        sequence_index=0,
        text="El documento tiene version.",
        functions=["F"],
        primary_function="F",
        confidence=0.99,
    )
    write_run(tmp_path, run_id, [document("doc", [review_unit])])

    result = CliRunner().invoke(
        app,
        ["build-review-set", "--run-id", run_id, "--outputs-dir", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert (tmp_path / run_id / "review" / "review_items.jsonl").exists()
    assert "Wrote" in result.stdout


def test_t_m_l_z_confusable_group_is_selected() -> None:
    transition_unit = unit(
        document_id="doc",
        unit_id="u0",
        sequence_index=0,
        text="Ahora pasemos al siguiente punto.",
        functions=["T"],
        primary_function="T",
    )

    assert confusable_labels(transition_unit) == ["L", "M", "T", "Z"]
