from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from narrative_dna.evaluator import load_gold_units, write_evaluation_outputs
from narrative_dna.models import NarrativeDocument, SegmentationInfo, SyntheticGoldCandidate
from narrative_dna.notation import derive_final_notation
from narrative_dna.validators import normalize_and_validate_unit

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "golden_regression"
GOLD_PATH = FIXTURE_DIR / "synthetic_gold_high_confidence.jsonl"
EXPECTED_PATH = FIXTURE_DIR / "expected_notation_sequences.json"


def load_expected() -> dict[str, Any]:
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


def load_candidates() -> list[SyntheticGoldCandidate]:
    return [
        SyntheticGoldCandidate.model_validate(json.loads(line))
        for line in GOLD_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_synthetic_gold_fixture_is_regression_eligible_and_derives_notation() -> None:
    expected = load_expected()
    candidates = load_candidates()
    expected_sequence = expected["expected_sequence"]
    expected_by_unit = {item["unit_id"]: item["final_notation"] for item in expected_sequence}

    assert expected["allowed_gold_status"] == "synthetic_gold_high_confidence"
    assert [candidate.unit.unit_id for candidate in candidates] == [
        item["unit_id"] for item in expected_sequence
    ]
    assert [candidate.unit.final_notation for candidate in candidates] == [
        item["final_notation"] for item in expected_sequence
    ]

    for candidate in candidates:
        unit = candidate.unit
        assert candidate.status == "synthetic_gold_high_confidence"
        assert candidate.reliability_score >= expected["minimum_reliability_score"]
        assert candidate.taxonomy_version_effective == expected["taxonomy_version_effective"]
        assert candidate.prompt_version_effective == expected["prompt_version_effective"]
        assert candidate.validator_version_effective == expected["validator_version_effective"]
        assert unit.needs_review is False
        assert unit.validator_flags == []
        assert derive_final_notation(unit.model_dump(mode="json")) == expected_by_unit[unit.unit_id]

        tampered_payload = deepcopy(unit.model_dump(mode="json"))
        tampered_payload["final_notation"] = "MANUAL_EDIT_SHOULD_NOT_SURVIVE"
        repaired = normalize_and_validate_unit(tampered_payload)

        assert repaired.final_notation == unit.final_notation
        assert any(flag.rule_id == "notation_derivation" for flag in repaired.validator_flags)


def test_golden_regression_fixture_evaluates_with_perfect_stability(tmp_path: Path) -> None:
    expected = load_expected()
    candidates = load_candidates()
    run_id = expected["run_id"]
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    document = NarrativeDocument(
        document_id="fixture_doc_001",
        source_path=str(GOLD_PATH),
        source_type="txt",
        language="en",
        metadata={
            "fixture_type": "synthetic_gold_high_confidence",
            "run_id": run_id,
        },
        segmentation=SegmentationInfo(
            strategy="golden_regression_fixture",
            unit_count=len(candidates),
            notes=["stable notation regression fixture"],
        ),
        units=[candidate.unit for candidate in candidates],
    )
    (run_dir / "documents.jsonl").write_text(
        json.dumps(document.model_dump(mode="json"), sort_keys=True) + "\n",
        encoding="utf-8",
    )

    metrics = write_evaluation_outputs(run_id=run_id, outputs_dir=tmp_path, gold_path=GOLD_PATH)

    assert metrics.total_gold_units == len(candidates)
    assert metrics.total_predicted_units == len(candidates)
    assert metrics.matched_units == len(candidates)
    assert metrics.missing_predictions == 0
    assert metrics.unexpected_predictions == 0
    assert metrics.functions_exact_match == 1.0
    assert metrics.primary_function_accuracy == 1.0
    assert metrics.micro_f1 == 1.0
    assert metrics.macro_f1 == 1.0
    assert metrics.regression_pass_rate == 1.0
    assert metrics.validator_violation_rate == 0.0
    assert metrics.needs_review_rate == 0.0

    payload = json.loads((run_dir / "evaluation_metrics.json").read_text(encoding="utf-8"))
    assert payload["run_id"] == run_id
    assert payload["taxonomy_version_effective"] == expected["taxonomy_version_effective"]
    assert payload["prompt_version_effective"] == expected["prompt_version_effective"]
    assert payload["validator_version_effective"] == expected["validator_version_effective"]
    assert Path(payload["outputs"]["evaluation_metrics"]).exists()


def test_non_high_confidence_synthetic_fixture_is_rejected_for_regression(
    tmp_path: Path,
) -> None:
    first_candidate = json.loads(GOLD_PATH.read_text(encoding="utf-8").splitlines()[0])
    first_candidate["status"] = "synthetic_gold_medium_confidence"
    gold_path = tmp_path / "synthetic_gold_medium_confidence.jsonl"
    gold_path.write_text(json.dumps(first_candidate) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="not high-confidence"):
        load_gold_units(gold_path)
