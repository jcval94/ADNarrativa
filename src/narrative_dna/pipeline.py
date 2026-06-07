"""End-to-end JSON-first pipeline entry points."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from narrative_dna.adjudicator import ConservativeAdjudicator
from narrative_dna.chain_detector import detect_chains_for_document
from narrative_dna.exporter import write_run_outputs
from narrative_dna.heuristic_candidates import annotate_document_with_heuristics
from narrative_dna.loader import load_documents
from narrative_dna.models import NarrativeDocument, ProjectRunManifest
from narrative_dna.relation_detector import detect_relations_for_document
from narrative_dna.similarity_auditor import audit_similarity, write_similarity_audit
from narrative_dna.unit_classifier import UnitClassifier

PROJECT_VERSION = "0.1.0"
DEFAULT_TAXONOMY_VERSION = "v1_0"
DEFAULT_PROMPT_VERSION = "v1_0"
DEFAULT_VALIDATOR_VERSION = "v1_0"


@dataclass(frozen=True)
class PipelineRunResult:
    run_id: str
    run_dir: Path
    documents: list[NarrativeDocument]
    manifest: ProjectRunManifest
    output_paths: dict[str, Path]


def run_pipeline(
    *,
    input_dir: str | Path = "data/transcripts",
    output_dir: str | Path = "outputs",
    run_id: str | None = None,
    use_llm: bool = False,
    use_adjudicator: bool = False,
    audit_similarity_enabled: bool = False,
    limit: int | None = None,
) -> PipelineRunResult:
    """Run the JSON-first pipeline and write core outputs."""

    effective_run_id = run_id or make_run_id()
    run_dir = Path(output_dir) / effective_run_id
    raw_documents = load_documents(input_dir, limit=limit)
    classifier = UnitClassifier() if use_llm else None
    adjudicator = ConservativeAdjudicator() if use_adjudicator else None
    processed_documents = [
        process_document(
            document,
            run_id=effective_run_id,
            classifier=classifier,
            adjudicator=adjudicator,
        )
        for document in raw_documents
    ]
    conflicts = []
    similarity_summary = None
    if audit_similarity_enabled:
        conflicts, similarity_summary = audit_similarity(
            processed_documents, run_id=effective_run_id
        )
    manifest = build_run_manifest(
        run_id=effective_run_id,
        input_dir=input_dir,
        output_dir=output_dir,
        use_llm=use_llm,
        use_adjudicator=use_adjudicator,
        audit_similarity_enabled=audit_similarity_enabled,
        limit=limit,
    )
    output_paths = write_run_outputs(
        run_dir=run_dir,
        manifest=manifest,
        documents=processed_documents,
        similarity_conflicts=conflicts,
    )
    if audit_similarity_enabled:
        assert similarity_summary is not None
        conflict_path, summary_path = write_similarity_audit(
            conflicts=conflicts,
            summary=similarity_summary,
            output_dir=run_dir,
        )
        output_paths["similarity_conflicts"] = conflict_path
        output_paths["similarity_conflicts_summary"] = summary_path
    return PipelineRunResult(
        run_id=effective_run_id,
        run_dir=run_dir,
        documents=processed_documents,
        manifest=manifest,
        output_paths=output_paths,
    )


def process_document(
    document: NarrativeDocument,
    *,
    run_id: str,
    classifier: UnitClassifier | None,
    adjudicator: ConservativeAdjudicator | None,
) -> NarrativeDocument:
    """Apply in-memory pipeline stages to one document."""

    current = annotate_document_with_heuristics(document)
    if classifier is not None:
        current = classifier.classify_document(current)
    if adjudicator is not None:
        current = adjudicator.adjudicate_document(current)
    current = detect_relations_for_document(current, run_id=run_id)
    current = detect_chains_for_document(current, run_id=run_id)
    payload = current.model_dump(mode="json")
    payload["audit_summary"] = {
        **current.audit_summary,
        "pipeline_completed": True,
        "taxonomy_version_effective": DEFAULT_TAXONOMY_VERSION,
        "prompt_version_effective": DEFAULT_PROMPT_VERSION,
        "validator_version_effective": DEFAULT_VALIDATOR_VERSION,
    }
    return NarrativeDocument.model_validate(payload)


def build_run_manifest(
    *,
    run_id: str,
    input_dir: str | Path,
    output_dir: str | Path,
    use_llm: bool,
    use_adjudicator: bool,
    audit_similarity_enabled: bool,
    limit: int | None,
) -> ProjectRunManifest:
    config_snapshot = load_json_object(Path("configs/project_config.json"))
    config_snapshot["pipeline_options"] = {
        "use_llm": use_llm,
        "use_adjudicator": use_adjudicator,
        "audit_similarity": audit_similarity_enabled,
        "limit": limit,
    }
    return ProjectRunManifest(
        run_id=run_id,
        created_at_utc=datetime.now(UTC),
        project_version=PROJECT_VERSION,
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        validator_version=DEFAULT_VALIDATOR_VERSION,
        prompt_version=DEFAULT_PROMPT_VERSION,
        input_dir=str(input_dir),
        output_dir=str(output_dir),
        config_snapshot=config_snapshot,
        llm_config_snapshot=load_json_object(Path("configs/llm_config.json")),
        git_commit=current_git_commit(),
    )


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def make_run_id(now: datetime | None = None) -> str:
    value = now or datetime.now(UTC)
    return f"run_{value.strftime('%Y%m%dT%H%M%SZ')}"


def current_git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    commit = result.stdout.strip()
    return commit or None
