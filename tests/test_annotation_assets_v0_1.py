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
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_taxonomy_v0_1_has_complete_function_cards() -> None:
    taxonomy = load_json(GUIDES / "taxonomy_v0_1.json")
    config_taxonomy = load_json(CONFIGS / "taxonomy_v0_1.json")

    assert EFFECTIVE_KEYS <= taxonomy.keys()
    assert taxonomy == config_taxonomy
    assert taxonomy["taxonomy_version"] == "v0_1"
    assert len(taxonomy["functions"]) == 24

    codes = {function["code"] for function in taxonomy["functions"]}
    assert codes == set(taxonomy["function_codes"])

    for function in taxonomy["functions"]:
        assert REQUIRED_FUNCTION_FIELDS <= function.keys()
        assert function["definition"]
        assert function["positive_examples"]
        assert function["negative_examples"]
        assert function["minimal_pair_examples"]
        assert set(function["confusable_with"]) <= codes


def test_label_boundaries_and_validator_rules_are_consistent() -> None:
    boundaries = load_json(GUIDES / "label_boundaries_v0_1.json")
    validators = load_json(GUIDES / "validator_rules_seed_v0_1.json")
    config_validators = load_json(CONFIGS / "validators_config_v0_1.json")

    assert EFFECTIVE_KEYS <= boundaries.keys()
    assert validators == config_validators
    assert EFFECTIVE_KEYS <= validators.keys()

    rule_ids = {rule["rule_id"] for rule in validators["rules"]}
    assert {
        "N_exclusive",
        "K_inherits_A",
        "D_requires_evidence",
        "R_requires_anchor",
        "emotion_mentioned_vs_expressed",
        "possible_overlabeling",
        "notation_derivation",
    } <= rule_ids

    for boundary in boundaries["boundaries"]:
        assert boundary["decision_rule_id"].startswith("DT_")
        assert set(boundary["validator_rule_ids"]) <= rule_ids


def test_minimal_pairs_seed_v0_1_is_large_and_referentially_valid() -> None:
    taxonomy = load_json(GUIDES / "taxonomy_v0_1.json")
    validators = load_json(GUIDES / "validator_rules_seed_v0_1.json")
    pairs = load_jsonl(GUIDES / "minimal_pairs_seed_v0_1.jsonl")

    function_codes = set(taxonomy["function_codes"])
    emotion_codes = {emotion["code"] for emotion in taxonomy["emotions"]}
    stance_codes = {stance["code"] for stance in taxonomy["stance"]}
    validator_rule_ids = {rule["rule_id"] for rule in validators["rules"]}
    decision_rule_ids = {boundary["decision_rule_id"] for boundary in taxonomy["boundary_groups"]}

    assert len(pairs) >= 120
    assert len({pair["pair_id"] for pair in pairs}) == len(pairs)

    for pair in pairs:
        assert EFFECTIVE_KEYS <= pair.keys()
        assert pair["taxonomy_version"] == "v0_1"
        assert pair["decision_rule_id"] in decision_rule_ids
        assert set(pair["validator_rule_ids"]) <= validator_rule_ids
        assert pair["text_a"]
        assert pair["text_b"]
        for side in ("expected_a", "expected_b"):
            expected = pair[side]
            assert set(expected["functions"]) <= function_codes
            assert expected["primary_function"] in function_codes
            assert expected["emotion_expressed"] in emotion_codes
            assert expected["stance"] in stance_codes


def test_positive_negative_examples_cover_every_function() -> None:
    taxonomy = load_json(GUIDES / "taxonomy_v0_1.json")
    examples = load_jsonl(GUIDES / "positive_negative_examples_v0_1.jsonl")

    function_codes = set(taxonomy["function_codes"])
    example_labels = {example["label"] for example in examples}

    assert example_labels == function_codes
    for example in examples:
        assert EFFECTIVE_KEYS <= example.keys()
        assert example["positive_examples"]
        assert example["negative_examples"]


def test_decision_trees_and_notation_contract_define_required_boundaries() -> None:
    decision_trees = (GUIDES / "decision_trees_v0_1.md").read_text(encoding="utf-8")
    notation_contract = (GUIDES / "notation_contract_v0_1.md").read_text(encoding="utf-8")

    for tree_id in [
        "DT_A_K_O",
        "DT_P_R_Y",
        "DT_D_A_K_Q",
        "DT_E_H_G",
        "DT_S_I_U",
        "DT_C_B_X",
        "DT_T_M_L_Z",
        "DT_EMOTION_EXPRESSED_MENTIONED",
        "DT_NEUTRAL_LIGHT_EMOTION",
        "DT_STANCE",
    ]:
        assert tree_id in decision_trees

    assert "final_notation` se deriva" in notation_contract
    assert "CSV sólo es export derivado" in notation_contract


def test_version_migration_rules_reserve_v1_0() -> None:
    migration = load_json(CONFIGS / "version_migration_rules.json")

    assert EFFECTIVE_KEYS <= migration.keys()
    assert migration["base_version"] == "v0_1"
    assert migration["reserved_stable_version"] == "v1_0"
    assert any(
        rule["from_version"] == "v0_1" and rule["to_version"] == "v1_0"
        for rule in migration["rules"]
    )
