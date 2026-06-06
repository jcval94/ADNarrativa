from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from narrative_dna.cli import app
from narrative_dna.models import (
    NarrativeUnit,
    SyntheticAggregatedReview,
    SyntheticFinalAdjudication,
    SyntheticGoldCandidate,
    SyntheticReviewerOutput,
    SyntheticReviewItem,
)
from narrative_dna.notation import derive_final_notation
from narrative_dna.synthetic_reliability import (
    score_synthetic_reliability,
    write_synthetic_reliability_outputs,
)


def unit_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "document_id": "doc",
        "unit_id": "u0",
        "sequence_index": 0,
        "text": "Esto demuestra que el flujo no escala.",
        "normalized_text": "esto demuestra que el flujo no escala.",
        "functions": ["K"],
        "primary_function": "K",
        "secondary_functions": [],
        "inherited_functions": [{"function": "A", "inherited_from": "K", "reason": "K_inherits_A"}],
        "certainty": "none",
        "emotion_expressed": "N",
        "emotion_intensity": 0,
        "emotions_mentioned": [],
        "stance": "neutral",
        "target": None,
        "speech_act": None,
        "logic": None,
        "evidence_spans": [{"text": "Esto demuestra que el flujo no escala."}],
        "rejected_labels": [],
        "validator_flags": [],
        "heuristic_candidates": [],
        "llm_votes": [],
        "confidence": 0.93,
        "method": "adjudicated",
        "needs_review": False,
        "review_reasons": [],
        "review_status": "accepted",
        "final_notation": "",
        "taxonomy_version": "v1_0",
        "prompt_version": "v1_0",
        "validator_version": "v1_0",
    }
    payload.update(overrides)
    payload["final_notation"] = derive_final_notation(payload)
    return payload


def unit(**overrides: Any) -> NarrativeUnit:
    return NarrativeUnit.model_validate(unit_payload(**overrides))


def review_item(review_item_id: str) -> SyntheticReviewItem:
    current_unit = unit(unit_id=f"unit_{review_item_id}")
    return SyntheticReviewItem(
        review_item_id=review_item_id,
        item_type="unit",
        document_id="doc",
        unit_id=current_unit.unit_id,
        unit_ids=[current_unit.unit_id],
        text=current_unit.text,
        context_before=[],
        context_after=[],
        current_prediction_json=current_unit.model_dump(mode="json"),
        current_notation=current_unit.final_notation,
        relevant_taxonomy_rules=[],
        relevant_decision_tree="## DT_A_K_O",
        relevant_minimal_pairs=[],
        validator_flags=[],
        similarity_conflict_info=None,
        expected_difficulty="medium",
        review_goal="validate",
        taxonomy_version_effective="v1_0",
        prompt_version_effective="v1_0",
        validator_version_effective="v1_0",
    )


def reviewer_output(
    *,
    run_id: str,
    review_item_id: str,
    reviewer_id: str,
    decision: str,
    confidence: float,
) -> SyntheticReviewerOutput:
    return SyntheticReviewerOutput(
        run_id=run_id,
        review_item_id=review_item_id,
        reviewer_id=reviewer_id,
        decision=decision,
        proposed_unit=None,
        confidence=confidence,
        rationale="Reviewer rationale.",
        validator_flags=[],
        taxonomy_version_effective="v1_0",
        prompt_version_effective="v1_0",
        validator_version_effective="v1_0",
    )


def aggregate(
    *,
    run_id: str,
    review_item_id: str,
    decisions: list[SyntheticReviewerOutput],
    decision: str,
    confidence: float,
) -> SyntheticAggregatedReview:
    return SyntheticAggregatedReview(
        run_id=run_id,
        review_item_id=review_item_id,
        decisions=decisions,
        aggregate_decision=decision,
        confidence=confidence,
        rationale="Aggregated rationale.",
        needs_final_adjudication=decision != "needs_review",
        taxonomy_version_effective="v1_0",
        prompt_version_effective="v1_0",
        validator_version_effective="v1_0",
    )


def final(
    *,
    run_id: str,
    review_item_id: str,
    decision: str,
    status: str | None,
    reliability: float,
    selected_unit: NarrativeUnit | None,
    needs_human_review: bool = False,
) -> SyntheticFinalAdjudication:
    return SyntheticFinalAdjudication(
        run_id=run_id,
        review_item_id=review_item_id,
        final_decision=decision,
        gold_status=status,
        selected_unit=selected_unit,
        reliability_score=reliability,
        rationale="Final rationale.",
        validator_flags=[],
        needs_human_review=needs_human_review,
        taxonomy_version_effective="v1_0",
        prompt_version_effective="v1_0",
        validator_version_effective="v1_0",
    )


def candidate(
    *,
    run_id: str,
    review_item_id: str,
    status: str,
    reliability: float,
    item_unit: NarrativeUnit,
) -> SyntheticGoldCandidate:
    return SyntheticGoldCandidate(
        run_id=run_id,
        candidate_id=f"candidate_{review_item_id}",
        review_item_id=review_item_id,
        status=status,
        unit=item_unit,
        reliability_score=reliability,
        promotion_notes="Candidate notes.",
        taxonomy_version_effective="v1_0",
        prompt_version_effective="v1_0",
        validator_version_effective="v1_0",
    )


