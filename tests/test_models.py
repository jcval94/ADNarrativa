from __future__ import annotations


def test_models_module_imports() -> None:
    import narrative_dna.models

    assert narrative_dna.models.__doc__
