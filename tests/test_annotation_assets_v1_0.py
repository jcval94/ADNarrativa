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
REQUIRED_FUNCTION_FIELDS = {
    "code",
    "name",
    "layer",
    "definition",
    "when_to_use",
    "when_not_to_use",
    "positive_tests",
    "negative_tests",
    "required_evidence",
    "common_lexical_signals",
    "misleading_lexical_signals",
    "confusable_with",
    "boundary_rules",
    "priority_rules",
    "inheritance",
    "allowed_relations",
    "positive_examples",
    "negative_examples",
    "minimal_pair_examples",
    "audit_resolutions",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_taxonomy_v1_0_parse_and_function_cards_are_complete() -> None:
    taxonomy = load_json(GUIDES / "taxonomy_v1_0.json")
    config_taxonomy = load_json(CONFIGS / "taxonomy_v1_0.json")

    assert taxonomy == config_taxonomy
    assert taxonomy["taxonomy_version"] == "v1_0"
    assert taxonomy["from_version"] == "v0_1"
    assert {key: taxonomy[key] for key in EFFECTIVE_KEYS} == {
        "taxonomy_version_effective": "v1_0",
        "prompt_version_effective": "v1_0",
        "validator_version_effective": "v1_0",
    }

    function_codes = set(taxonomy["function_codes"])
    assert len(function_codes) == 24
    assert len(taxonomy["resolved_audit_issues"]) >= 9

    for function in taxonomy["functions"]:
        assert REQUIRED_FUNCTION_FIELDS <= function.keys()
        assert function["code"] in function_codes
        assert set(function["confusable_with"]) <= function_codes
        assert len(function["positive_examples"]) >= 5
        assert len(function["negative_examples"]) >= 5
        assert len(function["minimal_pair_examples"]) >= 3
        assert function["boundary_rules"]
        assert function["priority_rules"]


def test_validator_rules_v1_0_cover_audit_resolutions() -> None:
    validators = load_json(GUIDES / "validator_rules_v1_0.json")
    config_validators = load_json(CONFIGS / "validators_config_v1_0.json")

    assert validators == config_validators
    assert validators["validator_version"] == "v1_0"
    assert EFFECTIVE_KEYS <= validators.keys()

    rule_ids = {rule["rule_id"] for rule in validators["rules"]}
    assert {
        "N_namespace_disambiguation",
        "claim_disputability_test",
        "attribution_content_split",
        "certainty_epistemic_not_intensity",
        "stance_emotion_target_split",
        "contrast_refutation_risk_target",
        "structural_primary_priority",
        "dominant_illustrative_unit",
    } <= rule_ids


def test_minimal_pairs_v1_0_are_valid_and_reference_known_rules() -> None:
    taxonomy = load_json(GUIDES / "taxonomy_v1_0.json")
    validators = load_json(GUIDES / "validator_rules_v1_0.json")
    boundaries = load_json(GUIDES / "label_boundaries_v1_0.json")
    pairs = load_jsonl(GUIDES / "minimal_pairs_v1_0.jsonl")

    function_codes = set(taxonomy["function_codes"])
    emotion_codes = {emotion["code"] for emotion in taxonomy["emotions"]}
    stance_codes = {stance["code"] for stance in taxonomy["stance"]}
    certainty_codes = {certainty["code"] for certainty in taxonomy["certainty"]}
    declared_labels = (
        function_codes
        | emotion_codes
        | stance_codes
        | certainty_codes
        | {"emotion_expressed", "emotions_mentioned", "stance", "certainty", "SUP", "EXPL", "CAUSE"}
    )
    validator_rule_ids = {rule["rule_id"] for rule in validators["rules"]}
    decision_rule_ids = {boundary["decision_rule_id"] for boundary in boundaries["boundaries"]}

    assert len(pairs) >= 180
    assert len({pair["pair_id"] for pair in pairs}) == len(pairs)

    for pair in pairs:
        assert EFFECTIVE_KEYS <= pair.keys()
        assert pair["taxonomy_version"] == "v1_0"
        assert pair["decision_rule_id"] in decision_rule_ids
        assert set(pair["validator_rule_ids"]) <= validator_rule_ids
        assert set(pair["confusable_labels"]) <= declared_labels
        for side in ("expected_a", "expected_b"):
            expected = pair[side]
            assert set(expected["functions"]) <= function_codes
            assert expected["primary_function"] in function_codes
            assert expected["emotion_expressed"] in emotion_codes
            assert expected["stance"] in stance_codes
            assert expected["certainty"] in certainty_codes


def test_no_orphan_labels_across_examples_and_confusion_groups() -> None:
    taxonomy = load_json(GUIDES / "taxonomy_v1_0.json")
    examples = load_jsonl(GUIDES / "positive_negative_examples_v1_0.jsonl")
    confusion_groups = load_json(GUIDES / "confusion_groups_v1_0.json")
    boundaries = load_json(GUIDES / "label_boundaries_v1_0.json")
    validators = load_json(GUIDES / "validator_rules_v1_0.json")

    function_codes = set(taxonomy["function_codes"])
    allowed_non_function = {
        "emotion_expressed",
        "emotions_mentioned",
        "stance",
        "certainty",
        "positive",
        "negative",
        "mixed",
        "neutral",
        "none",
        "strong",
        "tentative",
        "uncertain",
        "N",
        "A",
        "C",
        "S",
        "F",
        "SUP",
        "EXPL",
        "CAUSE",
    }
    decision_tree_ids = {boundary["decision_rule_id"] for boundary in boundaries["boundaries"]}
    validator_rule_ids = {rule["rule_id"] for rule in validators["rules"]}

    assert {example["label"] for example in examples} == function_codes

    for group in confusion_groups["confusion_groups"]:
        assert group["decision_rule_id"] in decision_tree_ids
        assert set(group["validator_rule_ids"]) <= validator_rule_ids
        assert set(group["labels"]) <= function_codes | allowed_non_function
        assert group["expected_confusions"]


def test_every_confusion_group_has_decision_tree_documented() -> None:
    boundaries = load_json(GUIDES / "label_boundaries_v1_0.json")
    decision_trees = (GUIDES / "decision_trees_v1_0.md").read_text(encoding="utf-8")

    for boundary in boundaries["boundaries"]:
        assert boundary["decision_rule_id"] in decision_trees
        assert boundary["validator_rule_ids"]


def test_changelog_records_all_critical_and_high_audit_resolutions() -> None:
    revision_plan = load_json(GUIDES / "taxonomy_revision_plan_v0_2.json")
    changelog = (GUIDES / "CHANGELOG_v0_1_to_v1_0.md").read_text(encoding="utf-8")

    critical_high_ids = {
        issue["issue_id"]
        for issue in revision_plan["issues"]
        if issue["severity"] in {"critical", "high"}
    }
    for issue_id in critical_high_ids:
        assert issue_id in changelog

    assert "No se agregan etiquetas nuevas" in changelog
    assert "No se eliminan etiquetas" in changelog
    assert "taxonomy_version_effective=v1_0" in changelog


def test_version_migration_rules_record_applied_v1_0() -> None:
    migration = load_json(CONFIGS / "version_migration_rules.json")

    assert {key: migration[key] for key in EFFECTIVE_KEYS} == {
        "taxonomy_version_effective": "v1_0",
        "prompt_version_effective": "v1_0",
        "validator_version_effective": "v1_0",
    }
    assert any(
        item["from_version"] == "v0_1" and item["to_version"] == "v1_0"
        for item in migration["applied_migrations"]
    )
