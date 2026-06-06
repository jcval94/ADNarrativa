"""Command line interface for narrative_dna."""

from __future__ import annotations

import typer
from rich.console import Console

from narrative_dna.review_set_builder import build_and_write_review_set
from narrative_dna.schema_exporter import export_schemas as export_schema_files
from narrative_dna.similarity_auditor import audit_similarity_run

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
def evaluate() -> None:
    """Evaluate a run against an allowed gold source."""


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


@app.command("synthetic-review")
def synthetic_review() -> None:
    """Run synthetic committee review."""


@app.command("promote-synthetic-gold")
def promote_synthetic_gold() -> None:
    """Promote high-confidence synthetic review outputs."""


@app.command("export-schemas")
def export_schemas(
    output_dir: str = typer.Option("schemas", help="Directory for schema files."),
) -> None:
    """Export JSON Schemas."""
    written = export_schema_files(output_dir)
    console.print(f"Exported {len(written)} schema files to {output_dir}")


if __name__ == "__main__":
    app()
