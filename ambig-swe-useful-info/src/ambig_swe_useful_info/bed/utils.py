from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Generator, Iterable


def safe_json_loads(text: str, fallback: dict) -> dict:
    """Parse JSON, tolerating markdown code fences and leading/trailing whitespace."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner_lines = []
        for line in lines[1:]:
            if line.strip() == "```":
                break
            inner_lines.append(line)
        text = "\n".join(inner_lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for start_char, end_char in [('{', '}'), ('[', ']')]:
            start = text.find(start_char)
            end = text.rfind(end_char)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
        return fallback


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


def iter_jsonl_records(path: Path) -> Generator[dict, None, None]:
    """Yield JSON records from a file, supporting both compact (one-per-line)
    and pretty-printed (indented, multi-line) JSONL formats."""
    text = path.read_text(encoding="utf-8", errors="replace")
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        while idx < len(text) and text[idx] in " \t\n\r":
            idx += 1
        if idx >= len(text):
            break
        try:
            obj, end_idx = decoder.raw_decode(text, idx)
            idx = end_idx
            if not isinstance(obj, dict):
                raise ValueError(
                    f"Expected JSON object in {path}, got {type(obj).__name__}."
                )
            yield obj
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON output file: {path}") from exc

