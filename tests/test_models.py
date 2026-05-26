from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from narrative_dna.models import (
    EvidenceSpan,
    GoldRecord,
    GoldType,
    Method,
    NarrativeRelation,
    NarrativeUnit,
    ProjectRunManifest,
    ReviewStatus,
    Stance,
    SyntheticDecision,
    SyntheticReviewerOutput,
)
from narrative_dna.schema_exporter import export_schemas


def valid_unit_payload() -> dict[str, object]:
    return {
        "document_id": "doc_001",
        "unit_id": "unit_001",
        "sequence_index": 0,
        "text": "Why does this matter?",
        "normalized_text": "why does this matter?",
        "functions": ["P", "V"],
        "primary_function": "P",
        "secondary_functions": ["V"],
        "inherited_functions": [],
        "certainty": "none",
        "emotion_expressed": "S",
        "emotion_intensity": 1,
        "emotions_mentioned": [],
        "stance": "neutral",
        "target": None,
        "speech_act": "question",
        "logic": None,
        "evidence_spans": [{"text": "Why does this matter?", "char_start": 0, "char_end": 21}],
        "rejected_labels": [{"label": "K", "reason": "Interrogative form, not a claim."}],
        "validator_flags": [],
        "heuristic_candidates": [{"label": "P", "confidence": 0.9, "reason": "Question mark."}],
        "llm_votes": [],
        "confidence": 0.84,
        "method": "heuristic",
        "needs_review": False,
        "review_reasons": [],
        "review_status": "accepted",
        "final_notation": "(P+V)_S1{0}",
        "taxonomy_version": "v0_1",
        "prompt_version": "v0_1",
        "validator_version": "v0_1",
    }


def test_valid_json_contracts() -> None:
    unit = NarrativeUnit.model_validate(valid_unit_payload())
    relation = NarrativeRelation.model_validate(
        {
            "relation_id": "rel_001",
            "document_id": "doc_001",
            "source_unit_id": "unit_001",
            "target_unit_id": "unit_002",
            "relation_type": "ANS",
            "confidence": 0.75,
            "method": Method.HEURISTIC,
            "evidence_spans": [EvidenceSpan(text="because", char_start=0, char_end=7)],
            "rejected_relation_types": [],
            "validator_flags": [],
            "needs_review": False,
        }
    )
    manifest = ProjectRunManifest.model_validate(
        {
            "run_id": "run_001",
            "created_at_utc": datetime.now(UTC),
            "project_version": "0.1.0",
            "taxonomy_version": "v0_1",
            "validator_version": "v0_1",
            "prompt_version": "v0_1",
            "input_dir": "data/transcripts",
            "output_dir": "outputs",
            "config_snapshot": {},
            "llm_config_snapshot": {},
        }
    )
    gold = GoldRecord.model_validate(
        {
            "gold_id": "gold_001",
            "gold_type": GoldType.SYNTHETIC_HIGH_CONFIDENCE,
            "unit": unit,
            "provenance": "synthetic committee",
            "taxonomy_version_effective": "v0_1",
            "prompt_version_effective": "v0_1",
            "validator_version_effective": "v0_1",
        }
    )

    assert unit.primary_function == "P"
    assert relation.relation_type == "ANS"
    assert manifest.run_id == "run_001"
    assert gold.gold_type == "synthetic_gold_high_confidence"


def test_rejects_extra_fields() -> None:
    payload = valid_unit_payload()
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        NarrativeUnit.model_validate(payload)


def test_rejects_invalid_emotion() -> None:
    payload = valid_unit_payload()
    payload["emotion_expressed"] = "NOT_AN_EMOTION"

    with pytest.raises(ValidationError):
        NarrativeUnit.model_validate(payload)


def test_rejects_emotion_intensity_out_of_range() -> None:
    payload = valid_unit_payload()
    payload["emotion_intensity"] = 4

    with pytest.raises(ValidationError):
        NarrativeUnit.model_validate(payload)


def test_rejects_invalid_function() -> None:
    payload = valid_unit_payload()
    payload["functions"] = ["P", "INVALID"]

    with pytest.raises(ValidationError):
        NarrativeUnit.model_validate(payload)


def test_rejects_invalid_relation_type() -> None:
    with pytest.raises(ValidationError):
        NarrativeRelation.model_validate(
            {
                "relation_id": "rel_001",
                "document_id": "doc_001",
                "source_unit_id": "unit_001",
                "target_unit_id": "unit_002",
                "relation_type": "INVALID",
                "confidence": 0.75,
                "method": "heuristic",
                "evidence_spans": [],
                "rejected_relation_types": [],
                "validator_flags": [],
                "needs_review": False,
            }
        )


def test_rejects_synthetic_review_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        SyntheticReviewerOutput.model_validate(
            {
                "review_item_id": "review_001",
                "reviewer_id": "reviewer_a",
                "decision": SyntheticDecision.ACCEPT,
                "proposed_unit": None,
                "confidence": 1.2,
                "rationale": "Too confident.",
                "validator_flags": [],
            }
        )


def test_rejects_n_with_other_functions() -> None:
    payload = valid_unit_payload()
    payload["functions"] = ["N", "P"]
    payload["primary_function"] = "N"

    with pytest.raises(ValidationError):
        NarrativeUnit.model_validate(payload)


def test_exports_json_schemas(tmp_path) -> None:
    written = export_schemas(tmp_path)
    names = {path.name for path in written}

    assert "unit.schema.json" in names
    assert "synthetic_reviewer_output.schema.json" in names
    assert (tmp_path / "unit.schema.json").exists()
    assert '"additionalProperties": false' in (tmp_path / "unit.schema.json").read_text(
        encoding="utf-8"
    )


def test_review_status_and_stance_enums_accept_values() -> None:
    payload = valid_unit_payload()
    payload["review_status"] = ReviewStatus.ACCEPTED
    payload["stance"] = Stance.NEUTRAL

    unit = NarrativeUnit.model_validate(payload)

    assert unit.review_status == "accepted"
    assert unit.stance == "neutral"
