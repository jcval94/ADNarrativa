# Golden Regression Fixtures

These fixtures are intentionally small and conservative. They represent
`synthetic_gold_high_confidence` records only, because medium-confidence or
rejected synthetic outputs are not allowed as regression truth.

The compact notation in `expected_notation_sequences.json` is not an editable
source of truth. Tests re-derive it from the strict `NarrativeUnit` JSON fields
and fail if the derived notation diverges.
