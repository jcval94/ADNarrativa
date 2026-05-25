from __future__ import annotations

import importlib

MODULES = [
    "narrative_dna",
    "narrative_dna.adjudicator",
    "narrative_dna.chain_detector",
    "narrative_dna.cli",
    "narrative_dna.cluster_auditor",
    "narrative_dna.evaluator",
    "narrative_dna.exporter",
    "narrative_dna.heuristic_candidates",
    "narrative_dna.llm_client",
    "narrative_dna.loader",
    "narrative_dna.models",
    "narrative_dna.normalizer",
    "narrative_dna.notation",
    "narrative_dna.pipeline",
    "narrative_dna.relation_detector",
    "narrative_dna.review_aggregator",
    "narrative_dna.review_set_builder",
    "narrative_dna.schema_exporter",
    "narrative_dna.segmenter",
    "narrative_dna.similarity_auditor",
    "narrative_dna.synthetic_reliability",
    "narrative_dna.synthetic_reviewer",
    "narrative_dna.taxonomy",
    "narrative_dna.unit_classifier",
    "narrative_dna.validators",
]


def test_scaffold_modules_import() -> None:
    for module_name in MODULES:
        importlib.import_module(module_name)
