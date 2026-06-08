from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from narrative_dna.cli import app
from narrative_dna.pipeline import run_pipeline, run_pipeline_from_text


def write_transcript(tmp_path: Path) -> Path:
    input_dir = tmp_path / "transcripts"
    input_dir.mkdir()
    (input_dir / "demo.txt").write_text(
        "¿Por qué falla? Porque faltan datos. En resumen, hay que revisar.",
        encoding="utf-8",
    )
    return input_dir


def test_run_pipeline_no_llm_writes_core_outputs(tmp_path: Path) -> None:
    input_dir = write_transcript(tmp_path)
    output_dir = tmp_path / "outputs"

    result = run_pipeline(
        input_dir=input_dir,
        output_dir=output_dir,
        run_id="run_pipeline_test",
        use_llm=False,
        use_adjudicator=False,
    )

    run_dir = output_dir / "run_pipeline_test"
    assert result.run_id == "run_pipeline_test"
    assert len(result.documents) == 1
    assert (run_dir / "run_manifest.json").exists()
    assert (run_dir / "documents.jsonl").exists()
    assert (run_dir / "units.jsonl").exists()
    assert (run_dir / "relations.jsonl").exists()
    assert (run_dir / "chains.jsonl").exists()
    assert (run_dir / "audit_report.json").exists()
    assert (run_dir / "audit_report.md").exists()
    assert (run_dir / "dna_sequences.txt").exists()
    assert (run_dir / "exports" / "units.csv").exists()
    assert (run_dir / "exports" / "relations.csv").exists()
    assert (run_dir / "exports" / "chains.csv").exists()

    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    units = [
        json.loads(line)
        for line in (run_dir / "units.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert manifest["run_id"] == "run_pipeline_test"
    assert manifest["taxonomy_version"] == "v1_0"
    assert manifest["config_snapshot"]["pipeline_options"]["use_llm"] is False
    assert any(unit["heuristic_candidates"] for unit in units)
    assert all(unit["final_notation"] == "N_N0{0}" for unit in units)
    assert "N_N0{0}" in (run_dir / "dna_sequences.txt").read_text(encoding="utf-8")


def test_run_pipeline_from_text_writes_general_outputs(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"

    result = run_pipeline_from_text(
        "Te propongo algo simple. Que aprendiste este año?",
        document_id="inline_demo",
        source_path="<test-string>",
        metadata={"source": "unit_test"},
        language="es",
        output_dir=output_dir,
        run_id="run_inline_text",
        use_llm=False,
        use_adjudicator=False,
    )

    run_dir = output_dir / "run_inline_text"
    units = [
        json.loads(line)
        for line in (run_dir / "units.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert result.run_id == "run_inline_text"
    assert result.documents[0].source_path == "<test-string>"
    assert units
    assert all(unit["final_notation"] == "N_N0{0}" for unit in units)
    assert any(unit["heuristic_candidates"] for unit in units)
    assert (run_dir / "documents.jsonl").exists()


def test_cli_run_and_inspect(tmp_path: Path) -> None:
    input_dir = write_transcript(tmp_path)
    output_dir = tmp_path / "outputs"
    runner = CliRunner()

    run_result = runner.invoke(
        app,
        [
            "run",
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--run-id",
            "run_cli_test",
            "--no-llm",
            "--no-adjudicator",
        ],
    )

    assert run_result.exit_code == 0
    assert "Wrote run run_cli_test" in run_result.stdout

    inspect_result = runner.invoke(
        app,
        ["inspect", "--run-id", "run_cli_test", "--outputs-dir", str(output_dir)],
    )

    assert inspect_result.exit_code == 0
    assert "Run run_cli_test" in inspect_result.stdout
    assert "documents" in inspect_result.stdout