def write_jsonl(path: Path, records: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record.model_dump(mode="json")) for record in records)
        + ("\n" if records else ""),
        encoding="utf-8",
    )


def write_reliability_run(tmp_path: Path, run_id: str) -> None:
    first_unit = unit(unit_id="u1")
    second_unit = unit(unit_id="u2")
    review_items = [review_item("review_1"), review_item("review_2"), review_item("review_medium")]
    first_decisions = [
        reviewer_output(
            run_id=run_id,
            review_item_id="review_1",
            reviewer_id="a",
            decision="accept",
            confidence=0.9,
        ),
        reviewer_output(
            run_id=run_id,
            review_item_id="review_1",
            reviewer_id="b",
            decision="accept",
            confidence=0.95,
        ),
        reviewer_output(
            run_id=run_id,
            review_item_id="review_1",
            reviewer_id="c",
            decision="revise",
            confidence=0.7,
        ),
    ]
    second_decisions = [
        reviewer_output(
            run_id=run_id,
            review_item_id="review_2",
            reviewer_id="a",
            decision="needs_review",
            confidence=0.6,
        ),
        reviewer_output(
            run_id=run_id,
            review_item_id="review_2",
            reviewer_id="b",
            decision="needs_review",
            confidence=0.62,
        ),
    ]
    run_dir = tmp_path / run_id
    write_jsonl(run_dir / "review" / "review_items.jsonl", review_items)
    write_jsonl(run_dir / "synthetic_reviews.jsonl", [*first_decisions, *second_decisions])
    write_jsonl(
        run_dir / "synthetic_review_aggregated.jsonl",
        [
            aggregate(
                run_id=run_id,
                review_item_id="review_1",
                decisions=first_decisions,
                decision="accept",
                confidence=0.86,
            ),
            aggregate(
                run_id=run_id,
                review_item_id="review_2",
                decisions=second_decisions,
                decision="needs_review",
                confidence=0.61,
            ),
        ],
    )
    write_jsonl(
        run_dir / "synthetic_final_adjudications.jsonl",
        [
            final(
                run_id=run_id,
                review_item_id="review_1",
                decision="accept",
                status="synthetic_gold_high_confidence",
                reliability=0.93,
                selected_unit=first_unit,
            ),
            final(
                run_id=run_id,
                review_item_id="review_2",
                decision="needs_review",
                status="synthetic_gold_rejected",
                reliability=0.42,
                selected_unit=None,
                needs_human_review=True,
            ),
        ],
    )
    write_jsonl(
        run_dir / "synthetic_gold_candidates.jsonl",
        [
            candidate(
                run_id=run_id,
                review_item_id="review_1",
                status="synthetic_gold_high_confidence",
                reliability=0.93,
                item_unit=first_unit,
            ),
            candidate(
                run_id=run_id,
                review_item_id="review_medium",
                status="synthetic_gold_medium_confidence",
                reliability=0.84,
                item_unit=second_unit,
            ),
        ],
    )


def test_scores_synthetic_reliability_metrics(tmp_path: Path) -> None:
    run_id = "run_reliability"
    write_reliability_run(tmp_path, run_id)

    metrics = score_synthetic_reliability(run_id=run_id, outputs_dir=tmp_path)

    assert metrics.total_review_items == 3
    assert metrics.reviewer_output_count == 5
    assert metrics.high_confidence_count == 1
    assert metrics.medium_confidence_count == 1
    assert metrics.rejected_count == 1
    assert metrics.needs_human_review_count == 1
    assert metrics.regression_eligible_count == 1
    assert metrics.inter_reviewer_agreement == 0.8334
    assert metrics.adjudicator_agreement == 1.0
    assert metrics.reviewer_decisions_by_type["accept"] == 2


def test_writes_reliability_report_and_candidate_buckets(tmp_path: Path) -> None:
    run_id = "run_reliability_write"
    write_reliability_run(tmp_path, run_id)

    metrics = write_synthetic_reliability_outputs(run_id=run_id, outputs_dir=tmp_path)

    run_dir = tmp_path / run_id
    assert metrics.outputs["synthetic_reliability_report"].endswith(
        "synthetic_reliability_report.json"
    )
    assert (run_dir / "synthetic_reliability_report.md").exists()
    assert len((run_dir / "synthetic_gold_high_confidence.jsonl").read_text().splitlines()) == 1
    assert len((run_dir / "synthetic_gold_medium_confidence.jsonl").read_text().splitlines()) == 1
    assert (run_dir / "synthetic_gold_rejected.jsonl").read_text(encoding="utf-8") == ""


def test_cli_promote_synthetic_gold_scores_reliability(tmp_path: Path) -> None:
    run_id = "run_reliability_cli"
    write_reliability_run(tmp_path, run_id)

    result = CliRunner().invoke(
        app,
        ["promote-synthetic-gold", "--run-id", run_id, "--outputs-dir", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert "Scored synthetic reliability" in result.stdout
    report = json.loads((tmp_path / run_id / "synthetic_reliability_report.json").read_text())
    assert report["regression_eligible_count"] == 1
