from __future__ import annotations

import json
from pathlib import Path

from narrative_dna.loader import load_document, load_documents
from narrative_dna.normalizer import normalize_text, stable_document_id
from narrative_dna.segmenter import SourceSegment, segment_transcript


def test_loads_basic_txt_with_offsets_and_neighbor_links(tmp_path: Path) -> None:
    transcript = tmp_path / "speech.txt"
    transcript.write_text("Primera idea. Segunda idea?", encoding="utf-8")

    document = load_document(transcript)

    assert document.source_type == "txt"
    assert document.units[0].text == "Primera idea."
    assert document.units[0].char_start == 0
    assert document.units[0].next_unit_id == document.units[1].unit_id
    assert document.units[1].previous_unit_id == document.units[0].unit_id
    assert document.units[0].final_notation == "N_N0{0}"


def test_loads_json_transcript_and_preserves_metadata(tmp_path: Path) -> None:
    transcript = tmp_path / "speech.json"
    transcript.write_text(
        json.dumps(
            {
                "document_id": "doc_json",
                "transcript": "Una tesis clara. Un cierre.",
                "metadata": {"channel": "demo"},
            }
        ),
        encoding="utf-8",
    )

    document = load_document(transcript)

    assert document.document_id == "doc_json"
    assert document.metadata["channel"] == "demo"
    assert len(document.units) == 2


def test_loads_json_segments_and_preserves_timestamps(tmp_path: Path) -> None:
    transcript = tmp_path / "speech.json"
    transcript.write_text(
        json.dumps(
            {
                "document_id": "doc_segments",
                "segments": [
                    {"start_ms": 0, "end_ms": 1200, "text": "Primera idea."},
                    {"start_ms": 1200, "end_ms": 2000, "text": "Segunda idea."},
                ],
                "metadata": {"source": "fixture"},
            }
        ),
        encoding="utf-8",
    )

    document = load_document(transcript)

    assert document.units[0].start_ms == 0
    assert document.units[0].end_ms == 1200
    assert document.units[1].start_ms == 1200
    assert document.document_metrics["has_timestamps"] is True


def test_splits_question_and_answer_on_same_line() -> None:
    units = segment_transcript(
        document_id="doc_qa",
        text="Por que pasa esto? Porque nadie mide bien.",
    )

    assert [unit.text for unit in units] == [
        "Por que pasa esto?",
        "Porque nadie mide bien.",
    ]


def test_splits_long_timestamped_segment_with_approximate_timing_flag() -> None:
    long_text = (
        "Esta es una observacion larga porque conecta varias partes del problema "
        "porque tambien explica una consecuencia y porque necesita dividirse."
    )

    units = segment_transcript(
        document_id="doc_long",
        source_segments=[SourceSegment(text=long_text, start_ms=0, end_ms=9000)],
        max_unit_chars=70,
    )

    assert len(units) > 1
    assert units[0].start_ms == 0
    assert units[-1].end_ms == 9000
    assert any(flag.rule_id == "approximate_timing" for flag in units[0].validator_flags)


def test_normalizes_weird_chars_and_invisible_marks() -> None:
    normalized = normalize_text("Hola\u200b  \u201cvida\u201d\r\nnueva\u00a0...")

    assert normalized == 'Hola "vida" nueva ...'


def test_loads_jsonl_one_document_per_line(tmp_path: Path) -> None:
    transcript = tmp_path / "documents.jsonl"
    transcript.write_text(
        "\n".join(
            [
                json.dumps({"document_id": "doc_1", "transcript": "Uno."}),
                json.dumps({"document_id": "doc_2", "transcript": "Dos."}),
            ]
        ),
        encoding="utf-8",
    )

    documents = load_documents(transcript)

    assert [document.document_id for document in documents] == ["doc_1", "doc_2"]


def test_loads_real_video_transcripts_preferring_timestamped_segments() -> None:
    documents = load_documents(Path("data/transcripts/videos"), limit=2)

    assert len(documents) == 2
    assert all(document.units for document in documents)
    assert all(document.document_metrics["has_timestamps"] for document in documents)
    assert all("source_metadata" in document.metadata for document in documents)


def test_stable_document_id_is_content_stable() -> None:
    assert stable_document_id(source_path="a.txt", content="same") == stable_document_id(
        source_path="a.txt", content="same"
    )
