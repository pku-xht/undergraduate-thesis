from __future__ import annotations

import json
from pathlib import Path

from clareval_experiment.schemas import ClarEvalTask, PremiseItem


def load_clareval_jsonl(path: str | Path) -> list[ClarEvalTask]:
    records: list[ClarEvalTask] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            if "header" in raw:
                header = raw.get("header", {})
                fuzzy = raw.get("fuzzy_version", {})
                criteria = raw.get("evaluation_criteria", {})
                premises = [
                    PremiseItem(description=item.get("description", ""))
                    for item in criteria.get("ground_truth_missing_premises", [])
                ]
                task_id = header.get("task_id", "")
                fuzzy_type = header.get("fuzzy_type", "")
                difficulty = header.get("difficulty", "")
                instruction = fuzzy.get("instruction", "")
                original_prompt_source = raw.get("original_prompt_source", "")
            else:
                premises = [
                    PremiseItem(description=item if isinstance(item, str) else item.get("description", ""))
                    for item in raw.get("ground_truth_missing_premises", [])
                ]
                task_id = raw.get("task_id", "")
                fuzzy_type = raw.get("fuzzy_type", "")
                difficulty = raw.get("difficulty", "")
                instruction = raw.get("instruction", "")
                original_prompt_source = raw.get("original_prompt_source", "")
            records.append(
                ClarEvalTask(
                    task_id=task_id,
                    fuzzy_type=fuzzy_type,
                    difficulty=difficulty,
                    instruction=instruction,
                    missing_premises=premises,
                    original_prompt_source=original_prompt_source,
                    raw=raw,
                )
            )
    return records
