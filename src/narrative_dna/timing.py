"""Timing instrumentation helpers for auditable pipeline runs."""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

LOGGER = logging.getLogger("narrative_dna.timing")
DEFAULT_TOP_BOTTLENECKS = 10


@dataclass(frozen=True)
class TimingRecord:
    """One measured execution span."""

    stage: str
    duration_ms: float
    started_at_utc: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "duration_ms": round(self.duration_ms, 3),
            "started_at_utc": self.started_at_utc,
            "metadata": _json_safe(self.metadata),
        }


class TimingRecorder:
    """Collect and optionally echo timing records during a run."""

    def __init__(
        self,
        *,
        run_id: str,
        enabled: bool = True,
        echo: bool = True,
        printer: Callable[[str], None] = print,
    ) -> None:
        self.run_id = run_id
        self.enabled = enabled
        self.echo = echo
        self.printer = printer
        self.records: list[TimingRecord] = []

    @contextmanager
    def span(self, stage: str, **metadata: Any) -> Iterator[dict[str, Any]]:
        """Measure a code block and record metadata filled in by the caller."""

        if not self.enabled:
            yield {}
            return

        extra: dict[str, Any] = {}
        started_at_utc = datetime.now(UTC).isoformat()
        start = perf_counter()
        try:
            yield extra
        except Exception as exc:
            extra.setdefault("ok", False)
            extra.setdefault("error_type", type(exc).__name__)
            raise
        finally:
            self.record(
                stage,
                duration_ms=(perf_counter() - start) * 1000,
                started_at_utc=started_at_utc,
                **metadata,
                **extra,
            )

    def record(
        self,
        stage: str,
        *,
        duration_ms: float,
        started_at_utc: str | None = None,
        **metadata: Any,
    ) -> None:
        if not self.enabled:
            return
        record = TimingRecord(
            stage=stage,
            duration_ms=duration_ms,
            started_at_utc=started_at_utc or datetime.now(UTC).isoformat(),
            metadata={key: value for key, value in metadata.items() if value is not None},
        )
        self.records.append(record)
        message = format_timing_record(record)
        LOGGER.info(message)
        if self.echo:
            self.printer(message)

    def report(
        self,
        *,
        taxonomy_version_effective: str,
        prompt_version_effective: str,
        validator_version_effective: str,
        top_bottlenecks: int = DEFAULT_TOP_BOTTLENECKS,
    ) -> dict[str, Any]:
        records = [record.as_dict() for record in self.records]
        return {
            "run_id": self.run_id,
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "taxonomy_version_effective": taxonomy_version_effective,
            "prompt_version_effective": prompt_version_effective,
            "validator_version_effective": validator_version_effective,
            "record_count": len(records),
            "summary_by_stage": summarize_records(records),
            "bottlenecks": slowest_records(records, limit=top_bottlenecks),
            "records": records,
        }


def write_timing_report(
    path: str | Path,
    recorder: TimingRecorder,
    *,
    taxonomy_version_effective: str,
    prompt_version_effective: str,
    validator_version_effective: str,
) -> Path:
    """Write an auditable JSON timing report for the run."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = recorder.report(
        taxonomy_version_effective=taxonomy_version_effective,
        prompt_version_effective=prompt_version_effective,
        validator_version_effective=validator_version_effective,
    )
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return destination


def summarize_records(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for record in records:
        buckets[str(record["stage"])].append(float(record["duration_ms"]))

    summary: dict[str, dict[str, Any]] = {}
    for stage, durations in sorted(buckets.items()):
        total = sum(durations)
        summary[stage] = {
            "count": len(durations),
            "total_ms": round(total, 3),
            "avg_ms": round(total / len(durations), 3),
            "max_ms": round(max(durations), 3),
        }
    return summary


def slowest_records(records: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    return sorted(records, key=lambda record: float(record["duration_ms"]), reverse=True)[:limit]


def format_timing_record(record: TimingRecord) -> str:
    fields = [f"stage={record.stage}", f"duration_ms={record.duration_ms:.1f}"]
    for key, value in record.metadata.items():
        if isinstance(value, float):
            rendered = f"{value:.3f}"
        else:
            rendered = str(value)
        fields.append(f"{key}={rendered}")
    return "[timing] " + " ".join(fields)


def json_size_chars(payload: Mapping[str, Any] | list[Any] | str) -> int:
    if isinstance(payload, str):
        return len(payload)
    return len(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def env_flag(name: str, *, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple | set):
        return [_json_safe(item) for item in value]
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value
