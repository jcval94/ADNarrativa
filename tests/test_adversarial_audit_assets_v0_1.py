from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDES = ROOT / "annotation_guidelines"
CONFIGS = ROOT / "configs"

EFFECTIVE_KEYS = {
    "taxonomy_version_effective",
    "prompt_version_effective",
    "validator_version_effective",
}
ALLOWED_SEVERITIES = {"low", "medium", "high", "critical"}
ISSUE_FIELDS = {
    "issue_id",
    "severity",
    "affected_labels",
    "problem",
    "examples",
    "proposed_fix",
    "expected_impact",
    "requires_new_validator",
    "requires_new_minimal_pairs",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_revision_plan_v0_2_has_required_issue_shape() -> None:
    plan = load_json(GUIDES / "taxonomy_revision_plan_v0_2.json")

    assert EFFECTIVE_KEYS <= plan.keys()
    assert plan["taxonomy_version"] == "v0_1"
    assert plan["do_not_modify_taxonomy_v0_1"] is True
    assert len(plan["issues"]) >= 10

    severities = {issue["severity"] for issue in plan["issues"]}
    assert {"critical", "high"} <= severities

    affected = {label for issue in plan["issues"] for label in issue["affected_labels"]}
    for label in ["A", "K", "O", "R", "Y", "D", "Q", "E", "H", "G", "S", "I", "U"]:
        assert label in affected

    for issue in plan["issues"]:
        assert ISSUE_FIELDS <= issue.keys()
        assert EFFECTIVE_KEYS <= issue.keys()
        assert issue["severity"] in ALLOWED_SEVERITIES
        assert issue["examples"]
        assert isinstance(issue["requires_new_validator"], bool)
        assert isinstance(issue["requires_new_minimal_pairs"], bool)


def test_ambiguous_cases_generated_v0_1_are_large_and_grounded() -> None:
    cases = load_jsonl(GUIDES / "ambiguous_cases_generated_v0_1.jsonl")

    assert len(cases) >= 100
    assert len({case["case_id"] for case in cases}) == len(cases)
    assert any(case["source"]["kind"] == "dataset_transcript" for case in cases)

    for case in cases:
        assert EFFECTIVE_KEYS <= case.keys()
        assert case["taxonomy_version"] == "v0_1"
        assert case["text"]
        assert case["possible_annotations"]
        assert case["preferred_annotation"]
        assert case["why_preferred"]
        assert case["rejected_options"]
        assert case["decision_rule_needed"]
        assert case["preferred_annotation"]["needs_review"] is True


def test_redundancy_report_covers_all_function_codes() -> None:
    taxonomy = load_json(GUIDES / "taxonomy_v0_1.json")
    report = load_json(GUIDES / "redundancy_report_v0_1.json")

    assert EFFECTIVE_KEYS <= report.keys()
    assert report["taxonomy_version"] == "v0_1"

    labels = {action["label"] for action in report["label_actions"]}
    assert labels == set(taxonomy["function_codes"])
    assert report["overlap_hotspots"]

    recommendations = {action["recommendation"] for action in report["label_actions"]}
    assert "keep" in recommendations
    assert "keep_exclusive_fallback" in recommendations


def test_confusion_matrix_expected_covers_required_groups() -> None:
    matrix = load_json(GUIDES / "confusion_matrix_expected_v0_1.json")

    assert EFFECTIVE_KEYS <= matrix.keys()
    assert matrix["taxonomy_version"] == "v0_1"
    groups = {tuple(group["labels"]) for group in matrix["expected_confusions"]}

    assert ("A", "K", "O") in groups
    assert ("P", "R", "Y") in groups
    assert ("D", "Q", "K") in groups
    assert ("E", "H", "G") in groups
    assert ("S", "I", "U") in groups
    assert ("C", "B", "X") in groups
    assert ("T", "M", "L", "Z") in groups


def test_adversarial_audit_markdown_documents_scope() -> None:
    audit = (GUIDES / "adversarial_audit_v0_1.md").read_text(encoding="utf-8")

    assert "taxonomy_version_effective=v0_1" in audit
    assert "data/transcripts/videos" in audit
    assert "No se modifica `taxonomy_v0_1.json`" in audit
    assert "AUDIT-001" in audit
    assert "AUDIT-012" in audit


def test_migration_rules_reference_audit_artifacts() -> None:
    migration = load_json(CONFIGS / "version_migration_rules.json")

    assert EFFECTIVE_KEYS <= migration.keys()
    audit_rules = [
        rule
        for rule in migration["rules"]
        if "auditoría adversarial v0.1" in rule["migration_notes"]
    ]
    assert audit_rules
    assert audit_rules[-1]["from_version"] == "v0_1"
    assert audit_rules[-1]["to_version"] == "v1_0"
    assert (
        "annotation_guidelines/taxonomy_revision_plan_v0_2.json"
        in audit_rules[-1]["audit_artifacts"]
    )
