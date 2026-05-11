from __future__ import annotations

import os
import time
from typing import Any

from openai import OpenAI, RateLimitError

from clareval_experiment.llm.base import LLMBackend

_MAX_RETRIES = 6
_RETRY_BASE_DELAY = 3.0  # seconds
_DEFAULT_TIMEOUT_SECONDS = 600.0
_DEFAULT_MAX_TOKENS = 8192


class OpenAIBackend(LLMBackend):
    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.last_response_metadata: dict[str, Any] = {}
        self.default_max_tokens = _env_int("CLAREVAL_OPENAI_MAX_TOKENS", _DEFAULT_MAX_TOKENS)
        self.timeout_seconds = _env_float("CLAREVAL_OPENAI_TIMEOUT", _DEFAULT_TIMEOUT_SECONDS)
        self.client = OpenAI(
            base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            timeout=self.timeout_seconds,
        )

    def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        *,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> str:
        delay = _RETRY_BASE_DELAY
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            self.last_response_metadata = {
                "backend": "openai",
                "model": self.model,
                "api_attempt": attempt + 1,
                "json_mode_requested": json_mode,
                "json_mode_fallback": False,
                "max_tokens": max_tokens if max_tokens is not None else self.default_max_tokens,
                "timeout_seconds": self.timeout_seconds,
            }
            try:
                effective_max_tokens = max_tokens if max_tokens is not None else self.default_max_tokens
                kwargs = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": temperature,
                    "max_tokens": effective_max_tokens,
                }
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                try:
                    response = self.client.chat.completions.create(**kwargs)
                except Exception as exc:
                    if json_mode and "response_format" in str(exc):
                        kwargs.pop("response_format", None)
                        self.last_response_metadata["json_mode_fallback"] = True
                        self.last_response_metadata["json_mode_fallback_error"] = str(exc)
                        response = self.client.chat.completions.create(**kwargs)
                    else:
                        raise
                self.last_response_metadata.update(_response_metadata(response))
                return response.choices[0].message.content or ""
            except RateLimitError as exc:
                last_exc = exc
                self.last_response_metadata["exception"] = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
                if attempt == _MAX_RETRIES - 1:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 60.0)
            except Exception as exc:
                last_exc = exc
                self.last_response_metadata["exception"] = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
                if attempt == _MAX_RETRIES - 1:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 60.0)
        raise RuntimeError(f"All {_MAX_RETRIES} retries failed") from last_exc


def _response_metadata(response: Any) -> dict[str, Any]:
    choices = getattr(response, "choices", None) or []
    choice = choices[0] if choices else None
    usage = getattr(response, "usage", None)
    if hasattr(usage, "model_dump"):
        usage_payload = usage.model_dump()
    elif usage is not None:
        usage_payload = {
            key: getattr(usage, key, None)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            if getattr(usage, key, None) is not None
        }
    else:
        usage_payload = None

    return {
        "response_id": getattr(response, "id", None),
        "response_model": getattr(response, "model", None),
        "created": getattr(response, "created", None),
        "finish_reason": getattr(choice, "finish_reason", None) if choice is not None else None,
        "usage": usage_payload,
    }


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default
