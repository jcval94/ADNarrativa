"""OpenAI client boundary for structured LLM workflows."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from time import sleep
from typing import Any, TypeVar

from pydantic import BaseModel, Field, ValidationError

from narrative_dna.models import StrictBaseModel
from narrative_dna.timing import TimingRecorder, env_flag, json_size_chars

T = TypeVar("T", bound=BaseModel)
DEFAULT_CONFIG_PATH = Path("configs/llm_config.json")
DEFAULT_CACHE_DIR = Path(".cache/narrative_dna")
DEFAULT_BACKOFF_SECONDS = [2, 8, 20]


class LLMClientError(RuntimeError):
    """Base error for controlled LLM client failures."""


class MissingAPIKeyError(LLMClientError):
    """Raised when a live OpenAI request is attempted without a key."""


class LLMProfile(StrictBaseModel):
    model: str = Field(min_length=1)
    reasoning_effort: str | None = None
    temperature: float | None = None
    temperature_supported: bool | None = None
    timeout_seconds: int | None = Field(default=None, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    text_verbosity: str | None = None
    enabled: bool = True


class LLMCallResult(StrictBaseModel):
    ok: bool
    profile_name: str = Field(min_length=1)
    model: str = Field(min_length=1)
    cache_key: str = Field(min_length=1)
    cache_path: str | None = None
    cache_hit: bool = False
    dry_run: bool = False
    attempts: int = Field(ge=0)
    parsed: dict[str, Any] | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    response_id: str | None = None
    error_type: str | None = None
    error: str | None = None
    fallback_allowed: bool = True


class OpenAIResponsesTransport:
    """Small adapter around the official OpenAI Responses API client."""

    def __init__(self, *, api_key: str) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on runtime package state.
            raise LLMClientError("The openai package is required for live API calls.") from exc
        self._client = OpenAI(api_key=api_key)

    def __call__(self, **kwargs: Any) -> Any:
        return self._client.responses.create(**kwargs)


class OpenAIStructuredClient:
    """Structured Responses API client with Pydantic validation and cache."""

    def __init__(
        self,
        *,
        config_path: str | Path = DEFAULT_CONFIG_PATH,
        cache_dir: str | Path | None = None,
        api_key: str | None = None,
        transport: Callable[..., Any] | None = None,
        sleeper: Callable[[float], None] = sleep,
        timing_recorder: TimingRecorder | None = None,
        log_timings: bool | None = None,
    ) -> None:
        self.config_path = Path(config_path)
        self.config = load_llm_config(self.config_path)
        configured_cache = (
            self.config.get("cache", {}).get("dir") if self.config.get("cache") else None
        )
        self.cache_dir = Path(cache_dir or configured_cache or DEFAULT_CACHE_DIR)
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.transport = transport
        self.sleeper = sleeper
        timing_enabled = (
            env_flag("NARRATIVE_DNA_LOG_TIMINGS") if log_timings is None else log_timings
        )
        self.timing_recorder = timing_recorder or (
            TimingRecorder(run_id="standalone_llm", enabled=True) if timing_enabled else None
        )

    def request_structured(
        self,
        *,
        profile_name: str,
        input_payload: Mapping[str, Any] | list[Any] | str,
        response_model: type[T],
        taxonomy_version: str,
        prompt_version: str,
        validator_version: str,
        system_prompt: str | None = None,
        dry_run: bool = False,
        use_cache: bool | None = None,
    ) -> LLMCallResult:
        """Request a strict structured response and validate it with Pydantic."""

        with self._timing_span(
            "llm.request",
            profile_name=profile_name,
            response_schema=response_model.__name__,
            payload_chars=json_size_chars(input_payload),
            system_prompt_chars=len(system_prompt or ""),
            api_call_purpose=api_call_purpose(profile_name, response_model.__name__),
        ) as timing:
            profile = resolve_profile(self.config, profile_name)
            cache_enabled = self._cache_enabled(use_cache)
            timing.update(
                {
                    "model": profile.model,
                    "reasoning_effort": profile.reasoning_effort,
                    "temperature": effective_temperature(profile),
                    "text_verbosity": profile.text_verbosity,
                    "max_output_tokens": profile.max_output_tokens,
                    "timeout_seconds": profile.timeout_seconds,
                    "cache_enabled": cache_enabled,
                }
            )
            cache_key = build_cache_key(
                profile=profile,
                profile_name=profile_name,
                input_payload=input_payload,
                taxonomy_version=taxonomy_version,
                prompt_version=prompt_version,
                validator_version=validator_version,
                schema_name=response_model.__name__,
                system_prompt=system_prompt,
            )
            cache_path = self.cache_dir / f"{cache_key}.json"

            if dry_run:
                timing.update({"ok": True, "dry_run": True, "attempts": 0, "cache_hit": False})
                return LLMCallResult(
                    ok=True,
                    profile_name=profile_name,
                    model=profile.model,
                    cache_key=cache_key,
                    cache_path=str(cache_path),
                    dry_run=True,
                    attempts=0,
                    error_type="dry_run",
                    error="Dry run enabled; no OpenAI request was sent.",
                )

            if cache_enabled:
                with self._timing_span(
                    "llm.cache_read",
                    profile_name=profile_name,
                    model=profile.model,
                    cache_path=str(cache_path),
                    api_call_purpose=api_call_purpose(profile_name, response_model.__name__),
                ) as cache_timing:
                    cached = self._read_cache(cache_path, response_model=response_model)
                    cache_timing["cache_hit"] = cached is not None
                if cached is not None:
                    timing.update({"ok": True, "cache_hit": True, "attempts": cached.attempts})
                    return cached.model_copy(
                        update={
                            "profile_name": profile_name,
                            "model": profile.model,
                            "cache_key": cache_key,
                            "cache_path": str(cache_path),
                            "cache_hit": True,
                        }
                    )

            try:
                with self._timing_span(
                    "llm.transport_init",
                    profile_name=profile_name,
                    model=profile.model,
                    api_call_purpose=api_call_purpose(profile_name, response_model.__name__),
                ):
                    transport = self._transport()
            except LLMClientError as exc:
                timing.update({"ok": False, "attempts": 0, "error_type": type(exc).__name__})
                return self._error_result(
                    profile_name=profile_name,
                    profile=profile,
                    cache_key=cache_key,
                    cache_path=cache_path,
                    attempts=0,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )

            with self._timing_span(
                "llm.build_request",
                profile_name=profile_name,
                model=profile.model,
                response_schema=response_model.__name__,
                api_call_purpose=api_call_purpose(profile_name, response_model.__name__),
            ):
                kwargs = build_responses_kwargs(
                    profile=profile,
                    input_payload=input_payload,
                    response_model=response_model,
                    system_prompt=system_prompt,
                )
            max_attempts, backoff_seconds = self._retry_policy()
            last_error: str | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    with self._timing_span(
                        "openai.api_call",
                        profile_name=profile_name,
                        model=profile.model,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        openai_api_call=True,
                        api_call_purpose=api_call_purpose(
                            profile_name,
                            response_model.__name__,
                        ),
                    ):
                        response = transport(**kwargs)
                    with self._timing_span(
                        "llm.parse_validate",
                        profile_name=profile_name,
                        model=profile.model,
                        attempt=attempt,
                        api_call_purpose=api_call_purpose(profile_name, response_model.__name__),
                    ):
                        parsed_payload = extract_json_payload(response)
                        parsed_model = response_model.model_validate(parsed_payload)
                    result = LLMCallResult(
                        ok=True,
                        profile_name=profile_name,
                        model=profile.model,
                        cache_key=cache_key,
                        cache_path=str(cache_path),
                        attempts=attempt,
                        parsed=parsed_model.model_dump(mode="json"),
                        usage=extract_usage(response),
                        response_id=extract_response_id(response),
                    )
                    if cache_enabled:
                        with self._timing_span(
                            "llm.cache_write",
                            profile_name=profile_name,
                            model=profile.model,
                            cache_path=str(cache_path),
                            api_call_purpose=api_call_purpose(
                                profile_name,
                                response_model.__name__,
                            ),
                        ):
                            self._write_cache(cache_path, result)
                    timing.update({"ok": True, "cache_hit": False, "attempts": attempt})
                    return result
                except ValidationError as exc:
                    timing.update(
                        {
                            "ok": False,
                            "cache_hit": False,
                            "attempts": attempt,
                            "error_type": "schema_validation",
                        }
                    )
                    return self._error_result(
                        profile_name=profile_name,
                        profile=profile,
                        cache_key=cache_key,
                        cache_path=cache_path,
                        attempts=attempt,
                        error_type="schema_validation",
                        error=str(exc),
                    )
                except (json.JSONDecodeError, LLMClientError, ValueError) as exc:
                    timing.update(
                        {
                            "ok": False,
                            "cache_hit": False,
                            "attempts": attempt,
                            "error_type": "invalid_structured_output",
                        }
                    )
                    return self._error_result(
                        profile_name=profile_name,
                        profile=profile,
                        cache_key=cache_key,
                        cache_path=cache_path,
                        attempts=attempt,
                        error_type="invalid_structured_output",
                        error=str(exc),
                    )
                except Exception as exc:  # pragma: no cover - exercised with test fakes.
                    last_error = str(exc)
                    retryable = is_retryable_exception(exc)
                    if retryable and attempt < max_attempts:
                        delay = backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)]
                        with self._timing_span(
                            "llm.retry_sleep",
                            profile_name=profile_name,
                            model=profile.model,
                            attempt=attempt,
                            delay_seconds=delay,
                            api_call_purpose=api_call_purpose(
                                profile_name,
                                response_model.__name__,
                            ),
                        ):
                            self.sleeper(delay)
                        continue
                    timing.update(
                        {
                            "ok": False,
                            "cache_hit": False,
                            "attempts": attempt,
                            "error_type": type(exc).__name__,
                            "retryable": retryable,
                        }
                    )
                    return self._error_result(
                        profile_name=profile_name,
                        profile=profile,
                        cache_key=cache_key,
                        cache_path=cache_path,
                        attempts=attempt,
                        error_type=type(exc).__name__,
                        error=last_error,
                    )

            timing.update(
                {
                    "ok": False,
                    "cache_hit": False,
                    "attempts": max_attempts,
                    "error_type": "unknown_error",
                }
            )
            return self._error_result(
                profile_name=profile_name,
                profile=profile,
                cache_key=cache_key,
                cache_path=cache_path,
                attempts=max_attempts,
                error_type="unknown_error",
                error=last_error or "Unknown LLM client failure.",
            )

    def _timing_span(self, stage: str, **metadata: Any):
        if self.timing_recorder is None:
            return _NullTimingSpan()
        return self.timing_recorder.span(stage, **metadata)

    def _cache_enabled(self, override: bool | None) -> bool:
        if override is not None:
            return override
        return bool(self.config.get("cache", {}).get("enabled", True))

    def _retry_policy(self) -> tuple[int, list[int]]:
        retry = self.config.get("retry", {})
        max_attempts = int(retry.get("max_attempts", 3))
        backoff_seconds = list(retry.get("backoff_seconds", DEFAULT_BACKOFF_SECONDS))
        return max(1, max_attempts), [int(delay) for delay in backoff_seconds]

    def _transport(self) -> Callable[..., Any]:
        if self.transport is not None:
            return self.transport
        if not self.api_key:
            raise MissingAPIKeyError("OPENAI_API_KEY is required for live OpenAI requests.")
        self.transport = OpenAIResponsesTransport(api_key=self.api_key)
        return self.transport

    def _read_cache(self, cache_path: Path, *, response_model: type[T]) -> LLMCallResult | None:
        if not cache_path.exists():
            return None
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            result = LLMCallResult.model_validate(payload)
            if result.parsed is not None:
                response_model.model_validate(result.parsed)
            return result
        except (json.JSONDecodeError, ValidationError):
            return None

    def _write_cache(self, cache_path: Path, result: LLMCallResult) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                result.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True
            ),
            encoding="utf-8",
        )

    def _error_result(
        self,
        *,
        profile_name: str,
        profile: LLMProfile,
        cache_key: str,
        cache_path: Path,
        attempts: int,
        error_type: str,
        error: str,
    ) -> LLMCallResult:
        return LLMCallResult(
            ok=False,
            profile_name=profile_name,
            model=profile.model,
            cache_key=cache_key,
            cache_path=str(cache_path),
            attempts=attempts,
            error_type=error_type,
            error=error,
            fallback_allowed=True,
        )


def load_llm_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load llm_config.json without exposing secrets."""

    path = Path(config_path)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise LLMClientError("llm_config.json must contain a JSON object.")
    return payload


