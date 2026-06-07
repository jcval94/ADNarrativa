from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from narrative_dna.cli import app
from narrative_dna.evaluator import (
    build_label_metrics,
    evaluate_run,
    load_gold_units,
    write_evaluation_outputs,
)
from narrative_dna.models import GoldRecord, NarrativeDocument, SyntheticGoldCandidate
from tests.test_relation_detector import document, unit, unit_payload


def write_documents(tmp_path: Path, run_id: str, documents: list[NarrativeDocument]) -> Path:
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "documents.jsonl").write_text(
        "\n".join(json.dumps(item.model_dump(mode="json")) for item in documents) + "\n",
        encoding="utf-8",
    )
    return run_dir


def write_gold(path: Path, records: list[Any]) -> None:
    path.write_text(
        "\n".join(json.dumps(record.model_dump(mode="json")) for record in records) + "\n",
        encoding="utf-8",
    )


def gold_record(gold_id: str, payload: dict[str, Any]) -> GoldRecord:
    return GoldRecord.model_validate(
        {
            "gold_id": gold_id,
            "gold_type": "synthetic_gold_high_confidence",
            "unit": payload,
            "provenance": "test synthetic high confidence",
            "taxonomy_version_effective": "v1_0",
            "prompt_version_effective": "v1_0",
            "validator_version_effective": "v1_0",
        }
    )


def synthetic_candidate(
    candidate_id: str, payload: dict[str, Any], status: str
) -> SyntheticGoldCandidate:
    return SyntheticGoldCandidate.model_validate(
        {
            "candidate_id": candidate_id,
            "review_item_id": candidate_id.replace("candidate", "review"),
            "status": status,
            "unit": payload,
            "reliability_score": 0.95,
            "promotion_notes": "test candidate",
        }
    )


def test_evaluate_run_scores_units_and_reports() -> None:
    predicted_units = [
        unit(
            unit_id="u0",
            sequence_index=0,
            text="Esto demuestra una falla.",
            functions=["K"],
            primary_function="K",
        ),
        unit(
            unit_id="u1",
            sequence_index=1,
            text="El reporte registra 42 casos.",
            functions=["D"],
            primary_function="D",
        ),
    ]
    gold_u0 = unit_payload(
        unit_id="u0",
        sequence_index=0,
        text="Esto demuestra una falla.",
        functions=["K"],
        primary_function="K",
    )
    gold_u1 = unit_payload(
        unit_id="u1",
        sequence_index=1,
        text="El reporte registra 42 casos.",
        functions=["Y"],
        primary_function="Y",
    )
    gold_units = [gold_record("g0", gold_u0), gold_record("g1", gold_u1)]
    predictions = {item.unit_id: item for item in predicted_units}

    metrics = build_label_metrics(
        predictions=predictions,
        gold_units=[record.unit for record in gold_units],
    )

    assert metrics["labels"]["K"]["f1"] == 1.0
    assert metrics["labels"]["D"]["fp"] == 1
    assert metrics["labels"]["Y"]["fn"] == 1


