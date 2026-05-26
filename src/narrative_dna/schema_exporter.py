"""JSON Schema export helpers for Pydantic contracts."""

from __future__ import annotations

import json
from pathlib import Path

from narrative_dna.models import SCHEMA_MODELS


def export_schemas(output_dir: str | Path = "schemas") -> list[Path]:
    """Write JSON Schema files for all public contract models."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for filename, model in SCHEMA_MODELS.items():
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        path = destination / filename
        path.write_text(
            json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written
