"""Command line interface for narrative_dna."""

from __future__ import annotations

import typer
from rich.console import Console

from narrative_dna.chain_detector import detect_chains_for_run
from narrative_dna.evaluator import write_evaluation_outputs
from narrative_dna.relation_detector import detect_relations_for_run
from narrative_dna.review_set_builder import build_and_write_review_set
from narrative_dna.schema_exporter import export_schemas as export_schema_files
from narrative_dna.similarity_auditor import audit_similarity_run
from narrative_dna.synthetic_reliability import write_synthetic_reliability_outputs
from narrative_dna.synthetic_reviewer import (
    SyntheticCommitteeReviewer,
    run_and_write_synthetic_review,
)

app = typer.Typer(
    help="JSON-first narrative DNA annotation toolkit.",
    no_args_is_help=True,
)
console = Console()


@app.command("validate-taxonomy")
def validate_taxonomy() -> None:
    """Validate taxonomy contracts."""


@app.command("run")
def run() -> None:
    """Run the JSON-first annotation pipeline."""


@app.command("evaluate")
def evaluate(
    run_id: str = typer.Option(..., "--run-id", help="Run id under outputs/."),
    gold: str = typer.Option(..., "--gold", help="Gold JSONL path."),
    outputs_dir: str = typer.Option("outputs", "--outputs-dir", help="Base outputs directory."),
) -> None:
    """Evaluate a run against an allowed gold source."""
    metrics = write_evaluation_outputs(run_id=run_id, gold_path=gold, outputs_dir=outputs_dir)
    console.print(
        f"Evaluated run {metrics.run_id}: "
        f"{metrics.matched_units}/{metrics.total_gold_units} matched gold units, "
        f"micro_f1={metrics.micro_f1:.4f}, macro_f1={metrics.macro_f1:.4f}."
    )


@app.command("inspect")
def inspect_run() -> None:
    """Inspect a run manifest and outputs."""


@app.command("audit-similarity")
def audit_similarity(
    run_id: str = typer.Option(..., "--run-id", help="Run id under outputs/."),
    outputs_dir: str = typer.Option("outputs", "--outputs-dir", help="Base outputs directory."),
    top_k: int = typer.Option(10, "--top-k", help="Nearest neighbors to inspect per unit."),
    threshold: float = typer.Option(0.82, "--threshold", help="Cosine similarity threshold."),
) -> None:
    """Audit semantic similarity conflicts."""
    conflicts, summary = audit_similarity_run(
        run_id=run_id,
        outputs_dir=outputs_dir,
        top_k=top_k,
        threshold=threshold,
    )
    console.print(
        f"Found {len(conflicts)} similarity conflicts for run {summary.run_id} "
        f"(threshold={summary.threshold}, top_k={summary.top_k})."
    )


@app.command("build-review-set")
def build_review_set(
    run_id: str = typer.Option(..., "--run-id", help="Run id under outputs/."),
    outputs_dir: str = typer.Option("outputs", "--outputs-dir", help="Base outputs directory."),
) -> None:
    """Build a synthetic review set."""
    items, manifest = build_and_write_review_set(run_id=run_id, outputs_dir=outputs_dir)
    console.print(
        f"Wrote {len(items)} review items for run {manifest.run_id} "
        f"to {outputs_dir}/{run_id}/review/."
    )


@app.command("detect-relations")
def detect_relations(
    run_id: str = typer.Option(..., "--run-id", help="Run id under outputs/."),
    outputs_dir: str = typer.Option("outputs", "--outputs-dir", help="Base outputs directory."),
    max_distance: int = typer.Option(3, "--max-distance", help="Maximum unit distance."),
    min_confidence: float = typer.Option(0.58, "--min-confidence", help="Minimum confidence."),
) -> None:
    """Detect deterministic auditable relations."""
    documents, relations = detect_relations_for_run(
        run_id=run_id,
        outputs_dir=outputs_dir,
        max_distance=max_distance,
        min_confidence=min_confidence,
    )
    console.print(
        f"Detected {len(relations)} relations across {len(documents)} documents for run {run_id}."
    )


@app.command("detect-chains")
def detect_chains(
    run_id: str = typer.Option(..., "--run-id", help="Run id under outputs/."),
    outputs_dir: str = typer.Option("outputs", "--outputs-dir", help="Base outputs directory."),
    min_score: float = typer.Option(0.58, "--min-score", help="Minimum chain score."),
    max_chain_length: int = typer.Option(6, "--max-chain-length", help="Maximum units in a chain."),
) -> None:
    """Detect deterministic auditable narrative chains."""
    documents, chains = detect_chains_for_run(
        run_id=run_id,
        outputs_dir=outputs_dir,
        min_score=min_score,
        max_chain_length=max_chain_length,
    )
    console.print(
        f"Detected {len(chains)} chains across {len(documents)} documents for run {run_id}."
    )


@app.command("synthetic-review")
def synthetic_review(
    run_id: str = typer.Option(..., "--run-id", help="Run id under outputs/."),
    outputs_dir: str = typer.Option("outputs", "--outputs-dir", help="Base outputs directory."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate workflow without API calls."),
    max_items: int | None = typer.Option(None, "--max-items", help="Limit reviewed items."),
) -> None:
    """Run synthetic committee review."""
    reviewer = SyntheticCommitteeReviewer(dry_run=dry_run)
    report = run_and_write_synthetic_review(
        run_id=run_id,
        outputs_dir=outputs_dir,
        reviewer=reviewer,
        max_items=max_items,
    )
    console.print(
        f"Wrote synthetic review for run {report.run_id}: "
        f"{report.reviewer_output_count} reviewer outputs, "
        f"{report.aggregated_count} aggregated items, "
        f"{report.synthetic_gold_candidate_count} candidates."
    )


@app.command("promote-synthetic-gold")
def promote_synthetic_gold(
    run_id: str = typer.Option(..., "--run-id", help="Run id under outputs/."),
    outputs_dir: str = typer.Option("outputs", "--outputs-dir", help="Base outputs directory."),
) -> None:
    """Promote high-confidence synthetic review outputs."""
    metrics = write_synthetic_reliability_outputs(run_id=run_id, outputs_dir=outputs_dir)
    console.print(
        f"Scored synthetic reliability for run {metrics.run_id}: "
        f"{metrics.high_confidence_count} high-confidence, "
        f"{metrics.medium_confidence_count} medium-confidence, "
        f"{metrics.rejected_count} rejected."
    )


@app.command("export-schemas")
def export_schemas(
    output_dir: str = typer.Option("schemas", help="Directory for schema files."),
) -> None:
    """Export JSON Schemas."""
    written = export_schema_files(output_dir)
    console.print(f"Exported {len(written)} schema files to {output_dir}")


if __name__ == "__main__":
    app()
