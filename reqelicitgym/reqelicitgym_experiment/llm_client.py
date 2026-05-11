"""Small OpenAI-compatible client helpers for the ReqElicitGym experiment."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, Optional

from openai import OpenAI


def parse_json_object(text: str) -> Dict[str, Any]:
    """Parse a JSON object from a model response."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced = re.findall(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    for block in fenced:
        try:
            return json.loads(block.strip())
        except json.JSONDecodeError:
            continue

    braces = re.findall(r"\{.*\}", text, flags=re.DOTALL)
    for block in braces:
        try:
            return json.loads(block.strip())
        except json.JSONDecodeError:
            continue
    return {}


class LLMClient:
    """Thin wrapper around an OpenAI-compatible chat completions endpoint."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        timeout: float = 90.0,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                kwargs: Dict[str, Any] = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": self.temperature if temperature is None else temperature,
                    "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
                    "timeout": self.timeout,
                }
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                response = self.client.chat.completions.create(**kwargs)
                return response.choices[0].message.content.strip()
            except Exception as exc:  # pragma: no cover - network behavior
                last_error = exc
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"LLM call failed after 3 attempts: {last_error}") from last_error

    def json(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> Dict[str, Any]:
        text = self.chat(system_prompt, user_prompt, json_mode=True, **kwargs)
        parsed = parse_json_object(text)
        if not parsed:
            repair_system_prompt = (
                f"{system_prompt}\n\nYour previous response was not parseable JSON. "
                "Return a single valid JSON object only, with no Markdown."
            )
            text = self.chat(repair_system_prompt, user_prompt, json_mode=True, **kwargs)
            parsed = parse_json_object(text)
        if not parsed:
            raise ValueError(f"Model did not return parseable JSON: {text[:500]}")
        return parsed

    def json_once(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> Dict[str, Any]:
        """Call once and parse one JSON object without repair prompting."""
        text = self.chat(system_prompt, user_prompt, json_mode=True, **kwargs)
        try:
            parsed = json.loads(text.strip())
        except json.JSONDecodeError:
            raise ValueError(f"Model did not return parseable JSON: {text[:500]}")
        if not isinstance(parsed, dict):
            raise ValueError(f"Model did not return a JSON object: {text[:500]}")
        return parsed
