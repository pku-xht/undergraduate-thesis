from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clareval_experiment.llm.base import LLMBackend

from clareval_experiment.bed.prompts import JUDGE_SYSTEM_PROMPT
from clareval_experiment.bed.utils import complete_json_with_retry
from clareval_experiment.schemas import EvaluationDetail


def judge_premises(
    backend: "LLMBackend",
    candidate: str,
    gold_items: list[str],
    original_prompt_source: str = "",
    temperature: float = 0.0,
) -> list[EvaluationDetail]:
    """Return final evaluator judgments for every gold premise."""
    if not gold_items or not candidate.strip():
        return [
            EvaluationDetail(
                premise=item,
                covered=False,
                reasoning="No generated code was available for evaluation.",
            )
            for item in gold_items
        ]

    user = (
        f"Original full ground-truth prompt:\n{original_prompt_source}\n\n"
        f"Ground-truth missing premises:\n{json.dumps(gold_items, ensure_ascii=False, indent=2)}\n\n"
        f"Generated Python code:\n{candidate}\n\n"
        "For each ground-truth missing premise, decide whether the generated code satisfies it."
    )
    payload = complete_json_with_retry(
        backend,
        JUDGE_SYSTEM_PROMPT,
        user,
        temperature,
        context="Final code evaluator",
        validate=lambda row: _validate_batch_judge_payload(row, gold_items),
    )
    return [
        EvaluationDetail(
            premise=row["premise"],
            covered=row["covered"],
            reasoning=str(row.get("reasoning", "")).strip(),
        )
        for row in payload["premise_results"]
    ]


def coverage_ratio(
    backend: "LLMBackend",
    candidates: list[str],
    gold_items: list[str],
    original_prompt_source: str = "",
) -> tuple[list[str], float, list[EvaluationDetail]]:
    """Check which gold items are covered by generated code.

    Returns (matched_gold_items, coverage_ratio).
    """
    if not gold_items:
        return [], 0.0, []
    if not candidates:
        details = [
            EvaluationDetail(
                premise=item,
                covered=False,
                reasoning="No generated code was available for evaluation.",
            )
            for item in gold_items
        ]
        return [], 0.0, details

    matched: list[str] = []
    all_details: list[EvaluationDetail] = []
    for candidate in candidates:
        details = judge_premises(
            backend,
            candidate,
            gold_items,
            original_prompt_source,
        )
        all_details = details
        for detail in details:
            if detail.covered and detail.premise not in matched:
                matched.append(detail.premise)

    ratio = len(matched) / len(gold_items)
    return matched, ratio, all_details


def _validate_batch_judge_payload(payload: dict, gold_items: list[str]) -> None:
    results = payload.get("premise_results")
    if not isinstance(results, list):
        raise ValueError("Expected list field 'premise_results'.")

    seen: list[str] = []
    for row in results:
        if not isinstance(row, dict):
            raise ValueError("Each premise result must be an object.")
        premise = row.get("premise")
        if not isinstance(premise, str) or premise not in gold_items:
            raise ValueError("Each premise result must copy one expected premise verbatim.")
        if premise in seen:
            raise ValueError("Each premise must appear exactly once.")
        seen.append(premise)
        if not isinstance(row.get("covered"), bool):
            raise ValueError("Each premise result must include boolean field 'covered'.")

    if set(seen) != set(gold_items):
        raise ValueError("The evaluator must return one result for every premise.")
