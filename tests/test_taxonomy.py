from __future__ import annotations


def test_taxonomy_module_imports() -> None:
    import narrative_dna.taxonomy

    assert narrative_dna.taxonomy.__doc__
