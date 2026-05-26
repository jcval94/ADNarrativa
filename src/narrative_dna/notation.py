"""Deterministic compact notation compiler."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from narrative_dna.models import NarrativeUnit

TAXONOMY_FUNCTION_ORDER = [
    "A",
    "K",
    "O",
    "F",
    "Y",
    "D",
    "Q",
    "P",
    "R",
    "E",
    "H",
    "G",
    "C",
    "B",
    "X",
    "T",
    "M",
    "L",
    "Z",
    "S",
    "I",
    "U",
    "V",
    "N",
]
CERTAINTY_SYMBOLS = {
    "none": "",
    "strong": "!",
    "tentative": "~",
    "uncertain": "?",
}
STANCE_SYMBOLS = {
    "positive": "+",
    "negative": "-",
    "mixed": "±",
    "neutral": "0",
}
TAXONOMY_ORDER_INDEX = {code: index for index, code in enumerate(TAXONOMY_FUNCTION_ORDER)}


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _get(source: NarrativeUnit | Mapping[str, Any], key: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key)


def normalize_function_codes(functions: list[Any]) -> list[str]:
    """Deduplicate and sort functions according to taxonomy order."""

    seen: set[str] = set()
    codes: list[str] = []
    for function in functions:
        code = str(_value(function))
        if code not in seen:
            seen.add(code)
            codes.append(code)
    return sorted(codes, key=lambda code: TAXONOMY_ORDER_INDEX.get(code, len(TAXONOMY_ORDER_INDEX)))


def compile_notation(
    unit: NarrativeUnit | Mapping[str, Any],
    *,
    always_parentheses: bool = False,
) -> str:
    """Compile compact notation from validated JSON fields."""

    functions = normalize_function_codes(list(_get(unit, "functions") or ["N"]))
    certainty = str(_value(_get(unit, "certainty") or "none"))
    emotion = str(_value(_get(unit, "emotion_expressed") or "N"))
    intensity = int(
        _get(unit, "emotion_intensity") if _get(unit, "emotion_intensity") is not None else 0
    )
    stance = str(_value(_get(unit, "stance") or "neutral"))

    if not 0 <= intensity <= 3:
        raise ValueError("emotion_intensity must be between 0 and 3")
    if certainty not in CERTAINTY_SYMBOLS:
        raise ValueError(f"unknown certainty: {certainty}")
    if stance not in STANCE_SYMBOLS:
        raise ValueError(f"unknown stance: {stance}")

    function_text = "+".join(functions)
    if always_parentheses or len(functions) > 1:
        function_text = f"({function_text})"

    certainty_symbol = CERTAINTY_SYMBOLS[certainty]
    stance_symbol = STANCE_SYMBOLS[stance]
    return f"{function_text}{certainty_symbol}_{emotion}{intensity}{{{stance_symbol}}}"


def derive_final_notation(
    unit: NarrativeUnit | Mapping[str, Any],
    *,
    always_parentheses: bool = False,
) -> str:
    """Alias used by validators to make derivation explicit."""

    return compile_notation(unit, always_parentheses=always_parentheses)