def resolve_profile(config: Mapping[str, Any], profile_name: str) -> LLMProfile:
    """Resolve top-level, legacy models.*, or named synthetic reviewer profiles."""

    if isinstance(config.get(profile_name), dict):
        return LLMProfile.model_validate(config[profile_name])
    models = config.get("models")
    if isinstance(models, dict) and isinstance(models.get(profile_name), dict):
        return LLMProfile.model_validate(models[profile_name])
    reviewers = config.get("synthetic_reviewers")
    if isinstance(reviewers, list):
        for reviewer in reviewers:
            if isinstance(reviewer, dict) and reviewer.get("name") == profile_name:
                payload = dict(reviewer)
                payload.pop("name", None)
                return LLMProfile.model_validate(payload)
    raise LLMClientError(f"unknown LLM profile: {profile_name}")


def api_call_purpose(profile_name: str, response_schema: str) -> str:
    """Explain why an OpenAI request is needed for timing logs."""

    by_profile = {
        "main_classifier": (
            "classify one narrative unit into strict JSON fields before deriving notation"
        ),
        "adjudicator": "review a high-risk unit conservatively before final notation",
        "synthetic_aggregator": "aggregate synthetic reviewer disagreements conservatively",
        "synthetic_final_adjudicator": "make final conservative synthetic-gold decision",
    }
    if profile_name in by_profile:
        return by_profile[profile_name]
    if response_schema == "SyntheticReviewerOutput":
        return "diversify synthetic review of a difficult or boundary-case annotation"
    return f"request strict structured output for {response_schema}"


