from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from narrative_dna.chain_detector import (
    chain_summary,
    detect_chains,
    detect_chains_for_document,
    detect_chains_for_run,
)
from narrative_dna.cli import app
from narrative_dna.models import NarrativeRelation
from narrative_dna.relation_detector import detect_relations
from tests.test_relation_detector import document, unit


def write_run(
    tmp_path: Path,
    run_id: str,
    documents: list,
    relations: list[NarrativeRelation],
) -> None:
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "documents.jsonl").write_text(
        "\n".join(json.dumps(item.model_dump(mode="json")) for item in documents) + "\n",
        encoding="utf-8",
    )
    (run_dir / "relations.jsonl").write_text(
        "\n".join(json.dumps(item.model_dump(mode="json")) for item in relations) + "\n",
        encoding="utf-8",
    )


def test_detects_relation_based_risk_solution_chain() -> None:
    units = [
        unit(
            unit_id="u0",
            sequence_index=0,
            text="Este flujo puede romper la auditoría.",
            functions=["K"],
            primary_function="K",
        ),
        unit(
            unit_id="u1",
            sequence_index=1,
            text="El riesgo es perder trazabilidad.",
            functions=["X"],
            primary_function="X",
        ),
        unit(
            unit_id="u2",
            sequence_index=2,
            text="La solución es exigir evidence_spans.",
            functions=["S"],
            primary_function="S",
        ),
    ]
    relations = detect_relations(units, run_id="run_chain")

    chains = detect_chains(units, relations, run_id="run_chain")
    risk_solution = [chain for chain in chains if chain.chain_type == "risk_solution"]

    assert risk_solution
    assert risk_solution[0].unit_ids == ["u0", "u1", "u2"]
    assert len(risk_solution[0].relation_ids) == 2
    assert risk_solution[0].run_id == "run_chain"
    assert risk_solution[0].taxonomy_version_effective == "v1_0"
    assert risk_solution[0].evidence_spans


def test_detects_sequence_chain_without_relations() -> None:
    units = [
        unit(
            unit_id="u0",
            sequence_index=0,
            text="Hay riesgo de inconsistencia.",
            functions=["X"],
            primary_function="X",
        ),
        unit(
            unit_id="u1",
            sequence_index=1,
            text="Conviene revisar los casos.",
            functions=["S", "I"],
            primary_function="S",
        ),
        unit(
            unit_id="u2",
            sequence_index=2,
            text="Suscríbete para ver el seguimiento.",
            functions=["V"],
            primary_function="V",
        ),
    ]

    chains = detect_chains(units, [], run_id="run_sequence")

    assert [chain.chain_type for chain in chains] == ["problem_solution_call_sequence"]
    assert chains[0].relation_ids == []
    assert chains[0].notation_sequence == [unit.final_notation for unit in units]


def test_detect_chains_for_document_attaches_summary() -> None:
    units = [
        unit(
            unit_id="u0",
            sequence_index=0,
            text="¿Por qué falla?",
            functions=["P"],
            primary_function="P",
        ),
        unit(
            unit_id="u1",
            sequence_index=1,
            text="La respuesta es que falta evidencia.",
            functions=["R"],
            primary_function="R",
        ),
    ]
    doc = document("doc", units)
    relations = detect_relations(units, run_id="run_doc")
    doc_with_relations = document("doc", units).model_copy(update={"relations": relations})

    detected = detect_chains_for_document(doc_with_relations, run_id="run_doc")

    assert detected.chains[0].chain_type == "question_answer"
    assert detected.chains[0].needs_review is False
    assert detected.audit_summary["chain_count"] == 1
    assert chain_summary(detected.chains)["chains_by_type"] == {"question_answer": 1}
    assert doc.relations == []


def test_detect_chains_for_run_writes_documents_and_chains(tmp_path: Path) -> None:
    run_id = "run_chains"
    units = [
        unit(
            unit_id="u0",
            sequence_index=0,
            text="Esto demuestra una falla.",
            functions=["K"],
            primary_function="K",
        ),
        unit(
            unit_id="u1",
            sequence_index=1,
            text="El reporte registra 42 casos.",
            functions=["D"],
            primary_function="D",
        ),
        unit(
            unit_id="u2",
            sequence_index=2,
            text="Falla porque el schema permite campos extra.",
            functions=["Y"],
            primary_function="Y",
        ),
    ]
    doc = document("doc", units)
    relations = detect_relations(units, run_id=run_id)
    write_run(tmp_path, run_id, [doc], relations)

    documents, chains = detect_chains_for_run(run_id=run_id, outputs_dir=tmp_path)

    assert len(documents) == 1
    assert any(chain.chain_type == "claim_support_explanation" for chain in chains)
    chain_payload = json.loads(
        (tmp_path / run_id / "chains.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert chain_payload["run_id"] == run_id
    assert chain_payload["taxonomy_version_effective"] == "v1_0"


def test_cli_detect_chains(tmp_path: Path) -> None:
    run_id = "run_chains_cli"
    units = [
        unit(
            unit_id="u0",
            sequence_index=0,
            text="¿Qué hacemos?",
            functions=["P"],
            primary_function="P",
        ),
        unit(
            unit_id="u1",
            sequence_index=1,
            text="La respuesta es validar antes.",
            functions=["R"],
            primary_function="R",
        ),
    ]
    doc = document("doc", units)
    relations = detect_relations(units, run_id=run_id)
    write_run(tmp_path, run_id, [doc], relations)

    result = CliRunner().invoke(
        app,
        ["detect-chains", "--run-id", run_id, "--outputs-dir", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert "Detected 1 chains" in result.stdout
