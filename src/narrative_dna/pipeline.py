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
from narrative_dna.loader import load_documents, load_text_document
from narrative_dna.models import NarrativeDocument, ProjectRunManifest
from narrative_dna.relation_detector import detect_relations_for_document
from narrative_dna.similarity_auditor import audit_similarity, write_similarity_audit
from narrative_dna.timing import TimingRecorder, write_timing_report
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
    log_timings: bool | None = None,
) -> PipelineRunResult:
    """Run the JSON-first pipeline and write core outputs."""

    effective_run_id = run_id or make_run_id()
    timing_recorder = make_timing_recorder(
        run_id=effective_run_id,
        log_timings=log_timings,
        use_llm=use_llm,
        use_adjudicator=use_adjudicator,
        audit_similarity_enabled=audit_similarity_enabled,
    )
    with timing_recorder.span("pipeline.load_documents", input_dir=str(input_dir), limit=limit):
        raw_documents = load_documents(input_dir, limit=limit)
    return run_pipeline_from_documents(
        documents=raw_documents,
        input_dir=input_dir,
        output_dir=output_dir,
        run_id=effective_run_id,
        use_llm=use_llm,
        use_adjudicator=use_adjudicator,
        audit_similarity_enabled=audit_similarity_enabled,
        limit=limit,
        log_timings=log_timings,
        timing_recorder=timing_recorder,
    )


def run_pipeline_from_text(
    text: str,
    *,
    document_id: str | None = None,
    source_path: str = "<text>",
    metadata: dict[str, Any] | None = None,
    language: str = "und",
    output_dir: str | Path = "outputs",
    run_id: str | None = None,
    use_llm: bool = False,
    use_adjudicator: bool = False,
    audit_similarity_enabled: bool = False,
    log_timings: bool | None = None,
) -> PipelineRunResult:
    """Run the JSON-first pipeline from an in-memory transcript string."""

    effective_run_id = run_id or make_run_id()
    timing_recorder = make_timing_recorder(
        run_id=effective_run_id,
        log_timings=log_timings,
        use_llm=use_llm,
        use_adjudicator=use_adjudicator,
        audit_similarity_enabled=audit_similarity_enabled,
    )
    with timing_recorder.span(
        "pipeline.load_text_document",
        document_id=document_id,
        source_path=source_path,
        text_chars=len(text),
    ) as timing:
        document = load_text_document(
            text,
            document_id=document_id,
            source_path=source_path,
            metadata=metadata,
            language=language,
        )
        timing["unit_count"] = len(document.units)
        timing["effective_document_id"] = document.document_id
        timing["char_count"] = document.document_metrics.get("char_count")
    return run_pipeline_from_documents(
        documents=[document],
        input_dir=source_path,
        output_dir=output_dir,
        run_id=effective_run_id,
        use_llm=use_llm,
        use_adjudicator=use_adjudicator,
        audit_similarity_enabled=audit_similarity_enabled,
        log_timings=log_timings,
        timing_recorder=timing_recorder,
    )


