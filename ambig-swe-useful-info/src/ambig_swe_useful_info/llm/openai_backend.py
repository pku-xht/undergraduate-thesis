from __future__ import annotations

import os
import time

from openai import OpenAI, RateLimitError

from ambig_swe_useful_info.llm.base import LLMBackend

_MAX_RETRIES = 6
_RETRY_BASE_DELAY = 3.0
_DEFAULT_TIMEOUT_SECONDS = 600.0


def _resolve_max_tokens() -> int | None:
    raw = os.environ.get("AMBIG_SWE_MAX_TOKENS") or os.environ.get("OPENAI_MAX_TOKENS")
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _resolve_timeout(timeout: float | None = None) -> float:
    if timeout is not None:
        return float(timeout)
    raw = os.environ.get("AMBIG_SWE_REQUEST_TIMEOUT") or os.environ.get("OPENAI_REQUEST_TIMEOUT")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return _DEFAULT_TIMEOUT_SECONDS


def _uses_json_mode(system: str) -> bool:
    lowered = system.lower()
    return (
        "return only valid json" in lowered
        or "return json only" in lowered
        or "return json" in lowered
    )


class OpenAIBackend(LLMBackend):
    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.model = model
        self.max_tokens = _resolve_max_tokens()
        self.client = OpenAI(
            base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            timeout=_resolve_timeout(timeout),
        )

    def complete(self, system: str, user: str, temperature: float = 0.2) -> str:
        delay = _RETRY_BASE_DELAY
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                kwargs = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": temperature,
                }
                if _uses_json_mode(system):
                    kwargs["response_format"] = {"type": "json_object"}
                if self.max_tokens is not None:
                    kwargs["max_tokens"] = self.max_tokens
                response = self.client.chat.completions.create(**kwargs)
                return response.choices[0].message.content or ""
            except RateLimitError as exc:
                last_exc = exc
                if attempt == _MAX_RETRIES - 1:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 60.0)
            except Exception as exc:
                last_exc = exc
                if attempt == _MAX_RETRIES - 1:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 60.0)
        raise RuntimeError(f"All {_MAX_RETRIES} retries failed") from last_exc