def test_write_evaluation_outputs(tmp_path: Path) -> None:
    run_id = "run_eval"
    predicted_units = [
        unit(
            unit_id="u0",
            sequence_index=0,
            text="Esto demuestra una falla.",
            functions=["K"],
            primary_function="K",
        ),
        unit(
            unit_id="u1",
            sequence_index=1,
            text="El reporte registra 42 casos.",
            functions=["D"],
            primary_function="D",
        ),
    ]
    write_documents(tmp_path, run_id, [document("doc", predicted_units)])
    gold_path = tmp_path / "gold.jsonl"
    write_gold(
        gold_path,
        [
            gold_record(
                "g0",
                unit_payload(
                    unit_id="u0",
                    sequence_index=0,
                    text="Esto demuestra una falla.",
                    functions=["K"],
                    primary_function="K",
                ),
            ),
            gold_record(
                "g1",
                unit_payload(
                    unit_id="u1",
                    sequence_index=1,
                    text="El reporte registra 42 casos.",
                    functions=["Y"],
                    primary_function="Y",
                ),
            ),
        ],
    )

    metrics = write_evaluation_outputs(run_id=run_id, outputs_dir=tmp_path, gold_path=gold_path)

    assert metrics.total_gold_units == 2
    assert metrics.matched_units == 2
    assert metrics.functions_exact_match == 0.5
    assert metrics.primary_function_accuracy == 0.5
    assert metrics.micro_f1 == 0.5
    assert metrics.regression_pass_rate == 0.5
    run_dir = tmp_path / run_id
    assert (run_dir / "evaluation_metrics.json").exists()
    assert (run_dir / "label_metrics.json").exists()
    assert (run_dir / "confusion_groups_report.json").exists()
    assert (run_dir / "audit_report.json").exists()
    assert (run_dir / "audit_report.md").exists()
    payload = json.loads((run_dir / "evaluation_metrics.json").read_text(encoding="utf-8"))
    assert payload["taxonomy_version_effective"] == "v1_0"


def test_evaluate_run_counts_missing_and_unexpected_predictions(tmp_path: Path) -> None:
    run_id = "run_missing"
    predicted_units = [
        unit(
            unit_id="u0",
            sequence_index=0,
            text="Esto demuestra una falla.",
            functions=["K"],
            primary_function="K",
        ),
        unit(
            unit_id="u_extra",
            sequence_index=1,
            text="Extra.",
            functions=["A"],
            primary_function="A",
        ),
    ]
    write_documents(tmp_path, run_id, [document("doc", predicted_units)])
    gold_path = tmp_path / "gold.jsonl"
    write_gold(
        gold_path,
        [
            gold_record(
                "g0",
                unit_payload(
                    unit_id="u0",
                    sequence_index=0,
                    text="Esto demuestra una falla.",
                    functions=["K"],
                    primary_function="K",
                ),
            ),
            gold_record(
                "g_missing",
                unit_payload(
                    unit_id="u_missing",
                    sequence_index=2,
                    text="Falta.",
                    functions=["D"],
                    primary_function="D",
                ),
            ),
        ],
    )

    metrics, _, _, _ = evaluate_run(run_id=run_id, outputs_dir=tmp_path, gold_path=gold_path)

    assert metrics.missing_predictions == 1
    assert metrics.unexpected_predictions == 1
    assert metrics.matched_units == 1


def test_load_gold_units_rejects_non_high_confidence_synthetic_candidate(tmp_path: Path) -> None:
    gold_path = tmp_path / "gold_medium.jsonl"
    payload = unit_payload(
        unit_id="u0",
        sequence_index=0,
        text="Esto demuestra una falla.",
        functions=["K"],
        primary_function="K",
    )
    write_gold(
        gold_path,
        [synthetic_candidate("candidate_0", payload, "synthetic_gold_medium_confidence")],
    )

    with pytest.raises(ValueError, match="not high-confidence"):
        load_gold_units(gold_path)


def test_cli_evaluate_writes_reports(tmp_path: Path) -> None:
    run_id = "run_eval_cli"
    predicted_units = [
        unit(
            unit_id="u0",
            sequence_index=0,
            text="Esto demuestra una falla.",
            functions=["K"],
            primary_function="K",
        )
    ]
    write_documents(tmp_path, run_id, [document("doc", predicted_units)])
    gold_path = tmp_path / "gold.jsonl"
    write_gold(
        gold_path,
        [
            gold_record(
                "g0",
                unit_payload(
                    unit_id="u0",
                    sequence_index=0,
                    text="Esto demuestra una falla.",
                    functions=["K"],
                    primary_function="K",
                ),
            )
        ],
    )

    result = CliRunner().invoke(
        app,
        ["evaluate", "--run-id", run_id, "--outputs-dir", str(tmp_path), "--gold", str(gold_path)],
    )

    assert result.exit_code == 0
    assert "micro_f1=1.0000" in result.stdout
    assert (tmp_path / run_id / "evaluation_metrics.json").exists()
