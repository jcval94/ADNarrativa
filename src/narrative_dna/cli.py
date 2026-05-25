"""Command line interface for narrative_dna."""

from __future__ import annotations

import typer

app = typer.Typer(
    help="JSON-first narrative DNA annotation toolkit.",
    no_args_is_help=True,
)


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
def export_schemas() -> None:
    """Export JSON Schemas."""
