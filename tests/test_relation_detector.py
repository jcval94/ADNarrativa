from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from narrative_dna.cli import app
from narrative_dna.models import NarrativeDocument, NarrativeUnit
from narrative_dna.notation import derive_final_notation
from narrative_dna.relation_detector import (
    detect_relations,
    detect_relations_for_document,
    detect_relations_for_run,
    relation_summary,
)


def unit_payload(
    *,
    document_id: str = "doc",
    unit_id: str,
    sequence_index: int,
    text: str,
    functions: list[str],
    primary_function: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "document_id": document_id,
        "unit_id": unit_id,
        "sequence_index": sequence_index,
        "text": text,
        "normalized_text": text.lower(),
        "functions": functions,
        "primary_function": primary_function,
        "secondary_functions": [function for function in functions if function != primary_function],
        "inherited_functions": [],
        "certainty": "none",
        "emotion_expressed": "N",
        "emotion_intensity": 0,
        "emotions_mentioned": [],
        "stance": "neutral",
        "target": None,
        "speech_act": None,
        "logic": None,
        "evidence_spans": [{"text": text}],
        "rejected_labels": [],
        "validator_flags": [],
        "heuristic_candidates": [],
        "llm_votes": [],
        "confidence": 0.9,
        "method": "adjudicated",
        "needs_review": False,
        "review_reasons": [],
        "review_status": "accepted",
        "final_notation": "",
        "taxonomy_version": "v1_0",
        "prompt_version": "v1_0",
        "validator_version": "v1_0",
    }
    payload["final_notation"] = derive_final_notation(payload)
    return payload


def unit(**kwargs: Any) -> NarrativeUnit:
    return NarrativeUnit.model_validate(unit_payload(**kwargs))


def document(document_id: str, units: list[NarrativeUnit]) -> NarrativeDocument:
    return NarrativeDocument.model_validate(
        {
            "document_id": document_id,
            "source_path": f"{document_id}.txt",
            "source_type": "txt",
            "language": "es",
            "metadata": {},
            "segmentation": {"strategy": "test", "unit_count": len(units), "notes": []},
            "units": [item.model_dump(mode="json") for item in units],
            "relations": [],
            "chains": [],
            "document_metrics": {},
            "audit_summary": {},
        }
    )


def write_run(tmp_path: Path, run_id: str, documents: list[NarrativeDocument]) -> None:
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "documents.jsonl").write_text(
        "\n".join(json.dumps(item.model_dump(mode="json")) for item in documents) + "\n",
        encoding="utf-8",
    )


def test_detects_core_auditable_relation_types() -> None:
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
        unit(
            unit_id="u2",
            sequence_index=2,
            text="Esto demuestra que el flujo no escala.",
            functions=["K"],
            primary_function="K",
        ),
        unit(
            unit_id="u3",
            sequence_index=3,
            text="El reporte registra 42 casos.",
            functions=["D"],
            primary_function="D",
        ),
        unit(
            unit_id="u4",
            sequence_index=4,
            text="Falla porque el schema permite campos extra.",
            functions=["Y"],
            primary_function="Y",
        ),
        unit(
            unit_id="u5",
            sequence_index=5,
            text="El riesgo es perder auditoría.",
            functions=["X"],
            primary_function="X",
        ),
        unit(
            unit_id="u6",
            sequence_index=6,
            text="La solución es exigir evidence_spans.",
            functions=["S"],
            primary_function="S",
        ),
    ]

    relations = detect_relations(units, run_id="run_rel")
    relation_keys = {
        (relation.source_unit_id, relation.target_unit_id, relation.relation_type)
        for relation in relations
    }

    assert ("u0", "u1", "ANS") in relation_keys
    assert ("u3", "u2", "SUP") in relation_keys
    assert ("u4", "u2", "CAUSE") in relation_keys
    assert ("u6", "u5", "SOLV") in relation_keys
    assert all(relation.run_id == "run_rel" for relation in relations)
    assert all(relation.evidence_spans for relation in relations)


def test_detect_relations_for_document_attaches_summary_and_versions() -> None:
    doc = document(
        "doc",
        [
            unit(
                unit_id="u0",
                sequence_index=0,
                text="Esto es importante.",
                functions=["A"],
                primary_function="A",
            ),
            unit(
                unit_id="u1",
                sequence_index=1,
                text="Por ejemplo, una unidad sin span debe revisarse.",
                functions=["E"],
                primary_function="E",
            ),
        ],
    )

    detected = detect_relations_for_document(doc, run_id="run_doc")

    assert detected.relations[0].relation_type == "EXMP"
    assert detected.relations[0].taxonomy_version_effective == "v1_0"
    assert detected.audit_summary["relation_count"] == 1
    assert relation_summary(detected.relations)["relations_by_type"] == {"EXMP": 1}


def test_detect_relations_for_run_writes_documents_and_relations(tmp_path: Path) -> None:
    run_id = "run_relations"
    doc = document(
        "doc",
        [
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
        ],
    )
    write_run(tmp_path, run_id, [doc])

    documents, relations = detect_relations_for_run(run_id=run_id, outputs_dir=tmp_path)

    assert len(documents) == 1
    assert relations[0].relation_type == "SUP"
    relation_payload = json.loads(
        (tmp_path / run_id / "relations.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert relation_payload["run_id"] == run_id
    assert relation_payload["taxonomy_version_effective"] == "v1_0"


def test_cli_detect_relations(tmp_path: Path) -> None:
    run_id = "run_relations_cli"
    doc = document(
        "doc",
        [
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
        ],
    )
    write_run(tmp_path, run_id, [doc])

    result = CliRunner().invoke(
        app,
        ["detect-relations", "--run-id", run_id, "--outputs-dir", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert "Detected 1 relations" in result.stdout
