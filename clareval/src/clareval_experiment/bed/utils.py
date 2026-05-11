from __future__ import annotations

import json
import math
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Generator, Iterable


UNKNOWN_OR_IRRELEVANT_ANSWER = "irrelevant or unknown"


class LLMOutputError(ValueError):
    """Raised when a structured LLM response is invalid after retry."""


def strict_json_loads(text: str) -> dict:
    """Parse a JSON object, tolerating markdown fences, and raise on failure."""
    parsed = _load_json_object(text)
    if parsed is None:
        raise LLMOutputError(f"Could not parse valid JSON object from LLM output: {_excerpt(text)}")
    return parsed


def complete_json_with_retry(
    backend,
    system: str,
    user: str,
    temperature: float,
    *,
    context: str,
    validate: Callable[[dict], None] | None = None,
    attempts: int = 2,
    json_mode: bool = True,
    max_tokens: int | None = None,
) -> dict:
    """Call an LLM for JSON, retrying once when parsing or validation fails."""
    last_error: Exception | None = None
    last_raw = ""
    response_metadata: list[dict] = []
    for attempt in range(attempts):
        retry_suffix = ""
        if attempt:
            retry_suffix = (
                "\n\nYour previous response had invalid JSON or did not match the required schema. "
                f"Validation error: {last_error}\n"
                "Return exactly one valid JSON object following the schema. No Markdown."
            )
        last_raw = backend.complete(
            system,
            user + retry_suffix,
            temperature,
            json_mode=json_mode,
            max_tokens=max_tokens,
        )
        metadata = _backend_response_metadata(backend)
        if metadata:
            response_metadata.append(metadata)
        try:
            payload = strict_json_loads(last_raw)
            if validate is not None:
                validate(payload)
            return payload
        except (LLMOutputError, ValueError) as exc:
            last_error = exc

    raise LLMOutputError(
        f"{context} failed after {attempts} attempts: {last_error}. "
        f"Last output: {_excerpt(last_raw)}"
        f"{_format_response_metadata(response_metadata)}"
    )


def _load_json_object(text: str) -> dict | None:
    text = text.strip()
    candidates = [text]
    for block in re.findall(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE):
        candidates.append(block.strip())

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start:end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _excerpt(text: str, limit: int = 240) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    return collapsed[:limit] + ("..." if len(collapsed) > limit else "")


def _backend_response_metadata(backend) -> dict | None:
    metadata = getattr(backend, "last_response_metadata", None)
    return metadata if isinstance(metadata, dict) and metadata else None


def _format_response_metadata(metadata: list[dict]) -> str:
    if not metadata:
        return ""
    try:
        payload = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    except TypeError:
        payload = repr(metadata)
    return f". Response metadata: {payload}"


def normalize(dist: dict[str, float]) -> dict[str, float]:
    total = sum(max(v, 0.0) for v in dist.values())
    if total <= 0:
        size = max(len(dist), 1)
        return {k: 1.0 / size for k in dist}
    return {k: max(v, 0.0) / total for k, v in dist.items()}


def entropy(values: Iterable[float]) -> float:
    score = 0.0
    for value in values:
        if value > 0:
            score -= value * math.log(value, 2)
    return score


def constrain_simulator_answer(answer: str, premises: list[str]) -> str:
    """Constrain simulated-user output to the allowed answer set."""
    stripped = answer.strip()
    fallback = UNKNOWN_OR_IRRELEVANT_ANSWER
    if stripped == fallback:
        return fallback
    if stripped.lower() == fallback:
        return fallback
    lowered = stripped.lower()
    if "unknown" in lowered or "irrelevant" in lowered or "not important" in lowered:
        return fallback

    for premise in premises:
        if stripped == premise or premise in stripped:
            return premise

    if not premises:
        return fallback

    best = max(
        premises,
        key=lambda premise: SequenceMatcher(None, _norm_text(stripped), _norm_text(premise)).ratio(),
    )
    score = SequenceMatcher(None, _norm_text(stripped), _norm_text(best)).ratio()
    return best if score >= 0.25 else fallback


def _norm_text(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def iter_jsonl_records(path: Path) -> Generator[dict, None, None]:
    """Yield JSON records from a file, supporting both compact (one-per-line)
    and pretty-printed (indented, multi-line) JSONL formats."""
    text = path.read_text(encoding="utf-8", errors="replace")
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        # Skip whitespace between records
        while idx < len(text) and text[idx] in " \t\n\r":
            idx += 1
        if idx >= len(text):
            break
        try:
            obj, end_idx = decoder.raw_decode(text, idx)
            idx = end_idx
            yield obj
        except json.JSONDecodeError:
            break
