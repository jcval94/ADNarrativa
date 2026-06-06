"""Conservative synthetic review aggregation helpers."""

from __future__ import annotations

import hashlib
from collections import Counter

from narrative_dna.models import (
    NarrativeUnit,
    SyntheticAggregatedReview,
    SyntheticDecision,
    SyntheticFinalAdjudication,
    SyntheticGoldCandidate,
    SyntheticReviewerOutput,
)
from narrative_dna.validators import normalize_and_validate_unit

DEFAULT_TAXONOMY_VERSION = "v1_0"
DEFAULT_PROMPT_VERSION = "v1_0"
DEFAULT_VALIDATOR_VERSION = "v1_0"


def aggregate_reviewer_outputs(
    *,
    run_id: str,
    review_item_id: str,
    decisions: list[SyntheticReviewerOutput],
    taxonomy_version: str = DEFAULT_TAXONOMY_VERSION,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    validator_version: str = DEFAULT_VALIDATOR_VERSION,
) -> SyntheticAggregatedReview:
    """Aggregate reviewer decisions conservatively without inventing labels."""

    if not decisions:
        raise ValueError("at least one reviewer decision is required")
    counts = Counter(str(decision.decision) for decision in decisions)
    top_decision, top_count = counts.most_common(1)[0]
    average_confidence = sum(decision.confidence for decision in decisions) / len(decisions)
    agreement = top_count / len(decisions)

    if agreement < 0.67 or average_confidence < 0.75:
        aggregate_decision = SyntheticDecision.NEEDS_REVIEW
        confidence = min(agreement, average_confidence)
        rationale = "Reviewer agreement or confidence was insufficient for a committee decision."
    else:
        aggregate_decision = SyntheticDecision(top_decision)
        confidence = min(agreement, average_confidence)
        rationale = (
            f"{top_count}/{len(decisions)} reviewers selected {top_decision} "
            f"with average confidence {average_confidence:.2f}."
        )

    return SyntheticAggregatedReview(
        run_id=run_id,
        review_item_id=review_item_id,
        decisions=decisions,
        aggregate_decision=aggregate_decision,
        confidence=round(confidence, 4),
        rationale=rationale,
        needs_final_adjudication=aggregate_decision != SyntheticDecision.NEEDS_REVIEW,
        taxonomy_version_effective=taxonomy_version,
        prompt_version_effective=prompt_version,
        validator_version_effective=validator_version,
    )


def conservative_final_adjudication(
    *,
    aggregate: SyntheticAggregatedReview,
    rationale: str = "Final adjudicator unavailable; kept item out of synthetic gold.",
) -> SyntheticFinalAdjudication:
    """Fallback final adjudication that refuses promotion."""

    return SyntheticFinalAdjudication(
        run_id=aggregate.run_id,
        review_item_id=aggregate.review_item_id,
        final_decision=SyntheticDecision.NEEDS_REVIEW,
        gold_status=None,
        selected_unit=None,
        reliability_score=min(aggregate.confidence, 0.5),
        rationale=rationale,
        validator_flags=[],
        needs_human_review=True,
        taxonomy_version_effective=aggregate.taxonomy_version_effective,
        prompt_version_effective=aggregate.prompt_version_effective,
        validator_version_effective=aggregate.validator_version_effective,
    )


def candidate_from_final_adjudication(
    final: SyntheticFinalAdjudication,
) -> SyntheticGoldCandidate | None:
    """Convert a conservative final adjudication into a synthetic gold candidate."""

    if final.final_decision not in {SyntheticDecision.ACCEPT, SyntheticDecision.REVISE}:
        return None
    if final.gold_status is None or final.selected_unit is None:
        return None
    if final.needs_human_review or final.reliability_score < 0.8:
        return None
    unit = normalize_and_validate_unit(final.selected_unit)
    return SyntheticGoldCandidate(
        run_id=final.run_id,
        candidate_id=_candidate_id(final, unit),
        review_item_id=final.review_item_id,
        status=final.gold_status,
        unit=unit,
        reliability_score=final.reliability_score,
        promotion_notes=final.rationale,
        taxonomy_version_effective=final.taxonomy_version_effective,
        prompt_version_effective=final.prompt_version_effective,
        validator_version_effective=final.validator_version_effective,
    )


def _candidate_id(final: SyntheticFinalAdjudication, unit: NarrativeUnit) -> str:
    text = f"{final.run_id}::{final.review_item_id}::{unit.unit_id}::{unit.final_notation}"
    return f"synthetic_candidate_{hashlib.sha256(text.encode()).hexdigest()[:16]}"
