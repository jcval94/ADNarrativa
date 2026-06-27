from __future__ import annotations

import json
from pathlib import Path

NOTEBOOK_PATH = (
    Path(__file__).resolve().parents[1] / "examples" / "colab" / "narrative_dna_quickstart.ipynb"
)


def notebook_source() -> str:
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") in {"code", "markdown"}
    )


def test_relation_and_chain_printers_use_current_json_contract() -> None:
    source = notebook_source()

    assert "rel.evidence_spans" in source
    assert "chain.evidence_spans" in source
    assert "chain.score" in source
    assert "rel.evidence}" not in source
    assert "chain.strength" not in source


def test_colab_pytest_cell_isolated_and_preserves_failure_output() -> None:
    source = notebook_source()

    assert 'pytest_env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"' in source
    assert '"no:cacheprovider"' in source
    assert "stdout=subprocess.PIPE" in source
    assert "stderr=subprocess.STDOUT" in source
    assert "check=False" in source
    assert "print(pytest_run.stdout)" in source


def test_colab_includes_executable_paraphrase_invariance_experiment() -> None:
    source = notebook_source()

    assert "paraphrase_groups =" in source
    assert "def classification_signature(unit):" in source
    assert "def run_paraphrase_experiment(*, use_llm, run_prefix):" in source
    assert 'report["same_signature"] = report["unique_signatures"].eq(1)' in source
    assert 'raise AssertionError(f"Invariancia rota en: {failed_groups}")' in source
