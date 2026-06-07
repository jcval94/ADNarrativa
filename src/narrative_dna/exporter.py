"""Derived run export entry points."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from narrative_dna.models import (
    AuditReport,
    NarrativeChain,
    NarrativeDocument,
    NarrativeRelation,
    NarrativeUnit,
    ProjectRunManifest,
    SimilarityConflict,
    ValidatorFlag,
    ValidatorSeverity,
    ValidatorSummary,
)

DEFAULT_TAXONOMY_VERSION = "v1_0"
DEFAULT_PROMPT_VERSION = "v1_0"
DEFAULT_VALIDATOR_VERSION = "v1_0"


def write_run_outputs(
    *,
    run_dir: str | Path,
    manifest: ProjectRunManifest,
    documents: list[NarrativeDocument],
    similarity_conflicts: list[SimilarityConflict] | None = None,
) -> dict[str, Path]:
    """Write all core JSON-first outputs plus derived CSV exports."""

    destination = Path(run_dir)
    destination.mkdir(parents=True, exist_ok=True)
    export_dir = destination / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    units = [unit for document in documents for unit in document.units]
    relations = [relation for document in documents for relation in document.relations]
    chains = [chain for document in documents for chain in document.chains]
    audit_report = build_audit_report(
        run_id=manifest.run_id,
        documents=documents,
        similarity_conflicts=similarity_conflicts or [],
    )

    paths = {
        "run_manifest": destination / "run_manifest.json",
        "documents": destination / "documents.jsonl",
        "units": destination / "units.jsonl",
        "relations": destination / "relations.jsonl",
        "chains": destination / "chains.jsonl",
        "audit_report": destination / "audit_report.json",
        "audit_report_md": destination / "audit_report.md",
        "dna_sequences": destination / "dna_sequences.txt",
        "units_csv": export_dir / "units.csv",
        "relations_csv": export_dir / "relations.csv",
        "chains_csv": export_dir / "chains.csv",
    }
    paths["run_manifest"].write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    write_jsonl(paths["documents"], documents)
    write_jsonl(paths["units"], units)
    write_jsonl(paths["relations"], relations)
    write_jsonl(paths["chains"], chains)
    paths["audit_report"].write_text(
        json.dumps(
            audit_report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    paths["audit_report_md"].write_text(audit_report_markdown(audit_report), encoding="utf-8")
    paths["dna_sequences"].write_text(dna_sequences(documents), encoding="utf-8")
    write_units_csv(paths["units_csv"], units)
    write_relations_csv(paths["relations_csv"], relations)
    write_chains_csv(paths["chains_csv"], chains)
    return paths


def build_audit_report(
    *,
    run_id: str,
    documents: list[NarrativeDocument],
    similarity_conflicts: list[SimilarityConflict] | None = None,
) -> AuditReport:
    units = [unit for document in documents for unit in document.units]
    relation_flags = [
        flag
        for document in documents
        for relation in document.relations
        for flag in relation.validator_flags
    ]
    chain_flags = [
        flag
        for document in documents
        for chain in document.chains
        for flag in chain.validator_flags
    ]
    unit_flags = [flag for unit in units for flag in unit.validator_flags]
    flags = [*unit_flags, *relation_flags, *chain_flags]
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
        similarity_conflicts=similarity_conflicts or [],
        cluster_instabilities=[],
        taxonomy_version_effective=DEFAULT_TAXONOMY_VERSION,
        prompt_version_effective=DEFAULT_PROMPT_VERSION,
        validator_version_effective=DEFAULT_VALIDATOR_VERSION,
    )


def write_jsonl(path: Path, records: list[BaseModel]) -> None:
    path.write_text(
        "\n".join(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False) for record in records
        )
        + ("\n" if records else ""),
        encoding="utf-8",
    )


def dna_sequences(documents: list[NarrativeDocument]) -> str:
    lines = []
    for document in documents:
        sequence = " ".join(unit.final_notation for unit in document.units)
        lines.append(f"{document.document_id}\t{sequence}")
    return "\n".join(lines) + ("\n" if lines else "")


def write_units_csv(path: Path, units: list[NarrativeUnit]) -> None:
    rows = [
        {
            "document_id": unit.document_id,
            "unit_id": unit.unit_id,
            "sequence_index": unit.sequence_index,
            "text": unit.text,
            "functions": "+".join(str(function) for function in unit.functions),
            "primary_function": str(unit.primary_function),
            "final_notation": unit.final_notation,
            "confidence": unit.confidence,
            "method": str(unit.method),
            "needs_review": unit.needs_review,
            "review_status": str(unit.review_status),
            "taxonomy_version": unit.taxonomy_version,
            "prompt_version": unit.prompt_version,
            "validator_version": unit.validator_version,
        }
        for unit in units
    ]
    write_csv(path, rows, fieldnames=list(rows[0]) if rows else default_unit_csv_fields())


def write_relations_csv(path: Path, relations: list[NarrativeRelation]) -> None:
    rows = [
        {
            "run_id": relation.run_id,
            "document_id": relation.document_id,
            "relation_id": relation.relation_id,
            "source_unit_id": relation.source_unit_id,
            "target_unit_id": relation.target_unit_id,
            "relation_type": str(relation.relation_type),
            "confidence": relation.confidence,
            "method": str(relation.method),
            "needs_review": relation.needs_review,
            "taxonomy_version_effective": relation.taxonomy_version_effective,
            "prompt_version_effective": relation.prompt_version_effective,
            "validator_version_effective": relation.validator_version_effective,
        }
        for relation in relations
    ]
    write_csv(path, rows, fieldnames=list(rows[0]) if rows else default_relation_csv_fields())


def write_chains_csv(path: Path, chains: list[NarrativeChain]) -> None:
    rows = [
        {
            "run_id": chain.run_id,
            "document_id": chain.document_id,
            "chain_id": chain.chain_id,
            "chain_type": chain.chain_type,
            "unit_ids": "|".join(chain.unit_ids),
            "relation_ids": "|".join(chain.relation_ids),
            "notation_sequence": " ".join(chain.notation_sequence),
            "score": chain.score,
            "needs_review": chain.needs_review,
            "taxonomy_version_effective": chain.taxonomy_version_effective,
            "prompt_version_effective": chain.prompt_version_effective,
            "validator_version_effective": chain.validator_version_effective,
        }
        for chain in chains
    ]
    write_csv(path, rows, fieldnames=list(rows[0]) if rows else default_chain_csv_fields())


def write_csv(path: Path, rows: list[dict[str, Any]], *, fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def audit_report_markdown(report: AuditReport) -> str:
    return (
        "# Audit Report\n\n"
        f"- run_id: `{report.run_id}`\n"
        f"- total_units: {report.summary.total_units}\n"
        f"- total_flags: {report.summary.total_flags}\n"
        f"- errors: {report.summary.errors}\n"
        f"- warnings: {report.summary.warnings}\n"
        f"- infos: {report.summary.infos}\n"
        f"- taxonomy_version_effective: `{report.taxonomy_version_effective}`\n"
        f"- prompt_version_effective: `{report.prompt_version_effective}`\n"
        f"- validator_version_effective: `{report.validator_version_effective}`\n"
    )


def count_severity(flags: list[ValidatorFlag], severity: ValidatorSeverity) -> int:
    return sum(1 for flag in flags if flag.severity == severity)


def default_unit_csv_fields() -> list[str]:
    return [
        "document_id",
        "unit_id",
        "sequence_index",
        "text",
        "functions",
        "primary_function",
        "final_notation",
        "confidence",
        "method",
        "needs_review",
        "review_status",
        "taxonomy_version",
        "prompt_version",
        "validator_version",
    ]


def default_relation_csv_fields() -> list[str]:
    return [
        "run_id",
        "document_id",
        "relation_id",
        "source_unit_id",
        "target_unit_id",
        "relation_type",
        "confidence",
        "method",
        "needs_review",
        "taxonomy_version_effective",
        "prompt_version_effective",
        "validator_version_effective",
    ]


def default_chain_csv_fields() -> list[str]:
    return [
        "run_id",
        "document_id",
        "chain_id",
        "chain_type",
        "unit_ids",
        "relation_ids",
        "notation_sequence",
        "score",
        "needs_review",
        "taxonomy_version_effective",
        "prompt_version_effective",
        "validator_version_effective",
    ]
