"""End-to-end JSON-first pipeline entry points."""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from narrative_dna.adjudicator import ConservativeAdjudicator
from narrative_dna.chain_detector import detect_chains_for_document
from narrative_dna.exporter import write_run_outputs
from narrative_dna.heuristic_candidates import (
    annotate_document_with_heuristics,
    apply_heuristic_baseline_to_document,
)
from narrative_dna.loader import load_documents, load_text_document
from narrative_dna.models import NarrativeDocument, ProjectRunManifest
from narrative_dna.relation_detector import detect_relations_for_document
from narrative_dna.similarity_auditor import audit_similarity, write_similarity_audit
from narrative_dna.timing import TimingRecorder, build_timing_report, write_timing_report
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
    summary: dict[str, Any]

    def summary_text(self) -> str:
        """Return a compact human-readable run summary for notebooks and CLI output."""

        parts = [
            f"run_id={self.run_id}",
            f"run_dir={self.run_dir}",
            f"documents={self.summary.get('document_count', 0)}",
            f"units={self.summary.get('unit_count', 0)}",
            f"relations={self.summary.get('relation_count', 0)}",
            f"chains={self.summary.get('chain_count', 0)}",
            f"needs_review={self.summary.get('needs_review_unit_count', 0)}",
        ]
        elapsed_seconds = self.summary.get("elapsed_seconds")
        if elapsed_seconds is not None:
            parts.append(f"elapsed={float(elapsed_seconds):.2f}s")
        api_summary = self.summary.get("api_summary") or {}
        if api_summary:
            openai_api_seconds = float(api_summary.get("openai_api_duration_ms", 0)) / 1000
            parts.extend(
                [
                    f"openai_real_calls={api_summary.get('real_openai_calls', 0)}",
                    f"llm_requests={api_summary.get('logical_llm_requests', 0)}",
                    f"cache_hits={api_summary.get('cache_hits', 0)}",
                    f"openai_api_time={openai_api_seconds:.2f}s",
                ]
            )
        timing_path = self.output_paths.get("timing_report")
        if timing_path is not None:
            parts.append(f"timing_report={timing_path}")
        return "PipelineRunResult(" + ", ".join(parts) + ")"

    def __str__(self) -> str:
        return self.summary_text()


