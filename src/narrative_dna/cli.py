"""Command line interface for narrative_dna."""

from __future__ import annotations

import typer
from rich.console import Console

from narrative_dna.schema_exporter import export_schemas as export_schema_files

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
def audit_similarity() -> None:
    """Audit semantic similarity conflicts."""


@app.command("build-review-set")
def build_review_set() -> None:
    """Build a synthetic review set."""


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
