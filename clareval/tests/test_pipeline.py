from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from clareval_experiment.cli import load_completed_task_ids, sanitize_jsonl_for_resume
from clareval_experiment.bed.planner import BEDClarEvalRunner
from clareval_experiment.bed.utils import (
    LLMOutputError,
    complete_json_with_retry,
    iter_jsonl_records,
)
from clareval_experiment.config import BEDConfig
from clareval_experiment.data.loader import load_clareval_jsonl
from clareval_experiment.direct.runner import DirectClarRunner
from clareval_experiment.eval.judge import coverage_ratio
from clareval_experiment.eval.metrics import evaluate_predictions
from clareval_experiment.llm.mock_backend import MockBackend


class _SequenceBackend:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0

    def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        *,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> str:
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return response


def _write_sample_dataset(path: Path) -> None:
    row = {
        "task_id": "sample_multi_turn",
        "fuzzy_type": "Missing Premises",
        "difficulty": "easy",
        "instruction": "Create a function that takes input and returns a result.",
        "ground_truth_missing_premises": [
            "The function should take a list of floats and a threshold.",
            "The function should return whether any pair is closer than the threshold.",
        ],
        "original_prompt_source": (
            "Implement a function that takes a list of floats and a threshold, "
            "then returns whether any pair is closer than the threshold."
        ),
    }
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")


def test_end_to_end(tmp_path: Path) -> None:
    dataset = tmp_path / "sample_dataset.jsonl"
    _write_sample_dataset(dataset)
    tasks = load_clareval_jsonl(dataset)
    runner = BEDClarEvalRunner(MockBackend(), BEDConfig(max_turns=3))

    output_file = tmp_path / "results.jsonl"
    with output_file.open("w", encoding="utf-8") as handle:
        for task in tasks:
            result = runner.run_task(task)
            assert result.turn_details
            assert result.evaluation_details
            row = asdict(result)
            row["dialogue"] = [asdict(turn) for turn in result.dialogue]
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = evaluate_predictions(output_file)
    assert "overall" in summary
    assert "by_task_group" in summary


def test_direct_records_action_trace(tmp_path: Path) -> None:
    dataset = tmp_path / "sample_dataset.jsonl"
    _write_sample_dataset(dataset)
    task = load_clareval_jsonl(dataset)[0]
    result = DirectClarRunner(MockBackend(), BEDConfig(max_turns=3)).run_task(task)

    assert result.turn_details
    assert [turn.action for turn in result.turn_details] == ["ask", "ask", "answer"]
    assert result.turn_details[0].question
    assert result.turn_details[0].simulator_raw_answer
    assert result.turn_details[0].simulated_answer
    assert result.turn_details[-1].code == result.generated_code
    assert result.evaluation_details


def test_resume_reader_stops_on_partial_json(tmp_path: Path) -> None:
    path = tmp_path / "partial.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"task_id": "task_a"}),
                json.dumps({"task_id": "task_b"}),
                '{"task_id": ',
            ]
        ),
        encoding="utf-8",
    )
    completed = load_completed_task_ids(path)
    assert completed == {"task_a", "task_b"}


def test_resume_sanitizer_truncates_invalid_tail(tmp_path: Path) -> None:
    path = tmp_path / "partial.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"task_id": "task_a"}),
                json.dumps({"task_id": "task_b"}),
                "\x00\x00\x00broken",
                json.dumps({"task_id": "task_c"}),
            ]
        ),
        encoding="utf-8",
    )
    completed, truncated = sanitize_jsonl_for_resume(path)
    assert truncated is True
    assert completed == {"task_a", "task_b"}
    assert list(iter_jsonl_records(path)) == [
        {"task_id": "task_a"},
        {"task_id": "task_b"},
    ]


def test_structured_llm_output_retries_once() -> None:
    backend = _SequenceBackend(["not json", '{"question": "What input?"}'])
    payload = complete_json_with_retry(
        backend,
        "system",
        "user",
        0.0,
        context="test retry",
        validate=lambda row: None if row.get("question") else (_ for _ in ()).throw(ValueError("missing")),
    )
    assert payload["question"] == "What input?"
    assert backend.calls == 2


def test_structured_llm_retry_adds_validation_error() -> None:
    class InspectBackend(_SequenceBackend):
        def __init__(self) -> None:
            super().__init__(["not json", '{"question": "What input?"}'])
            self.users: list[str] = []

        def complete(
            self,
            system: str,
            user: str,
            temperature: float = 0.2,
            *,
            json_mode: bool = False,
            max_tokens: int | None = None,
        ) -> str:
            self.users.append(user)
            return super().complete(
                system,
                user,
                temperature,
                json_mode=json_mode,
                max_tokens=max_tokens,
            )

    backend = InspectBackend()
    complete_json_with_retry(
        backend,
        "system",
        "user",
        0.0,
        context="test retry",
        validate=lambda row: None if row.get("question") else (_ for _ in ()).throw(ValueError("missing")),
    )
    assert "Validation error:" in backend.users[1]
    assert "Return exactly one valid JSON object" in backend.users[1]


def test_structured_llm_output_raises_after_retry() -> None:
    backend = _SequenceBackend(["not json", '{"question": ""}'])
    try:
        complete_json_with_retry(
            backend,
            "system",
            "user",
            0.0,
            context="test failure",
            validate=lambda row: None if row.get("question") else (_ for _ in ()).throw(ValueError("missing")),
        )
    except LLMOutputError:
        pass
    else:
        raise AssertionError("Expected LLMOutputError")


def test_structured_llm_failure_reports_response_metadata() -> None:
    class MetadataBackend(_SequenceBackend):
        def complete(
            self,
            system: str,
            user: str,
            temperature: float = 0.2,
            *,
            json_mode: bool = False,
            max_tokens: int | None = None,
        ) -> str:
            self.last_response_metadata = {
                "response_id": f"resp-{self.calls}",
                "finish_reason": "stop",
                "usage": {"prompt_tokens": 10, "completion_tokens": 0, "total_tokens": 10},
                "json_mode_requested": json_mode,
                "json_mode_fallback": False,
            }
            return super().complete(
                system,
                user,
                temperature,
                json_mode=json_mode,
                max_tokens=max_tokens,
            )

    backend = MetadataBackend(["", ""])
    try:
        complete_json_with_retry(
            backend,
            "system",
            "user",
            0.0,
            context="metadata failure",
        )
    except LLMOutputError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected LLMOutputError")

    assert "Response metadata:" in message
    assert "resp-0" in message
    assert "resp-1" in message
    assert "finish_reason" in message
    assert "json_mode_fallback" in message


def test_final_evaluator_judges_all_premises_in_one_call() -> None:
    premises = [
        "The function should take a list of floats and a threshold.",
        "The function should return whether any pair is closer than the threshold.",
    ]
    backend = _SequenceBackend(
        [
            json.dumps(
                {
                    "premise_results": [
                        {
                            "premise": premises[0],
                            "covered": True,
                            "reasoning": "The code has the expected inputs.",
                        },
                        {
                            "premise": premises[1],
                            "covered": False,
                            "reasoning": "The return behavior is missing.",
                        },
                    ]
                }
            )
        ]
    )

    matched, ratio, details = coverage_ratio(
        backend,
        ["def f(numbers, threshold): return False"],
        premises,
        original_prompt_source="Implement the function.",
    )

    assert backend.calls == 1
    assert matched == [premises[0]]
    assert ratio == 0.5
    assert [detail.premise for detail in details] == premises
    assert [detail.covered for detail in details] == [True, False]