def effective_temperature(profile: LLMProfile) -> float | None:
    """Return the temperature value that should actually be sent to the API."""

    if profile.temperature is None:
        return None
    if profile.temperature_supported is not None:
        return profile.temperature if profile.temperature_supported else None
    if is_gpt5_reasoning_model(profile.model):
        return None
    return profile.temperature


def is_gpt5_reasoning_model(model: str) -> bool:
    return model.lower().startswith("gpt-5")


def is_retryable_exception(exc: Exception) -> bool:
    """Classify transport errors conservatively to avoid retrying bad requests."""

    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code in {408, 409, 429} or status_code >= 500

    message = str(exc).lower()
    if (
        "unsupported parameter" in message
        or "invalid_request" in message
        or "bad request" in message
        or "error code: 400" in message
    ):
        return False
    retry_markers = (
        "rate_limit",
        "rate limit",
        "timeout",
        "timed out",
        "temporarily",
        "connection",
        "server error",
        "service unavailable",
    )
    return any(marker in message for marker in retry_markers)


def build_responses_kwargs(
    *,
    profile: LLMProfile,
    input_payload: Mapping[str, Any] | list[Any] | str,
    response_model: type[BaseModel],
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Build a Responses API request that only accepts strict structured output."""

    text_config: dict[str, Any] = {"format": build_text_format(response_model)}
    if profile.text_verbosity:
        text_config["verbosity"] = profile.text_verbosity
    request: dict[str, Any] = {
        "model": profile.model,
        "input": build_responses_input(input_payload, system_prompt=system_prompt),
        "text": text_config,
    }
    if profile.reasoning_effort:
        request["reasoning"] = {"effort": profile.reasoning_effort}
    if effective_temperature(profile) is not None:
        request["temperature"] = effective_temperature(profile)
    if profile.max_output_tokens is not None:
        request["max_output_tokens"] = profile.max_output_tokens
    if profile.timeout_seconds is not None:
        request["timeout"] = profile.timeout_seconds
    return request


def build_responses_input(
    input_payload: Mapping[str, Any] | list[Any] | str,
    *,
    system_prompt: str | None,
) -> list[dict[str, str]]:
    user_content = (
        input_payload
        if isinstance(input_payload, str)
        else json.dumps(input_payload, ensure_ascii=False, sort_keys=True)
    )
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append(
        {
            "role": "user",
            "content": f"Return JSON that matches the provided strict schema.\n\n{user_content}",
        }
    )
    return messages


def build_text_format(response_model: type[BaseModel]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": _schema_name(response_model),
        "strict": True,
        "schema": prepare_openai_json_schema(response_model.model_json_schema()),
    }


def prepare_openai_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Trim common Pydantic metadata while preserving strict JSON object contracts."""

    cleaned = _clean_schema_node(schema)
    if cleaned.get("type") == "object":
        cleaned["additionalProperties"] = False
        properties = cleaned.get("properties")
        if isinstance(properties, dict):
            cleaned["required"] = list(properties.keys())
    return cleaned


def build_cache_key(
    *,
    profile: LLMProfile,
    profile_name: str,
    input_payload: Mapping[str, Any] | list[Any] | str,
    taxonomy_version: str,
    prompt_version: str,
    validator_version: str,
    schema_name: str,
    system_prompt: str | None,
) -> str:
    cache_payload = {
        "profile_name": profile_name,
        "model": profile.model,
        "reasoning_effort": profile.reasoning_effort,
        "temperature": effective_temperature(profile),
        "text_verbosity": profile.text_verbosity,
        "max_output_tokens": profile.max_output_tokens,
        "timeout_seconds": profile.timeout_seconds,
        "taxonomy_version": taxonomy_version,
        "prompt_version": prompt_version,
        "validator_version": validator_version,
        "schema_name": schema_name,
        "system_prompt": system_prompt,
        "input_payload": input_payload,
    }
    encoded = json.dumps(cache_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def extract_json_payload(response: Any) -> dict[str, Any]:
    """Extract JSON object output from Responses API response objects or test doubles."""

    if isinstance(response, dict):
        if "refusal" in response and response["refusal"]:
            raise LLMClientError("model refused the request")
        if isinstance(response.get("parsed"), dict):
            return response["parsed"]
        if isinstance(response.get("output_parsed"), dict):
            return response["output_parsed"]
        if isinstance(response.get("output_text"), str):
            payload = json.loads(response["output_text"])
            if not isinstance(payload, dict):
                raise ValueError("structured output must be a JSON object")
            return payload
        if isinstance(response.get("data"), dict):
            return response["data"]
        output_payload = _extract_from_output_items(response.get("output"))
        if output_payload is not None:
            return output_payload

    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str):
        payload = json.loads(output_text)
        if not isinstance(payload, dict):
            raise ValueError("structured output must be a JSON object")
        return payload
    output_parsed = getattr(response, "output_parsed", None)
    if isinstance(output_parsed, dict):
        return output_parsed
    output_payload = _extract_from_output_items(getattr(response, "output", None))
    if output_payload is not None:
        return output_payload
    raise LLMClientError("Responses API returned no structured JSON payload.")


def extract_usage(response: Any) -> dict[str, Any]:
    usage = (
        response.get("usage") if isinstance(response, dict) else getattr(response, "usage", None)
    )
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return dict(usage)
    if hasattr(usage, "model_dump"):
        return usage.model_dump(mode="json")
    return dict(vars(usage))


def extract_response_id(response: Any) -> str | None:
    response_id = (
        response.get("id") if isinstance(response, dict) else getattr(response, "id", None)
    )
    return str(response_id) if response_id else None


def _extract_from_output_items(output: Any) -> dict[str, Any] | None:
    if not isinstance(output, list):
        return None
    for item in output:
        content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
        if not isinstance(content, list):
            continue
        for content_item in content:
            kind = (
                content_item.get("type")
                if isinstance(content_item, dict)
                else getattr(content_item, "type", None)
            )
            if kind == "refusal":
                raise LLMClientError("model refused the request")
            text = (
                content_item.get("text")
                if isinstance(content_item, dict)
                else getattr(content_item, "text", None)
            )
            if isinstance(text, str):
                payload = json.loads(text)
                if not isinstance(payload, dict):
                    raise ValueError("structured output must be a JSON object")
                return payload
    return None


def _clean_schema_node(node: Any) -> Any:
    unsupported = {
        "title",
        "default",
        "examples",
        "format",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "pattern",
        "minItems",
        "maxItems",
    }
    if isinstance(node, dict):
        cleaned: dict[str, Any] = {}
        for key, value in node.items():
            if key in unsupported:
                continue
            cleaned[key] = _clean_schema_node(value)
        if cleaned.get("type") == "object":
            cleaned["additionalProperties"] = False
            properties = cleaned.get("properties")
            if isinstance(properties, dict):
                cleaned["required"] = list(properties.keys())
        return cleaned
    if isinstance(node, list):
        return [_clean_schema_node(item) for item in node]
    return node


def _schema_name(response_model: type[BaseModel]) -> str:
    name = response_model.__name__
    safe = "".join(char if char.isalnum() or char in "_-" else "_" for char in name)
    return safe[:64] or "structured_response"


class _NullTimingSpan:
    def __enter__(self) -> dict[str, Any]:
        return {}

    def __exit__(self, *_exc_info: Any) -> bool:
        return False
