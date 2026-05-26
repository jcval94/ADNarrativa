from __future__ import annotations

import pytest

from narrative_dna.notation import compile_notation, normalize_function_codes


def test_compile_multifunction_examples_exactly() -> None:
    assert (
        compile_notation(
            {
                "functions": ["V", "P"],
                "certainty": "none",
                "emotion_expressed": "S",
                "emotion_intensity": 1,
                "stance": "neutral",
            }
        )
        == "(P+V)_S1{0}"
    )
    assert (
        compile_notation(
            {
                "functions": ["Y", "K"],
                "certainty": "strong",
                "emotion_expressed": "E",
                "emotion_intensity": 2,
                "stance": "negative",
            }
        )
        == "(K+Y)!_E2{-}"
    )
    assert (
        compile_notation(
            {
                "functions": ["U", "I", "S"],
                "certainty": "none",
                "emotion_expressed": "C",
                "emotion_intensity": 1,
                "stance": "positive",
            }
        )
        == "(S+I+U)_C1{+}"
    )


def test_compile_single_function_without_parentheses_by_default() -> None:
    assert (
        compile_notation(
            {
                "functions": ["N"],
                "certainty": "none",
                "emotion_expressed": "N",
                "emotion_intensity": 0,
                "stance": "neutral",
            }
        )
        == "N_N0{0}"
    )


def test_compile_single_function_with_parentheses_when_configured() -> None:
    assert (
        compile_notation(
            {
                "functions": ["K"],
                "certainty": "none",
                "emotion_expressed": "N",
                "emotion_intensity": 1,
                "stance": "neutral",
            },
            always_parentheses=True,
        )
        == "(K)_N1{0}"
    )


def test_normalize_functions_deduplicates_and_sorts_by_taxonomy() -> None:
    assert normalize_function_codes(["V", "P", "P", "K"]) == ["K", "P", "V"]


def test_compile_rejects_bad_intensity() -> None:
    with pytest.raises(ValueError):
        compile_notation(
            {
                "functions": ["K"],
                "certainty": "none",
                "emotion_expressed": "N",
                "emotion_intensity": 4,
                "stance": "neutral",
            }
        )