def run_pipeline_from_documents(
    *,
    documents: list[NarrativeDocument],
    input_dir: str | Path,
    output_dir: str | Path = "outputs",
    run_id: str | None = None,
    use_llm: bool = False,
    use_adjudicator: bool = False,
    audit_similarity_enabled: bool = False,
    limit: int | None = None,
    log_timings: bool | None = None,
    timing_recorder: TimingRecorder | None = None,
) -> PipelineRunResult:
    """Run the JSON-first pipeline from pre-built documents."""

    effective_run_id = run_id or make_run_id()
    run_dir = Path(output_dir) / effective_run_id
    timing = timing_recorder or make_timing_recorder(
        run_id=effective_run_id,
        log_timings=log_timings,
        use_llm=use_llm,
        use_adjudicator=use_adjudicator,
        audit_similarity_enabled=audit_similarity_enabled,
    )
    with timing.span(
        "pipeline.total",
        output_dir=str(output_dir),
        use_llm=use_llm,
        use_adjudicator=use_adjudicator,
        audit_similarity_enabled=audit_similarity_enabled,
    ) as total_timing:
        raw_documents = documents[:limit] if limit is not None else documents
        total_timing["document_count"] = len(raw_documents)
        total_timing["unit_count"] = sum(len(document.units) for document in raw_documents)

        classifier = None
        if use_llm:
            with timing.span("pipeline.init_classifier", profile_name="main_classifier"):
                classifier = UnitClassifier(timing_recorder=timing, log_timings=log_timings)

        adjudicator = None
        if use_adjudicator:
            with timing.span("pipeline.init_adjudicator", profile_name="adjudicator"):
                adjudicator = ConservativeAdjudicator(
                    timing_recorder=timing,
                    log_timings=log_timings,
                )

        processed_documents = [
            process_document(
                document,
                run_id=effective_run_id,
                classifier=classifier,
                adjudicator=adjudicator,
                timing_recorder=timing,
            )
            for document in raw_documents
        ]
        conflicts = []
        similarity_summary = None
        if audit_similarity_enabled:
            with timing.span(
                "pipeline.audit_similarity",
                document_count=len(processed_documents),
                unit_count=sum(len(document.units) for document in processed_documents),
            ) as audit_timing:
                conflicts, similarity_summary = audit_similarity(
                    processed_documents,
                    run_id=effective_run_id,
                )
                audit_timing["conflict_count"] = len(conflicts)
        with timing.span("pipeline.build_manifest"):
            manifest = build_run_manifest(
                run_id=effective_run_id,
                input_dir=input_dir,
                output_dir=output_dir,
                use_llm=use_llm,
                use_adjudicator=use_adjudicator,
                audit_similarity_enabled=audit_similarity_enabled,
                limit=limit,
            )
        with timing.span(
            "pipeline.write_outputs",
            run_dir=str(run_dir),
            document_count=len(processed_documents),
        ):
            output_paths = write_run_outputs(
                run_dir=run_dir,
                manifest=manifest,
                documents=processed_documents,
                similarity_conflicts=conflicts,
            )
        if audit_similarity_enabled:
            assert similarity_summary is not None
            with timing.span(
                "pipeline.write_similarity_audit",
                run_dir=str(run_dir),
                conflict_count=len(conflicts),
            ):
                conflict_path, summary_path = write_similarity_audit(
                    conflicts=conflicts,
                    summary=similarity_summary,
                    output_dir=run_dir,
                )
                output_paths["similarity_conflicts"] = conflict_path
                output_paths["similarity_conflicts_summary"] = summary_path
        total_timing["processed_document_count"] = len(processed_documents)
        total_timing["processed_unit_count"] = sum(
            len(document.units) for document in processed_documents
        )
    if timing.enabled:
        timing_path = run_dir / "timing_report.json"
        write_timing_report(
            timing_path,
            timing,
            taxonomy_version_effective=DEFAULT_TAXONOMY_VERSION,
            prompt_version_effective=DEFAULT_PROMPT_VERSION,
            validator_version_effective=DEFAULT_VALIDATOR_VERSION,
        )
        output_paths["timing_report"] = timing_path
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
    timing_recorder: TimingRecorder | None = None,
) -> NarrativeDocument:
    """Apply in-memory pipeline stages to one document."""

    timing = timing_recorder or TimingRecorder(run_id=run_id, enabled=False)
    with timing.span(
        "pipeline.process_document",
        document_id=document.document_id,
        unit_count=len(document.units),
    ) as document_timing:
        with timing.span(
            "pipeline.heuristics",
            document_id=document.document_id,
            unit_count=len(document.units),
        ):
            current = annotate_document_with_heuristics(document)
        if classifier is not None:
            current = classifier.classify_document(current)
        if adjudicator is not None:
            current = adjudicator.adjudicate_document(current)
        with timing.span(
            "pipeline.detect_relations",
            document_id=current.document_id,
            unit_count=len(current.units),
        ) as relation_timing:
            current = detect_relations_for_document(current, run_id=run_id)
            relation_timing["relation_count"] = len(current.relations)
        with timing.span(
            "pipeline.detect_chains",
            document_id=current.document_id,
            relation_count=len(current.relations),
        ) as chain_timing:
            current = detect_chains_for_document(current, run_id=run_id)
            chain_timing["chain_count"] = len(current.chains)
        payload = current.model_dump(mode="json")
        payload["audit_summary"] = {
            **current.audit_summary,
            "pipeline_completed": True,
            "taxonomy_version_effective": DEFAULT_TAXONOMY_VERSION,
            "prompt_version_effective": DEFAULT_PROMPT_VERSION,
            "validator_version_effective": DEFAULT_VALIDATOR_VERSION,
        }
        document_timing["relation_count"] = len(current.relations)
        document_timing["chain_count"] = len(current.chains)
        return NarrativeDocument.model_validate(payload)


def make_timing_recorder(
    *,
    run_id: str,
    log_timings: bool | None,
    use_llm: bool,
    use_adjudicator: bool,
    audit_similarity_enabled: bool,
) -> TimingRecorder:
    if log_timings is None:
        enabled = use_llm or use_adjudicator or audit_similarity_enabled
    else:
        enabled = log_timings
    return TimingRecorder(run_id=run_id, enabled=enabled, echo=enabled)


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
