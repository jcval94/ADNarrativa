from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from narrative_dna.llm_client import (
    OpenAIStructuredClient,
    api_call_purpose,
    build_cache_key,
    build_responses_kwargs,
    build_text_format,
    load_llm_config,
    prepare_openai_json_schema,
    resolve_profile,
)
from narrative_dna.timing import TimingRecorder


class TinyClassification(BaseModel):
    label: str
    confidence: float = Field(ge=0, le=1)


class CountingTransport:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def write_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "main_classifier": {
                    "model": "gpt-5.5",
                    "reasoning_effort": "medium",
                    "temperature": 0.1,
                },
                "adjudicator": {
                    "model": "gpt-5.5",
                    "reasoning_effort": "high",
                    "temperature": 0.0,
                },
                "cache": {"enabled": True, "dir": str(path.parent / "cache")},
                "retry": {"max_attempts": 2, "backoff_seconds": [0, 0]},
            }
        ),
        encoding="utf-8",
    )


def client(tmp_path: Path, transport: CountingTransport) -> OpenAIStructuredClient:
    config_path = tmp_path / "llm_config.json"
    write_config(config_path)
    return OpenAIStructuredClient(
        config_path=config_path,
        cache_dir=tmp_path / "cache",
        api_key="test-key",
        transport=transport,
        sleeper=lambda _: None,
    )


def request(client_: OpenAIStructuredClient):
    return client_.request_structured(
        profile_name="main_classifier",
        input_payload={"unit_id": "u1", "text": "Por que importa?"},
        response_model=TinyClassification,
        taxonomy_version="v1_0",
        prompt_version="v1_0",
        validator_version="v1_0",
        system_prompt="Classify as JSON.",
    )


def test_cache_miss_calls_responses_api_and_writes_cache(tmp_path: Path) -> None:
    transport = CountingTransport(
        [
            {
                "id": "resp_1",
                "output_text": '{"label":"P","confidence":0.92}',
                "usage": {"input_tokens": 5},
            }
        ]
    )
    result = request(client(tmp_path, transport))

    assert result.ok is True
    assert result.cache_hit is False
    assert result.parsed == {"label": "P", "confidence": 0.92}
    assert result.usage == {"input_tokens": 5}
    assert len(transport.calls) == 1
    assert Path(result.cache_path).exists()


def test_cache_hit_skips_transport(tmp_path: Path) -> None:
    first_transport = CountingTransport(
        [{"id": "resp_1", "output_text": '{"label":"P","confidence":0.92}'}]
    )
    first = request(client(tmp_path, first_transport))
    second_transport = CountingTransport([])
    second = request(client(tmp_path, second_transport))

    assert first.ok is True
    assert second.ok is True
    assert second.cache_hit is True
    assert second.parsed == {"label": "P", "confidence": 0.92}
    assert second_transport.calls == []


def test_invalid_schema_response_returns_controlled_error(tmp_path: Path) -> None:
    transport = CountingTransport([{"output_text": '{"label":"P"}'}])

    result = request(client(tmp_path, transport))

    assert result.ok is False
    assert result.error_type == "schema_validation"
    assert result.fallback_allowed is True


def test_retry_on_transient_transport_error(tmp_path: Path) -> None:
    transport = CountingTransport(
        [RuntimeError("rate_limit"), {"output_text": '{"label":"P","confidence":0.8}'}]
    )

    result = request(client(tmp_path, transport))

    assert result.ok is True
    assert result.attempts == 2
    assert len(transport.calls) == 2


def test_openai_api_call_timing_records_purpose(tmp_path: Path) -> None:
    transport = CountingTransport(
        [{"id": "resp_1", "output_text": '{"label":"P","confidence":0.92}'}]
    )
    config_path = tmp_path / "llm_config.json"
    write_config(config_path)
    timing = TimingRecorder(run_id="timing_test", enabled=True, echo=False)
    client_ = OpenAIStructuredClient(
        config_path=config_path,
        cache_dir=tmp_path / "cache",
        api_key="test-key",
        transport=transport,
        sleeper=lambda _: None,
        timing_recorder=timing,
    )

    result = request(client_)

    api_records = [record for record in timing.records if record.stage == "openai.api_call"]
    assert result.ok is True
    assert len(api_records) == 1
    assert api_records[0].metadata["openai_api_call"] is True
    assert api_records[0].metadata["api_call_purpose"] == api_call_purpose(
        "main_classifier",
        "TinyClassification",
    )


def test_dry_run_skips_transport_and_cache(tmp_path: Path) -> None:
    transport = CountingTransport([])
    client_ = client(tmp_path, transport)

    result = client_.request_structured(
        profile_name="main_classifier",
        input_payload={"unit_id": "u1"},
        response_model=TinyClassification,
        taxonomy_version="v1_0",
        prompt_version="v1_0",
        validator_version="v1_0",
        dry_run=True,
    )

    assert result.ok is True
    assert result.dry_run is True
    assert result.attempts == 0
    assert transport.calls == []
    assert not Path(result.cache_path).exists()


def test_missing_api_key_returns_controlled_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config_path = tmp_path / "llm_config.json"
    write_config(config_path)
    client_ = OpenAIStructuredClient(
        config_path=config_path,
        cache_dir=tmp_path / "cache",
        api_key=None,
        transport=None,
    )

    result = client_.request_structured(
        profile_name="main_classifier",
        input_payload={"unit_id": "u1"},
        response_model=TinyClassification,
        taxonomy_version="v1_0",
        prompt_version="v1_0",
        validator_version="v1_0",
    )

    assert result.ok is False
    assert result.error_type == "MissingAPIKeyError"
    assert result.fallback_allowed is True


def test_request_uses_strict_json_schema_format(tmp_path: Path) -> None:
    config_path = tmp_path / "llm_config.json"
    write_config(config_path)
    config = load_llm_config(config_path)
    profile = resolve_profile(config, "main_classifier")

    kwargs = build_responses_kwargs(
        profile=profile,
        input_payload={"text": "demo"},
        response_model=TinyClassification,
        system_prompt="Return JSON.",
    )

    assert kwargs["model"] == "gpt-5.5"
    assert kwargs["text"]["format"]["type"] == "json_schema"
    assert kwargs["text"]["format"]["strict"] is True
    assert kwargs["reasoning"] == {"effort": "medium"}
    assert kwargs["temperature"] == 0.1


def test_cache_key_includes_versions_and_model_fields() -> None:
    profile = resolve_profile(
        {
            "main_classifier": {
                "model": "gpt-5.5",
                "reasoning_effort": "medium",
                "temperature": 0.1,
            }
        },
        "main_classifier",
    )

    key_a = build_cache_key(
        profile=profile,
        profile_name="main_classifier",
        input_payload={"text": "same"},
        taxonomy_version="v1_0",
        prompt_version="v1_0",
        validator_version="v1_0",
        schema_name="TinyClassification",
        system_prompt=None,
    )
    key_b = build_cache_key(
        profile=profile,
        profile_name="main_classifier",
        input_payload={"text": "same"},
        taxonomy_version="v1_1",
        prompt_version="v1_0",
        validator_version="v1_0",
        schema_name="TinyClassification",
        system_prompt=None,
    )

    assert key_a != key_b


def test_openai_schema_removes_pydantic_metadata_and_forbids_extra_fields() -> None:
    text_format = build_text_format(TinyClassification)
    schema = prepare_openai_json_schema(TinyClassification.model_json_schema())

    assert text_format["name"] == "TinyClassification"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["label", "confidence"]
    assert "title" not in schema
