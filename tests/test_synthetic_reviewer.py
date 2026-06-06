from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from narrative_dna.cli import app
from narrative_dna.llm_client import LLMCallResult
from narrative_dna.models import NarrativeUnit, SyntheticReviewItem
from narrative_dna.notation import derive_final_notation
from narrative_dna.synthetic_reviewer import (
    SyntheticCommitteeReviewer,
    load_review_items,
    run_and_write_synthetic_review,
)


class FakeCommitteeClient:
    def __init__(self, parsed_outputs: list[dict[str, Any] | LLMCallResult]) -> None:
        self.parsed_outputs = list(parsed_outputs)
        self.calls: list[dict[str, Any]] = []

    def request_structured(self, **kwargs: Any) -> LLMCallResult:
        self.calls.append(kwargs)
        output = self.parsed_outputs.pop(0)
        if isinstance(output, LLMCallResult):
            return output
        return LLMCallResult(
            ok=True,
            profile_name=kwargs["profile_name"],
            model="gpt-5.5",
            cache_key=f"synthetic_{len(self.calls)}",
            attempts=1,
            parsed=output,
            usage={"input_tokens": 10, "output_tokens": 5},
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
        "rejected_labels": [{"label": "A", "reason": "It is a disputable thesis."}],
        "validator_flags": [],
        "heuristic_candidates": [],
        "llm_votes": [],
        "confidence": 0.91,
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


def review_item(run_id: str = "run_synth") -> SyntheticReviewItem:
    current_unit = unit()
    return SyntheticReviewItem(
        review_item_id="review_001",
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
        relevant_decision_tree="## DT_A_K_O\nK is a disputable thesis.",
        relevant_minimal_pairs=[],
        validator_flags=[],
        similarity_conflict_info=None,
        expected_difficulty="medium",
        review_goal="validate",
        taxonomy_version_effective="v1_0",
        prompt_version_effective="v1_0",
        validator_version_effective="v1_0",
    )


def write_review_items(tmp_path: Path, run_id: str, items: list[SyntheticReviewItem]) -> Path:
    review_dir = tmp_path / run_id / "review"
    review_dir.mkdir(parents=True)
    (review_dir / "review_items.jsonl").write_text(
        "\n".join(json.dumps(item.model_dump(mode="json")) for item in items) + "\n",
        encoding="utf-8",
    )
    return review_dir


def reviewer_output(
    *,
    run_id: str,
    item: SyntheticReviewItem,
    reviewer_id: str,
    decision: str = "accept",
    confidence: float = 0.92,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "review_item_id": item.review_item_id,
        "reviewer_id": reviewer_id,
        "decision": decision,
        "proposed_unit": None,
        "confidence": confidence,
        "rationale": "Annotation is stable under the provided boundary rules.",
        "validator_flags": [],
        "taxonomy_version_effective": "v1_0",
        "prompt_version_effective": "v1_0",
        "validator_version_effective": "v1_0",
    }


def aggregate_output(
    *,
    run_id: str,
    item: SyntheticReviewItem,
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "review_item_id": item.review_item_id,
        "decisions": decisions,
        "aggregate_decision": "accept",
        "confidence": 0.9,
        "rationale": "Both reviewers accepted the annotation.",
        "needs_final_adjudication": True,
        "taxonomy_version_effective": "v1_0",
        "prompt_version_effective": "v1_0",
        "validator_version_effective": "v1_0",
    }


def final_output(
    *,
    run_id: str,
    item: SyntheticReviewItem,
    selected_unit: NarrativeUnit,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "review_item_id": item.review_item_id,
        "final_decision": "accept",
        "gold_status": "synthetic_gold_high_confidence",
        "selected_unit": selected_unit.model_dump(mode="json"),
        "reliability_score": 0.91,
        "rationale": "Committee agreement is strong and validators are clean.",
        "validator_flags": [],
        "needs_human_review": False,
        "taxonomy_version_effective": "v1_0",
        "prompt_version_effective": "v1_0",
        "validator_version_effective": "v1_0",
    }


def failing_result(profile_name: str) -> LLMCallResult:
    return LLMCallResult(
        ok=False,
        profile_name=profile_name,
        model="gpt-5.5",
        cache_key=f"failed_{profile_name}",
        attempts=1,
        error_type="mock_failure",
        error="mock failure",
    )


def test_synthetic_committee_writes_reviews_aggregates_and_candidates(tmp_path: Path) -> None:
    run_id = "run_synth"
    item = review_item(run_id)
    selected_unit = unit()
    decisions = [
        reviewer_output(run_id=run_id, item=item, reviewer_id="reviewer_a"),
        reviewer_output(run_id=run_id, item=item, reviewer_id="reviewer_b"),
    ]
    fake = FakeCommitteeClient(
        [
            decisions[0],
            decisions[1],
            aggregate_output(run_id=run_id, item=item, decisions=decisions),
            final_output(run_id=run_id, item=item, selected_unit=selected_unit),
        ]
    )
    write_review_items(tmp_path, run_id, [item])
    reviewer = SyntheticCommitteeReviewer(
        llm_client=fake,
        reviewer_profiles=["reviewer_a", "reviewer_b"],
    )

    report = run_and_write_synthetic_review(
        run_id=run_id,
        outputs_dir=tmp_path,
        reviewer=reviewer,
    )

    assert [call["profile_name"] for call in fake.calls] == [
        "reviewer_a",
        "reviewer_b",
        "synthetic_aggregator",
        "synthetic_final_adjudicator",
    ]
    assert report.reviewer_output_count == 2
    assert report.synthetic_gold_candidate_count == 1
    candidate_path = tmp_path / run_id / "synthetic_gold_candidates.jsonl"
    candidate = json.loads(candidate_path.read_text(encoding="utf-8").splitlines()[0])
    assert candidate["status"] == "synthetic_gold_high_confidence"
    assert candidate["unit"]["final_notation"] == selected_unit.final_notation
    assert (tmp_path / run_id / "synthetic_review_report.md").exists()


def test_synthetic_committee_falls_back_conservatively_on_aggregation_failures(
    tmp_path: Path,
) -> None:
    run_id = "run_synth_fallback"
    item = review_item(run_id)
    decisions = [
        reviewer_output(run_id=run_id, item=item, reviewer_id="reviewer_a", confidence=0.78),
        reviewer_output(run_id=run_id, item=item, reviewer_id="reviewer_b", confidence=0.76),
    ]
    fake = FakeCommitteeClient(
        [
            decisions[0],
            decisions[1],
            failing_result("synthetic_aggregator"),
            failing_result("synthetic_final_adjudicator"),
        ]
    )
    write_review_items(tmp_path, run_id, [item])
    reviewer = SyntheticCommitteeReviewer(
        llm_client=fake,
        reviewer_profiles=["reviewer_a", "reviewer_b"],
    )

    report = run_and_write_synthetic_review(
        run_id=run_id,
        outputs_dir=tmp_path,
        reviewer=reviewer,
    )

    assert report.reviewer_failure_count == 2
    assert report.aggregated_count == 1
    assert report.synthetic_gold_candidate_count == 0
    finals = (tmp_path / run_id / "synthetic_final_adjudications.jsonl").read_text(encoding="utf-8")
    assert '"needs_human_review": true' in finals


def test_cli_synthetic_review_dry_run_writes_empty_report_without_api_key(tmp_path: Path) -> None:
    run_id = "run_cli_synth"
    write_review_items(tmp_path, run_id, [review_item(run_id)])

    result = CliRunner().invoke(
        app,
        [
            "synthetic-review",
            "--run-id",
            run_id,
            "--outputs-dir",
            str(tmp_path),
            "--dry-run",
            "--max-items",
            "1",
        ],
    )

    assert result.exit_code == 0
    report = json.loads((tmp_path / run_id / "synthetic_review_report.json").read_text())
    assert report["reviewer_output_count"] == 0
    assert report["reviewer_failure_count"] == 3
    assert load_review_items(tmp_path / run_id)[0].review_item_id == "review_001"
