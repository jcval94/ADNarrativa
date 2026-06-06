"""Synthetic review reliability scoring entry points."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from narrative_dna.models import (
    SyntheticAggregatedReview,
    SyntheticDecision,
    SyntheticFinalAdjudication,
    SyntheticGoldCandidate,
    SyntheticGoldStatus,
    SyntheticReliabilityMetrics,
    SyntheticReviewerOutput,
    SyntheticReviewItem,
)

DEFAULT_TAXONOMY_VERSION = "v1_0"
DEFAULT_PROMPT_VERSION = "v1_0"
DEFAULT_VALIDATOR_VERSION = "v1_0"
REGRESSION_ELIGIBLE_THRESHOLD = 0.9

T = TypeVar("T", bound=BaseModel)


def score_synthetic_reliability(
    *,
    run_id: str,
    outputs_dir: str | Path = "outputs",
) -> SyntheticReliabilityMetrics:
    """Score synthetic review outputs without calling an LLM."""

    run_dir = Path(outputs_dir) / run_id
    review_items = load_jsonl(run_dir / "review" / "review_items.jsonl", SyntheticReviewItem)
    reviewer_outputs = load_jsonl(run_dir / "synthetic_reviews.jsonl", SyntheticReviewerOutput)
    aggregated = load_jsonl(
        run_dir / "synthetic_review_aggregated.jsonl", SyntheticAggregatedReview
    )
    finals = load_jsonl(
        run_dir / "synthetic_final_adjudications.jsonl",
        SyntheticFinalAdjudication,
    )
    candidates = load_jsonl(run_dir / "synthetic_gold_candidates.jsonl", SyntheticGoldCandidate)

    agreement_by_item = reviewer_agreement_by_item(reviewer_outputs)
    final_reliability_by_item = {
        final.review_item_id: round(final.reliability_score, 4) for final in finals
    }
    status_counts = gold_status_counts(finals=finals, candidates=candidates)
    high_count = status_counts.get(SyntheticGoldStatus.HIGH_CONFIDENCE.value, 0)
    medium_count = status_counts.get(SyntheticGoldStatus.MEDIUM_CONFIDENCE.value, 0)
    rejected_count = status_counts.get(SyntheticGoldStatus.REJECTED.value, 0) + sum(
        1
        for final in finals
        if final.final_decision == SyntheticDecision.REJECT and final.gold_status is None
    )
    needs_review_count = sum(
        1 for final in finals if final.final_decision == SyntheticDecision.NEEDS_REVIEW
    )
    regression_eligible_count = sum(
        1
        for candidate in candidates
        if candidate.status == SyntheticGoldStatus.HIGH_CONFIDENCE
        and candidate.reliability_score >= REGRESSION_ELIGIBLE_THRESHOLD
        and not candidate.unit.needs_review
        and not candidate.unit.validator_flags
    )
    metrics = SyntheticReliabilityMetrics(
        run_id=run_id,
        total_review_items=len(review_items),
        reviewer_output_count=len(reviewer_outputs),
        aggregated_review_count=len(aggregated),
        final_adjudication_count=len(finals),
        synthetic_gold_candidate_count=len(candidates),
        high_confidence_count=high_count,
        medium_confidence_count=medium_count,
        rejected_count=rejected_count,
        needs_review_count=needs_review_count,
        needs_human_review_count=sum(1 for final in finals if final.needs_human_review),
        inter_reviewer_agreement=average(list(agreement_by_item.values())),
        adjudicator_agreement=adjudicator_agreement(aggregated, finals),
        average_reviewer_confidence=average([output.confidence for output in reviewer_outputs]),
        average_aggregate_confidence=average([item.confidence for item in aggregated]),
        average_final_reliability=average([item.reliability_score for item in finals]),
        regression_eligible_count=regression_eligible_count,
        regression_eligible_rate=ratio(regression_eligible_count, len(review_items)),
        reviewer_decisions_by_type=count_values(
            str(output.decision) for output in reviewer_outputs
        ),
        aggregate_decisions_by_type=count_values(
            str(item.aggregate_decision) for item in aggregated
        ),
        final_decisions_by_type=count_values(str(item.final_decision) for item in finals),
        gold_status_counts=status_counts,
        agreement_by_item=agreement_by_item,
        reliability_by_item=final_reliability_by_item,
        outputs={},
        taxonomy_version_effective=DEFAULT_TAXONOMY_VERSION,
        prompt_version_effective=DEFAULT_PROMPT_VERSION,
        validator_version_effective=DEFAULT_VALIDATOR_VERSION,
    )
    return metrics


def write_synthetic_reliability_outputs(
    *,
    run_id: str,
    outputs_dir: str | Path = "outputs",
    metrics: SyntheticReliabilityMetrics | None = None,
) -> SyntheticReliabilityMetrics:
    """Write reliability report and derived synthetic gold buckets."""

    run_dir = Path(outputs_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    metrics = metrics or score_synthetic_reliability(run_id=run_id, outputs_dir=outputs_dir)
    candidates = load_jsonl(run_dir / "synthetic_gold_candidates.jsonl", SyntheticGoldCandidate)
    high, medium, rejected = split_candidates(candidates)
    paths = {
        "synthetic_gold_high_confidence": run_dir / "synthetic_gold_high_confidence.jsonl",
        "synthetic_gold_medium_confidence": run_dir / "synthetic_gold_medium_confidence.jsonl",
        "synthetic_gold_rejected": run_dir / "synthetic_gold_rejected.jsonl",
        "synthetic_reliability_report": run_dir / "synthetic_reliability_report.json",
        "synthetic_reliability_report_md": run_dir / "synthetic_reliability_report.md",
    }
    write_jsonl(paths["synthetic_gold_high_confidence"], high)
    write_jsonl(paths["synthetic_gold_medium_confidence"], medium)
    write_jsonl(paths["synthetic_gold_rejected"], rejected)
    payload = metrics.model_dump(mode="json")
    payload["outputs"] = {key: str(path) for key, path in paths.items()}
    metrics = SyntheticReliabilityMetrics.model_validate(payload)
    paths["synthetic_reliability_report"].write_text(
        json.dumps(metrics.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    paths["synthetic_reliability_report_md"].write_text(
        reliability_markdown(metrics), encoding="utf-8"
    )
    return metrics


def load_jsonl(path: Path, model: type[T]) -> list[T]:
    if not path.exists():
        return []
    return [
        model.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def reviewer_agreement_by_item(outputs: list[SyntheticReviewerOutput]) -> dict[str, float]:
    grouped: dict[str, list[SyntheticReviewerOutput]] = defaultdict(list)
    for output in outputs:
        grouped[output.review_item_id].append(output)
    agreement: dict[str, float] = {}
    for review_item_id, decisions in grouped.items():
        counts = Counter(str(decision.decision) for decision in decisions)
        majority = counts.most_common(1)[0][1]
        agreement[review_item_id] = round(ratio(majority, len(decisions)), 4)
    return agreement


def adjudicator_agreement(
    aggregated: list[SyntheticAggregatedReview],
    finals: list[SyntheticFinalAdjudication],
) -> float:
    if not aggregated or not finals:
        return 0.0
    final_by_item = {final.review_item_id: final for final in finals}
    comparable = [
        aggregate
        for aggregate in aggregated
        if aggregate.review_item_id in final_by_item
        and aggregate.aggregate_decision != SyntheticDecision.NEEDS_REVIEW
    ]
    if not comparable:
        return 0.0
    matches = sum(
        1
        for aggregate in comparable
        if final_by_item[aggregate.review_item_id].final_decision == aggregate.aggregate_decision
    )
    return round(ratio(matches, len(comparable)), 4)


def gold_status_counts(
    *,
    finals: list[SyntheticFinalAdjudication],
    candidates: list[SyntheticGoldCandidate],
) -> dict[str, int]:
    status_by_item = {
        final.review_item_id: str(final.gold_status)
        for final in finals
        if final.gold_status is not None
    }
    for candidate in candidates:
        status_by_item.setdefault(candidate.review_item_id, str(candidate.status))
    return dict(sorted(Counter(status_by_item.values()).items()))


def split_candidates(
    candidates: list[SyntheticGoldCandidate],
) -> tuple[
    list[SyntheticGoldCandidate],
    list[SyntheticGoldCandidate],
    list[SyntheticGoldCandidate],
]:
    high: list[SyntheticGoldCandidate] = []
    medium: list[SyntheticGoldCandidate] = []
    rejected: list[SyntheticGoldCandidate] = []
    for candidate in candidates:
        if candidate.status == SyntheticGoldStatus.HIGH_CONFIDENCE:
            high.append(candidate)
        elif candidate.status == SyntheticGoldStatus.MEDIUM_CONFIDENCE:
            medium.append(candidate)
        else:
            rejected.append(candidate)
    return high, medium, rejected


def write_jsonl(path: Path, records: list[BaseModel]) -> None:
    path.write_text(
        "\n".join(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False) for record in records
        )
        + ("\n" if records else ""),
        encoding="utf-8",
    )


def reliability_markdown(metrics: SyntheticReliabilityMetrics) -> str:
    return (
        "# Synthetic Reliability Report\n\n"
        f"- run_id: `{metrics.run_id}`\n"
        f"- review_items: {metrics.total_review_items}\n"
        f"- reviewer_outputs: {metrics.reviewer_output_count}\n"
        f"- inter_reviewer_agreement: {metrics.inter_reviewer_agreement:.4f}\n"
        f"- adjudicator_agreement: {metrics.adjudicator_agreement:.4f}\n"
        f"- average_reviewer_confidence: {metrics.average_reviewer_confidence:.4f}\n"
        f"- average_final_reliability: {metrics.average_final_reliability:.4f}\n"
        f"- high_confidence_count: {metrics.high_confidence_count}\n"
        f"- medium_confidence_count: {metrics.medium_confidence_count}\n"
        f"- rejected_count: {metrics.rejected_count}\n"
        f"- needs_human_review_count: {metrics.needs_human_review_count}\n"
        f"- regression_eligible_count: {metrics.regression_eligible_count}\n"
        f"- regression_eligible_rate: {metrics.regression_eligible_rate:.4f}\n"
        f"- taxonomy_version_effective: `{metrics.taxonomy_version_effective}`\n"
        f"- prompt_version_effective: `{metrics.prompt_version_effective}`\n"
        f"- validator_version_effective: `{metrics.validator_version_effective}`\n"
    )


def average(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def count_values(values: Any) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))
