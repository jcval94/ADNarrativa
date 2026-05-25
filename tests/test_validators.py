from __future__ import annotations


def test_validators_module_imports() -> None:
    import narrative_dna.validators

    assert narrative_dna.validators.__doc__
