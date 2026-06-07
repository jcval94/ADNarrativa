"""Evaluation and audit metric entry points for JSON-first runs."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from narrative_dna.models import (
    AuditReport,
    EvaluationMetrics,
    GoldRecord,
    GoldType,
    NarrativeDocument,
    NarrativeUnit,
    SimilarityConflict,
    SyntheticGoldCandidate,
    SyntheticGoldStatus,
    ValidatorFlag,
    ValidatorSeverity,
    ValidatorSummary,
)
from narrative_dna.similarity_auditor import load_run_documents

DEFAULT_TAXONOMY_VERSION = "v1_0"
DEFAULT_PROMPT_VERSION = "v1_0"
DEFAULT_VALIDATOR_VERSION = "v1_0"


def evaluate_run(
    *,
    run_id: str,
    gold_path: str | Path,
    outputs_dir: str | Path = "outputs",
) -> tuple[EvaluationMetrics, dict[str, Any], dict[str, Any], AuditReport]:
    """Evaluate unit annotations against an allowed JSONL gold source."""

    run_dir = Path(outputs_dir) / run_id
    documents = load_run_documents(run_dir)
    predictions = {unit.unit_id: unit for document in documents for unit in document.units}
    gold_units = load_gold_units(Path(gold_path))
    metrics = score_units(
        run_id=run_id,
        gold_path=Path(gold_path),
        predictions=predictions,
        gold_units=gold_units,
        run_dir=run_dir,
    )
    label_metrics = build_label_metrics(predictions=predictions, gold_units=gold_units)
    confusion_report = build_confusion_groups_report(predictions=predictions, gold_units=gold_units)
    audit_report = build_audit_report(run_id=run_id, run_dir=run_dir, documents=documents)
    return metrics, label_metrics, confusion_report, audit_report


def write_evaluation_outputs(
    *,
    run_id: str,
    gold_path: str | Path,
    outputs_dir: str | Path = "outputs",
) -> EvaluationMetrics:
    """Evaluate and write JSON/Markdown reports as derived outputs."""

    run_dir = Path(outputs_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    metrics, label_metrics, confusion_report, audit_report = evaluate_run(
        run_id=run_id,
        gold_path=gold_path,
        outputs_dir=outputs_dir,
    )
    paths = {
        "evaluation_metrics": run_dir / "evaluation_metrics.json",
        "label_metrics": run_dir / "label_metrics.json",
        "confusion_groups_report": run_dir / "confusion_groups_report.json",
        "audit_report": run_dir / "audit_report.json",
        "audit_report_md": run_dir / "audit_report.md",
    }
    payload = metrics.model_dump(mode="json")
    payload["outputs"] = {key: str(path) for key, path in paths.items()}
    metrics = EvaluationMetrics.model_validate(payload)

    paths["evaluation_metrics"].write_text(
        json.dumps(metrics.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    paths["label_metrics"].write_text(
        json.dumps(label_metrics, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    paths["confusion_groups_report"].write_text(
        json.dumps(confusion_report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    paths["audit_report"].write_text(
        json.dumps(
            audit_report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    paths["audit_report_md"].write_text(audit_markdown(metrics, audit_report), encoding="utf-8")
    return metrics


def score_units(
    *,
    run_id: str,
    gold_path: Path,
    predictions: dict[str, NarrativeUnit],
    gold_units: list[NarrativeUnit],
    run_dir: Path,
) -> EvaluationMetrics:
    matched_pairs = [
        (predictions[gold.unit_id], gold) for gold in gold_units if gold.unit_id in predictions
    ]
    gold_ids = {gold.unit_id for gold in gold_units}
    predicted_ids = set(predictions)
    exact_matches = sum(
        1 for predicted, gold in matched_pairs if function_set(predicted) == function_set(gold)
    )
    primary_matches = sum(
        1
        for predicted, gold in matched_pairs
        if str(predicted.primary_function) == str(gold.primary_function)
    )
    emotion_matches = sum(
        1
        for predicted, gold in matched_pairs
        if str(predicted.emotion_expressed) == str(gold.emotion_expressed)
    )
    stance_matches = sum(
        1 for predicted, gold in matched_pairs if str(predicted.stance) == str(gold.stance)
    )
    certainty_matches = sum(
        1 for predicted, gold in matched_pairs if str(predicted.certainty) == str(gold.certainty)
    )
    emotion_intensity_errors = [
        abs(predicted.emotion_intensity - gold.emotion_intensity)
        for predicted, gold in matched_pairs
    ]
    all_predicted_units = list(predictions.values())
    all_flags = [flag for unit in all_predicted_units for flag in unit.validator_flags]
    similarity_conflicts = load_similarity_conflicts(run_dir)
    micro_precision, micro_recall, micro_f1 = micro_scores(matched_pairs)
    label_metrics = per_label_metrics(predictions=predictions, gold_units=gold_units)
    macro_f1 = average([values["f1"] for values in label_metrics.values()])
    matched_count = len(matched_pairs)
    regression_passes = sum(
        1
        for predicted, gold in matched_pairs
        if predicted.final_notation == gold.final_notation and not predicted.needs_review
    )

    return EvaluationMetrics(
        run_id=run_id,
        gold_path=str(gold_path),
        total_gold_units=len(gold_units),
        total_predicted_units=len(predictions),
        matched_units=matched_count,
        missing_predictions=len(gold_ids - predicted_ids),
        unexpected_predictions=len(predicted_ids - gold_ids),
        functions_exact_match=ratio(exact_matches, matched_count),
        primary_function_accuracy=ratio(primary_matches, matched_count),
        multilabel_jaccard=average(
            [
                jaccard(function_set(predicted), function_set(gold))
                for predicted, gold in matched_pairs
            ]
        ),
        micro_f1=micro_f1,
        macro_f1=macro_f1,
        emotion_expressed_accuracy=ratio(emotion_matches, matched_count),
        emotion_intensity_mae=average(emotion_intensity_errors),
        stance_accuracy=ratio(stance_matches, matched_count),
        certainty_accuracy=ratio(certainty_matches, matched_count),
        overlabeling_rate=ratio(
            sum(1 for unit in all_predicted_units if len(unit.functions) > 5),
            len(all_predicted_units),
        ),
        n_rate=ratio(
            sum(1 for unit in all_predicted_units if "N" in function_set(unit)),
            len(all_predicted_units),
        ),
        validator_violation_rate=ratio(len(all_flags), len(all_predicted_units)),
        needs_review_rate=ratio(
            sum(1 for unit in all_predicted_units if unit.needs_review),
            len(all_predicted_units),
        ),
        similarity_conflict_rate=ratio(len(similarity_conflicts), max(1, len(all_predicted_units))),
        relation_precision_recall_f1=0.0,
        regression_pass_rate=ratio(regression_passes, matched_count),
        outputs={},
        taxonomy_version_effective=DEFAULT_TAXONOMY_VERSION,
        prompt_version_effective=DEFAULT_PROMPT_VERSION,
        validator_version_effective=DEFAULT_VALIDATOR_VERSION,
    )


def load_gold_units(path: Path) -> list[NarrativeUnit]:
    if not path.exists():
        raise FileNotFoundError(f"Missing gold JSONL file: {path}")
    units: list[NarrativeUnit] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        units.append(gold_unit_from_payload(payload, path=path, line_number=line_number))
    return units


def gold_unit_from_payload(
    payload: dict[str, Any], *, path: Path, line_number: int
) -> NarrativeUnit:
    if "gold_type" in payload:
        record = GoldRecord.model_validate(payload)
        if record.gold_type not in {
            GoldType.HUMAN_GOLD,
            GoldType.SYNTHETIC_HIGH_CONFIDENCE,
        }:
            raise ValueError(f"Gold record {record.gold_id} is not allowed for evaluation.")
        return record.unit
    if "status" in payload and "unit" in payload:
        candidate = SyntheticGoldCandidate.model_validate(payload)
        if candidate.status != SyntheticGoldStatus.HIGH_CONFIDENCE:
            raise ValueError(
                f"Synthetic candidate {candidate.candidate_id} is not high-confidence gold."
            )
        return candidate.unit
    if "unit" in payload:
        return NarrativeUnit.model_validate(payload["unit"])
    try:
        return NarrativeUnit.model_validate(payload)
    except Exception as exc:
        raise ValueError(f"Invalid gold record at {path}:{line_number}") from exc


def build_label_metrics(
    *,
    predictions: dict[str, NarrativeUnit],
    gold_units: list[NarrativeUnit],
) -> dict[str, Any]:
    metrics = per_label_metrics(predictions=predictions, gold_units=gold_units)
    return {
        "labels": metrics,
        "taxonomy_version_effective": DEFAULT_TAXONOMY_VERSION,
        "prompt_version_effective": DEFAULT_PROMPT_VERSION,
        "validator_version_effective": DEFAULT_VALIDATOR_VERSION,
    }


def per_label_metrics(
    *,
    predictions: dict[str, NarrativeUnit],
    gold_units: list[NarrativeUnit],
) -> dict[str, dict[str, float | int]]:
    labels = sorted(
        {
            function
            for unit in [*predictions.values(), *gold_units]
            for function in function_set(unit)
        }
    )
    result: dict[str, dict[str, float | int]] = {}
    for label in labels:
        tp = fp = fn = 0
        for gold in gold_units:
            predicted = predictions.get(gold.unit_id)
            predicted_has = bool(predicted and label in function_set(predicted))
            gold_has = label in function_set(gold)
            if predicted_has and gold_has:
                tp += 1
            elif predicted_has and not gold_has:
                fp += 1
            elif gold_has and not predicted_has:
                fn += 1
        precision, recall, f1 = prf(tp, fp, fn)
        result[label] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    return result


def build_confusion_groups_report(
    *,
    predictions: dict[str, NarrativeUnit],
    gold_units: list[NarrativeUnit],
) -> dict[str, Any]:
    confusion_counts: Counter[str] = Counter()
    examples: list[dict[str, str]] = []
    for gold in gold_units:
        predicted = predictions.get(gold.unit_id)
        if predicted is None:
            continue
        if str(predicted.primary_function) == str(gold.primary_function):
            continue
        key = f"{gold.primary_function}->{predicted.primary_function}"
        confusion_counts[key] += 1
        if len(examples) < 25:
            examples.append(
                {
                    "unit_id": gold.unit_id,
                    "gold_primary_function": str(gold.primary_function),
                    "predicted_primary_function": str(predicted.primary_function),
                    "text": predicted.text,
                }
            )
    return {
        "primary_function_confusions": dict(sorted(confusion_counts.items())),
        "examples": examples,
        "taxonomy_version_effective": DEFAULT_TAXONOMY_VERSION,
        "prompt_version_effective": DEFAULT_PROMPT_VERSION,
        "validator_version_effective": DEFAULT_VALIDATOR_VERSION,
    }


def build_audit_report(
    *,
    run_id: str,
    run_dir: Path,
    documents: list[NarrativeDocument],
) -> AuditReport:
    units = [unit for document in documents for unit in document.units]
    flags = [flag for unit in units for flag in unit.validator_flags]
    conflicts = load_similarity_conflicts(run_dir)
    summary = ValidatorSummary(
        run_id=run_id,
        validator_version=DEFAULT_VALIDATOR_VERSION,
        total_units=len(units),
        total_flags=len(flags),
        errors=count_severity(flags, ValidatorSeverity.ERROR),
        warnings=count_severity(flags, ValidatorSeverity.WARNING),
        infos=count_severity(flags, ValidatorSeverity.INFO),
        flags_by_rule=dict(sorted(Counter(flag.rule_id for flag in flags).items())),
    )
    return AuditReport(
        run_id=run_id,
        summary=summary,
        validator_flags=flags,
        similarity_conflicts=conflicts,
        cluster_instabilities=[],
        taxonomy_version_effective=DEFAULT_TAXONOMY_VERSION,
        prompt_version_effective=DEFAULT_PROMPT_VERSION,
        validator_version_effective=DEFAULT_VALIDATOR_VERSION,
    )


def load_similarity_conflicts(run_dir: Path) -> list[SimilarityConflict]:
    path = run_dir / "similarity_conflicts.jsonl"
    if not path.exists():
        return []
    return [
        SimilarityConflict.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def audit_markdown(metrics: EvaluationMetrics, report: AuditReport) -> str:
    return (
        "# Audit Report\n\n"
        f"- run_id: `{metrics.run_id}`\n"
        f"- total_units: {report.summary.total_units}\n"
        f"- total_flags: {report.summary.total_flags}\n"
        f"- similarity_conflicts: {len(report.similarity_conflicts)}\n"
        f"- functions_exact_match: {metrics.functions_exact_match:.4f}\n"
        f"- primary_function_accuracy: {metrics.primary_function_accuracy:.4f}\n"
        f"- micro_f1: {metrics.micro_f1:.4f}\n"
        f"- macro_f1: {metrics.macro_f1:.4f}\n"
        f"- regression_pass_rate: {metrics.regression_pass_rate:.4f}\n"
        f"- taxonomy_version_effective: `{metrics.taxonomy_version_effective}`\n"
        f"- prompt_version_effective: `{metrics.prompt_version_effective}`\n"
        f"- validator_version_effective: `{metrics.validator_version_effective}`\n"
    )


def micro_scores(
    matched_pairs: list[tuple[NarrativeUnit, NarrativeUnit]],
) -> tuple[float, float, float]:
    tp = fp = fn = 0
    for predicted, gold in matched_pairs:
        predicted_functions = function_set(predicted)
        gold_functions = function_set(gold)
        tp += len(predicted_functions & gold_functions)
        fp += len(predicted_functions - gold_functions)
        fn += len(gold_functions - predicted_functions)
    precision, recall, f1 = prf(tp, fp, fn)
    return precision, recall, f1


def function_set(unit: NarrativeUnit) -> set[str]:
    return {str(function) for function in unit.functions}


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return round(len(left & right) / len(union), 4) if union else 0.0


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = ratio(tp, tp + fp)
    recall = ratio(tp, tp + fn)
    f1 = round((2 * precision * recall) / (precision + recall), 4) if precision + recall else 0.0
    return precision, recall, f1


def ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def average(values: list[float | int]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def count_severity(flags: list[ValidatorFlag], severity: ValidatorSeverity) -> int:
    return sum(1 for flag in flags if flag.severity == severity)
