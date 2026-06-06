"""Synthetic OpenAI committee review workflow."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from narrative_dna.llm_client import LLMCallResult, OpenAIStructuredClient, load_llm_config
from narrative_dna.models import (
    SyntheticAggregatedReview,
    SyntheticFinalAdjudication,
    SyntheticGoldCandidate,
    SyntheticReviewerOutput,
    SyntheticReviewItem,
    SyntheticReviewReport,
)
from narrative_dna.review_aggregator import (
    aggregate_reviewer_outputs,
    candidate_from_final_adjudication,
    conservative_final_adjudication,
)

DEFAULT_TAXONOMY_VERSION = "v1_0"
DEFAULT_PROMPT_VERSION = "v1_0"
DEFAULT_VALIDATOR_VERSION = "v1_0"
DEFAULT_LLM_CONFIG_PATH = Path("configs/llm_config.json")
DEFAULT_REVIEWER_PROMPT_PATH = Path("prompts/synthetic_reviewer.md")
DEFAULT_AGGREGATOR_PROMPT_PATH = Path("prompts/synthetic_aggregator.md")
DEFAULT_FINAL_ADJUDICATOR_PROMPT_PATH = Path("prompts/synthetic_adjudicator.md")
DEFAULT_REVIEWER_PROFILES = (
    "divergent_reviewer_a",
    "divergent_reviewer_b",
    "taxonomy_strict_reviewer",
)


class SyntheticCommitteeReviewer:
    """Run a synthetic reviewer committee over review_items.jsonl."""

    def __init__(
        self,
        *,
        llm_client: Any | None = None,
        config_path: str | Path = DEFAULT_LLM_CONFIG_PATH,
        reviewer_prompt_path: str | Path = DEFAULT_REVIEWER_PROMPT_PATH,
        aggregator_prompt_path: str | Path = DEFAULT_AGGREGATOR_PROMPT_PATH,
        final_adjudicator_prompt_path: str | Path = DEFAULT_FINAL_ADJUDICATOR_PROMPT_PATH,
        reviewer_profiles: list[str] | None = None,
        aggregator_profile: str = "synthetic_aggregator",
        final_adjudicator_profile: str = "synthetic_final_adjudicator",
        taxonomy_version: str = DEFAULT_TAXONOMY_VERSION,
        prompt_version: str = DEFAULT_PROMPT_VERSION,
        validator_version: str = DEFAULT_VALIDATOR_VERSION,
        dry_run: bool = False,
        use_cache: bool | None = None,
    ) -> None:
        self.config_path = Path(config_path)
        self.llm_config = load_llm_config(self.config_path)
        self.llm_client = llm_client or OpenAIStructuredClient(config_path=self.config_path)
        self.reviewer_profiles = reviewer_profiles or reviewer_profile_names(self.llm_config)
        self.aggregator_profile = aggregator_profile
        self.final_adjudicator_profile = final_adjudicator_profile
        self.taxonomy_version = taxonomy_version
        self.prompt_version = prompt_version
        self.validator_version = validator_version
        self.dry_run = dry_run
        self.use_cache = use_cache
        self.reviewer_prompt = read_text(reviewer_prompt_path)
        self.aggregator_prompt = read_text(aggregator_prompt_path)
        self.final_adjudicator_prompt = read_text(final_adjudicator_prompt_path)
        self.failures: list[dict[str, Any]] = []

    def run(
        self,
        *,
        run_id: str,
        outputs_dir: str | Path = "outputs",
        max_items: int | None = None,
    ) -> tuple[
        list[SyntheticReviewerOutput],
        list[SyntheticAggregatedReview],
        list[SyntheticFinalAdjudication],
        list[SyntheticGoldCandidate],
        SyntheticReviewReport,
    ]:
        run_dir = Path(outputs_dir) / run_id
        items = load_review_items(run_dir)
        if max_items is not None:
            items = items[: max(0, max_items)]

        reviewer_outputs: list[SyntheticReviewerOutput] = []
        grouped_outputs: dict[str, list[SyntheticReviewerOutput]] = defaultdict(list)

        for item in items:
            for reviewer_id in self.reviewer_profiles:
                result = self._request_reviewer_output(
                    run_id=run_id,
                    item=item,
                    reviewer_id=reviewer_id,
                )
                if result is None:
                    continue
                reviewer_outputs.append(result)
                grouped_outputs[item.review_item_id].append(result)

        aggregated: list[SyntheticAggregatedReview] = []
        final_adjudications: list[SyntheticFinalAdjudication] = []
        candidates: list[SyntheticGoldCandidate] = []
        items_by_id = {item.review_item_id: item for item in items}

        for review_item_id, decisions in grouped_outputs.items():
            item = items_by_id[review_item_id]
            aggregate = self._request_aggregated_review(
                run_id=run_id,
                item=item,
                decisions=decisions,
            )
            aggregated.append(aggregate)
            final = self._request_final_adjudication(item=item, aggregate=aggregate)
            final_adjudications.append(final)
            candidate = candidate_from_final_adjudication(final)
            if candidate is not None:
                candidates.append(candidate)

        report = build_report(
            run_id=run_id,
            item_count=len(items),
            reviewer_profile_count=len(self.reviewer_profiles),
            reviewer_outputs=reviewer_outputs,
            failures=self.failures,
            aggregated=aggregated,
            finals=final_adjudications,
            candidates=candidates,
        )
        return reviewer_outputs, aggregated, final_adjudications, candidates, report

    def _request_reviewer_output(
        self,
        *,
        run_id: str,
        item: SyntheticReviewItem,
        reviewer_id: str,
    ) -> SyntheticReviewerOutput | None:
        result = self.llm_client.request_structured(
            profile_name=reviewer_id,
            input_payload=reviewer_payload(run_id=run_id, item=item, reviewer_id=reviewer_id),
            response_model=SyntheticReviewerOutput,
            taxonomy_version=item.taxonomy_version_effective,
            prompt_version=item.prompt_version_effective,
            validator_version=item.validator_version_effective,
            system_prompt=self.reviewer_prompt,
            dry_run=self.dry_run,
            use_cache=self.use_cache,
        )
        if not result.ok or not result.parsed:
            self.failures.append(failure_record(run_id, item.review_item_id, reviewer_id, result))
            return None
        try:
            output = SyntheticReviewerOutput.model_validate(result.parsed)
            return normalize_reviewer_output(
                output,
                run_id=run_id,
                item=item,
                reviewer_id=reviewer_id,
            )
        except ValueError as exc:
            self.failures.append(
                failure_record(
                    run_id,
                    item.review_item_id,
                    reviewer_id,
                    result,
                    error_type="reviewer_output_mismatch",
                    error=str(exc),
                )
            )
            return None

    def _request_aggregated_review(
        self,
        *,
        run_id: str,
        item: SyntheticReviewItem,
        decisions: list[SyntheticReviewerOutput],
    ) -> SyntheticAggregatedReview:
        fallback = aggregate_reviewer_outputs(
            run_id=run_id,
            review_item_id=item.review_item_id,
            decisions=decisions,
            taxonomy_version=item.taxonomy_version_effective,
            prompt_version=item.prompt_version_effective,
            validator_version=item.validator_version_effective,
        )
        result = self.llm_client.request_structured(
            profile_name=self.aggregator_profile,
            input_payload=aggregator_payload(item=item, decisions=decisions, fallback=fallback),
            response_model=SyntheticAggregatedReview,
            taxonomy_version=item.taxonomy_version_effective,
            prompt_version=item.prompt_version_effective,
            validator_version=item.validator_version_effective,
            system_prompt=self.aggregator_prompt,
            dry_run=self.dry_run,
            use_cache=self.use_cache,
        )
        if not result.ok or not result.parsed:
            self.failures.append(
                failure_record(run_id, item.review_item_id, self.aggregator_profile, result)
            )
            return fallback
        try:
            aggregate = SyntheticAggregatedReview.model_validate(result.parsed)
            return normalize_aggregate(aggregate, run_id=run_id, item=item, decisions=decisions)
        except ValueError as exc:
            self.failures.append(
                failure_record(
                    run_id,
                    item.review_item_id,
                    self.aggregator_profile,
                    result,
                    error_type="aggregated_output_mismatch",
                    error=str(exc),
                )
            )
            return fallback

    def _request_final_adjudication(
        self,
        *,
        item: SyntheticReviewItem,
        aggregate: SyntheticAggregatedReview,
    ) -> SyntheticFinalAdjudication:
        result = self.llm_client.request_structured(
            profile_name=self.final_adjudicator_profile,
            input_payload=final_adjudicator_payload(item=item, aggregate=aggregate),
            response_model=SyntheticFinalAdjudication,
            taxonomy_version=item.taxonomy_version_effective,
            prompt_version=item.prompt_version_effective,
            validator_version=item.validator_version_effective,
            system_prompt=self.final_adjudicator_prompt,
            dry_run=self.dry_run,
            use_cache=self.use_cache,
        )
        if not result.ok or not result.parsed:
            self.failures.append(
                failure_record(
                    aggregate.run_id,
                    item.review_item_id,
                    self.final_adjudicator_profile,
                    result,
                )
            )
            return conservative_final_adjudication(aggregate=aggregate)
        try:
            final = SyntheticFinalAdjudication.model_validate(result.parsed)
            return normalize_final_adjudication(final, item=item, aggregate=aggregate)
        except ValueError as exc:
            self.failures.append(
                failure_record(
                    aggregate.run_id,
                    item.review_item_id,
                    self.final_adjudicator_profile,
                    result,
                    error_type="final_adjudication_mismatch",
                    error=str(exc),
                )
            )
            return conservative_final_adjudication(aggregate=aggregate)


def run_synthetic_review(
    *,
    run_id: str,
    outputs_dir: str | Path = "outputs",
    reviewer: SyntheticCommitteeReviewer | None = None,
    max_items: int | None = None,
) -> tuple[
    list[SyntheticReviewerOutput],
    list[SyntheticAggregatedReview],
    list[SyntheticFinalAdjudication],
    list[SyntheticGoldCandidate],
    SyntheticReviewReport,
]:
    return (reviewer or SyntheticCommitteeReviewer()).run(
        run_id=run_id,
        outputs_dir=outputs_dir,
        max_items=max_items,
    )


def run_and_write_synthetic_review(
    *,
    run_id: str,
    outputs_dir: str | Path = "outputs",
    reviewer: SyntheticCommitteeReviewer | None = None,
    max_items: int | None = None,
) -> SyntheticReviewReport:
    reviews, aggregated, finals, candidates, report = run_synthetic_review(
        run_id=run_id,
        outputs_dir=outputs_dir,
        reviewer=reviewer,
        max_items=max_items,
    )
    return write_synthetic_review_outputs(
        run_id=run_id,
        outputs_dir=outputs_dir,
        reviewer_outputs=reviews,
        aggregated=aggregated,
        finals=finals,
        candidates=candidates,
        report=report,
    )


def write_synthetic_review_outputs(
    *,
    run_id: str,
    outputs_dir: str | Path,
    reviewer_outputs: list[SyntheticReviewerOutput],
    aggregated: list[SyntheticAggregatedReview],
    finals: list[SyntheticFinalAdjudication],
    candidates: list[SyntheticGoldCandidate],
    report: SyntheticReviewReport,
) -> SyntheticReviewReport:
    run_dir = Path(outputs_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "synthetic_reviews": run_dir / "synthetic_reviews.jsonl",
        "synthetic_review_aggregated": run_dir / "synthetic_review_aggregated.jsonl",
        "synthetic_final_adjudications": run_dir / "synthetic_final_adjudications.jsonl",
        "synthetic_gold_candidates": run_dir / "synthetic_gold_candidates.jsonl",
        "synthetic_review_report": run_dir / "synthetic_review_report.json",
        "synthetic_review_report_md": run_dir / "synthetic_review_report.md",
    }
    write_jsonl(paths["synthetic_reviews"], reviewer_outputs)
    write_jsonl(paths["synthetic_review_aggregated"], aggregated)
    write_jsonl(paths["synthetic_final_adjudications"], finals)
    write_jsonl(paths["synthetic_gold_candidates"], candidates)
    report_payload = report.model_dump(mode="json")
    report_payload["outputs"] = {key: str(path) for key, path in paths.items()}
    report = SyntheticReviewReport.model_validate(report_payload)
    paths["synthetic_review_report"].write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    paths["synthetic_review_report_md"].write_text(report_markdown(report), encoding="utf-8")
    return report


def load_review_items(run_dir: str | Path) -> list[SyntheticReviewItem]:
    path = Path(run_dir) / "review" / "review_items.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"Missing review items JSONL: {path}")
    return [
        SyntheticReviewItem.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def reviewer_profile_names(config: dict[str, Any]) -> list[str]:
    reviewers = config.get("synthetic_reviewers")
    if isinstance(reviewers, list):
        names = [
            str(reviewer.get("name"))
            for reviewer in reviewers
            if isinstance(reviewer, dict) and reviewer.get("name")
        ]
        if names:
            return names
    return list(DEFAULT_REVIEWER_PROFILES)


def reviewer_payload(
    *,
    run_id: str,
    item: SyntheticReviewItem,
    reviewer_id: str,
) -> dict[str, Any]:
    return {
        "task": "synthetic_review",
        "run_id": run_id,
        "reviewer_id": reviewer_id,
        "required_review_item_id": item.review_item_id,
        "review_item": item.model_dump(mode="json"),
        "rules": {
            "do_not_claim_human_gold": True,
            "compact_notation_is_derived": True,
            "prefer_needs_review_when_two_readings_remain_plausible": True,
        },
    }


def aggregator_payload(
    *,
    item: SyntheticReviewItem,
    decisions: list[SyntheticReviewerOutput],
    fallback: SyntheticAggregatedReview,
) -> dict[str, Any]:
    return {
        "task": "synthetic_review_aggregation",
        "review_item": item.model_dump(mode="json"),
        "reviewer_outputs": [decision.model_dump(mode="json") for decision in decisions],
        "deterministic_conservative_baseline": fallback.model_dump(mode="json"),
    }


def final_adjudicator_payload(
    *,
    item: SyntheticReviewItem,
    aggregate: SyntheticAggregatedReview,
) -> dict[str, Any]:
    return {
        "task": "synthetic_final_adjudication",
        "review_item": item.model_dump(mode="json"),
        "aggregated_review": aggregate.model_dump(mode="json"),
        "promotion_policy": {
            "high_confidence_requires_strong_agreement": True,
            "medium_confidence_is_not_regression_gold": True,
            "reject_or_keep_review_when_uncertain": True,
        },
    }


def normalize_reviewer_output(
    output: SyntheticReviewerOutput,
    *,
    run_id: str,
    item: SyntheticReviewItem,
    reviewer_id: str,
) -> SyntheticReviewerOutput:
    if output.review_item_id != item.review_item_id:
        raise ValueError("reviewer output review_item_id does not match the input item")
    if output.reviewer_id != reviewer_id:
        raise ValueError("reviewer output reviewer_id does not match the requested profile")
    payload = output.model_dump(mode="json")
    payload.update(version_payload(run_id=run_id, item=item))
    return SyntheticReviewerOutput.model_validate(payload)


def normalize_aggregate(
    aggregate: SyntheticAggregatedReview,
    *,
    run_id: str,
    item: SyntheticReviewItem,
    decisions: list[SyntheticReviewerOutput],
) -> SyntheticAggregatedReview:
    if aggregate.review_item_id != item.review_item_id:
        raise ValueError("aggregated review_item_id does not match the input item")
    decision_ids = [decision.reviewer_id for decision in aggregate.decisions]
    expected_ids = [decision.reviewer_id for decision in decisions]
    if sorted(decision_ids) != sorted(expected_ids):
        raise ValueError("aggregated decisions do not match reviewer outputs")
    payload = aggregate.model_dump(mode="json")
    payload.update(version_payload(run_id=run_id, item=item))
    return SyntheticAggregatedReview.model_validate(payload)


def normalize_final_adjudication(
    final: SyntheticFinalAdjudication,
    *,
    item: SyntheticReviewItem,
    aggregate: SyntheticAggregatedReview,
) -> SyntheticFinalAdjudication:
    if final.review_item_id != item.review_item_id:
        raise ValueError("final adjudication review_item_id does not match the input item")
    payload = final.model_dump(mode="json")
    payload.update(version_payload(run_id=aggregate.run_id, item=item))
    return SyntheticFinalAdjudication.model_validate(payload)


def build_report(
    *,
    run_id: str,
    item_count: int,
    reviewer_profile_count: int,
    reviewer_outputs: list[SyntheticReviewerOutput],
    failures: list[dict[str, Any]],
    aggregated: list[SyntheticAggregatedReview],
    finals: list[SyntheticFinalAdjudication],
    candidates: list[SyntheticGoldCandidate],
) -> SyntheticReviewReport:
    decision_counts = Counter(str(output.decision) for output in reviewer_outputs)
    return SyntheticReviewReport(
        run_id=run_id,
        total_review_items=item_count,
        reviewer_profile_count=reviewer_profile_count,
        reviewer_output_count=len(reviewer_outputs),
        reviewer_failure_count=len(failures),
        aggregated_count=len(aggregated),
        final_adjudication_count=len(finals),
        synthetic_gold_candidate_count=len(candidates),
        decisions_by_type=dict(sorted(decision_counts.items())),
        outputs={},
        taxonomy_version_effective=DEFAULT_TAXONOMY_VERSION,
        prompt_version_effective=DEFAULT_PROMPT_VERSION,
        validator_version_effective=DEFAULT_VALIDATOR_VERSION,
    )


def write_jsonl(path: Path, records: list[Any]) -> None:
    path.write_text(
        "\n".join(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False) for record in records
        )
        + ("\n" if records else ""),
        encoding="utf-8",
    )


def report_markdown(report: SyntheticReviewReport) -> str:
    decisions = ", ".join(
        f"{decision}: {count}" for decision, count in report.decisions_by_type.items()
    )
    return (
        f"# Synthetic Review Report\n\n"
        f"- run_id: `{report.run_id}`\n"
        f"- review_items: {report.total_review_items}\n"
        f"- reviewer_outputs: {report.reviewer_output_count}\n"
        f"- reviewer_failures: {report.reviewer_failure_count}\n"
        f"- aggregated: {report.aggregated_count}\n"
        f"- final_adjudications: {report.final_adjudication_count}\n"
        f"- synthetic_gold_candidates: {report.synthetic_gold_candidate_count}\n"
        f"- reviewer_decisions: {decisions or 'none'}\n"
        f"- taxonomy_version_effective: `{report.taxonomy_version_effective}`\n"
        f"- prompt_version_effective: `{report.prompt_version_effective}`\n"
        f"- validator_version_effective: `{report.validator_version_effective}`\n"
    )


def failure_record(
    run_id: str,
    review_item_id: str,
    profile_name: str,
    result: LLMCallResult,
    *,
    error_type: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "review_item_id": review_item_id,
        "profile_name": profile_name,
        "ok": result.ok,
        "cache_key": result.cache_key,
        "cache_hit": result.cache_hit,
        "dry_run": result.dry_run,
        "attempts": result.attempts,
        "error_type": error_type or result.error_type,
        "error": error or result.error,
        "taxonomy_version_effective": DEFAULT_TAXONOMY_VERSION,
        "prompt_version_effective": DEFAULT_PROMPT_VERSION,
        "validator_version_effective": DEFAULT_VALIDATOR_VERSION,
    }


def version_payload(*, run_id: str, item: SyntheticReviewItem) -> dict[str, str]:
    return {
        "run_id": run_id,
        "taxonomy_version_effective": item.taxonomy_version_effective,
        "prompt_version_effective": item.prompt_version_effective,
        "validator_version_effective": item.validator_version_effective,
    }


def read_text(path: str | Path) -> str:
    source = Path(path)
    return source.read_text(encoding="utf-8") if source.exists() else ""