def run_pipeline(
    *,
    input_dir: str | Path = "data/transcripts",
    output_dir: str | Path = "outputs",
    run_id: str | None = None,
    use_llm: bool = False,
    use_adjudicator: bool = False,
    llm_strategy: Literal["unit", "chunked"] = "chunked",
    adjudication_policy: Literal["actionable", "strict"] = "actionable",
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
        llm_strategy=llm_strategy,
        adjudication_policy=adjudication_policy,
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
        llm_strategy=llm_strategy,
        adjudication_policy=adjudication_policy,
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
    llm_strategy: Literal["unit", "chunked"] = "chunked",
    adjudication_policy: Literal["actionable", "strict"] = "actionable",
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
        llm_strategy=llm_strategy,
        adjudication_policy=adjudication_policy,
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
        llm_strategy=llm_strategy,
        adjudication_policy=adjudication_policy,
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
    llm_strategy: Literal["unit", "chunked"] = "chunked",
    adjudication_policy: Literal["actionable", "strict"] = "actionable",
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
        llm_strategy=llm_strategy,
        adjudication_policy=adjudication_policy,
        audit_similarity_enabled=audit_similarity_enabled,
    )
    with timing.span(
        "pipeline.total",
        output_dir=str(output_dir),
        use_llm=use_llm,
        use_adjudicator=use_adjudicator,
        llm_strategy=llm_strategy,
        adjudication_policy=adjudication_policy,
        audit_similarity_enabled=audit_similarity_enabled,
    ) as total_timing:
        raw_documents = documents[:limit] if limit is not None else documents
        total_timing["document_count"] = len(raw_documents)
        total_timing["unit_count"] = sum(len(document.units) for document in raw_documents)

        classifier = None
        if use_llm:
            with timing.span(
                "pipeline.init_classifier",
                profile_name="main_classifier",
                strategy=llm_strategy,
            ):
                classifier = UnitClassifier(
                    strategy=llm_strategy,
                    timing_recorder=timing,
                    log_timings=log_timings,
                )

        adjudicator = None
        if use_adjudicator:
            with timing.span(
                "pipeline.init_adjudicator",
                profile_name="adjudicator",
                policy=adjudication_policy,
            ):
                adjudicator = ConservativeAdjudicator(
                    policy=adjudication_policy,
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
                llm_strategy=llm_strategy,
                adjudication_policy=adjudication_policy,
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
    timing_report_payload: dict[str, Any] | None = None
    if timing.enabled:
        timing_path = run_dir / "timing_report.json"
        timing_report_payload = build_timing_report(
            timing,
            taxonomy_version_effective=DEFAULT_TAXONOMY_VERSION,
            prompt_version_effective=DEFAULT_PROMPT_VERSION,
            validator_version_effective=DEFAULT_VALIDATOR_VERSION,
        )
        write_timing_report(
            timing_path,
            timing,
            taxonomy_version_effective=DEFAULT_TAXONOMY_VERSION,
            prompt_version_effective=DEFAULT_PROMPT_VERSION,
            validator_version_effective=DEFAULT_VALIDATOR_VERSION,
            payload=timing_report_payload,
        )
        output_paths["timing_report"] = timing_path
    summary = build_pipeline_result_summary(
        run_id=effective_run_id,
        run_dir=run_dir,
        documents=processed_documents,
        timing_report=timing_report_payload,
    )
    return PipelineRunResult(
        run_id=effective_run_id,
        run_dir=run_dir,
        documents=processed_documents,
        manifest=manifest,
        output_paths=output_paths,
        summary=summary,
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
        else:
            current = apply_heuristic_baseline_to_document(current)
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
    llm_strategy: Literal["unit", "chunked"],
    adjudication_policy: Literal["actionable", "strict"],
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
    llm_strategy: Literal["unit", "chunked"],
    adjudication_policy: Literal["actionable", "strict"],
    audit_similarity_enabled: bool,
    limit: int | None,
) -> ProjectRunManifest:
    config_snapshot = load_json_object(Path("configs/project_config.json"))
    config_snapshot["pipeline_options"] = {
        "use_llm": use_llm,
        "use_adjudicator": use_adjudicator,
        "llm_strategy": llm_strategy,
        "adjudication_policy": adjudication_policy,
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


def build_pipeline_result_summary(
    *,
    run_id: str,
    run_dir: Path,
    documents: list[NarrativeDocument],
    timing_report: dict[str, Any] | None,
) -> dict[str, Any]:
    units = [unit for document in documents for unit in document.units]
    relations = [relation for document in documents for relation in document.relations]
    chains = [chain for document in documents for chain in document.chains]
    methods = Counter(str(unit.method) for unit in units)
    summary: dict[str, Any] = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "document_count": len(documents),
        "unit_count": len(units),
        "relation_count": len(relations),
        "chain_count": len(chains),
        "needs_review_unit_count": sum(1 for unit in units if unit.needs_review),
        "accepted_unit_count": sum(1 for unit in units if not unit.needs_review),
        "unit_methods": dict(sorted(methods.items())),
        "taxonomy_version_effective": DEFAULT_TAXONOMY_VERSION,
        "prompt_version_effective": DEFAULT_PROMPT_VERSION,
        "validator_version_effective": DEFAULT_VALIDATOR_VERSION,
    }
    if timing_report:
        summary["elapsed_seconds"] = timing_report.get("elapsed_seconds")
        summary["elapsed_ms"] = timing_report.get("elapsed_ms")
        summary["api_summary"] = timing_report.get("api_summary", {})
        summary["slowest_stages"] = timing_report.get("bottlenecks", [])[:3]
    return summary


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
