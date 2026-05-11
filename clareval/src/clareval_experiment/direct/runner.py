from __future__ import annotations

import json

from clareval_experiment.bed.prompts import (
    SIMULATOR_SYSTEM_PROMPT,
)
from clareval_experiment.bed.utils import (
    UNKNOWN_OR_IRRELEVANT_ANSWER,
    complete_json_with_retry,
    constrain_simulator_answer,
)
from clareval_experiment.config import BEDConfig
from clareval_experiment.direct.prompts import DIRECT_ACTION_SYSTEM_PROMPT
from clareval_experiment.eval.judge import coverage_ratio
from clareval_experiment.llm.base import LLMBackend
from clareval_experiment.schemas import ClarEvalTask, DialogueTurn, RunResult, TurnDetail


class DirectClarRunner:
    """Runner that asks the LLM for clarification questions directly."""

    def __init__(
        self,
        backend: LLMBackend,
        config: BEDConfig,
        simulator_backend: LLMBackend | None = None,
        evaluator_backend: LLMBackend | None = None,
    ) -> None:
        self.backend = backend
        self.simulator_backend = simulator_backend or backend
        self.evaluator_backend = evaluator_backend or self.simulator_backend
        self.config = config

    def run_task(self, task: ClarEvalTask) -> RunResult:
        dialogue: list[DialogueTurn] = [
            DialogueTurn(turn_index=0, role="user", content=task.instruction)
        ]
        asked_questions: list[str] = []
        turn_details: list[TurnDetail] = []
        turn_count = 0

        generated_code = ""
        unresolved = True
        for action_index in range(self.config.max_turns):
            action = self._decide_action(task, dialogue)
            if action["action"] == "answer":
                generated_code = action["code"].strip()
                turn_details.append(
                    TurnDetail(
                        turn_number=action_index + 1,
                        action="answer",
                        rationale=str(action.get("rationale", "")).strip(),
                        code=generated_code,
                    )
                )
                unresolved = False
                break

            question = action["question"].strip()
            asked_questions.append(question)

            raw_answer = self.simulator_backend.complete(
                SIMULATOR_SYSTEM_PROMPT,
                _format_simulator_user_message(task, question),
                temperature=0.0,
            )
            answer = constrain_simulator_answer(
                raw_answer,
                [premise.description for premise in task.missing_premises],
            )
            turn_details.append(
                TurnDetail(
                    turn_number=action_index + 1,
                    action="ask",
                    rationale=str(action.get("rationale", "")).strip(),
                    question=question,
                    selected_question=question,
                    simulator_raw_answer=raw_answer.strip(),
                    simulated_answer=answer,
                )
            )

            dialogue.append(
                DialogueTurn(turn_index=turn_count + 1, role="agent", content=question)
            )
            dialogue.append(
                DialogueTurn(turn_index=turn_count + 2, role="user", content=answer)
            )
            turn_count += 2

        gold_premises = [item.description for item in task.missing_premises]
        user_responses = [t.content for t in dialogue[1:] if t.role == "user"]
        simulator_answered_count = sum(
            1 for answer in user_responses if answer != UNKNOWN_OR_IRRELEVANT_ANSWER
        )
        matched_premises, completion_rate, evaluation_details = coverage_ratio(
            self.evaluator_backend,
            [generated_code] if generated_code.strip() else [],
            gold_premises,
            original_prompt_source=task.original_prompt_source,
        )

        scenario = "Multi-Turn"
        n_asked = len(asked_questions)
        metrics = {
            "completion_rate": completion_rate,
            "total_gold_premises": len(gold_premises),
            "matched_premises_count": len(matched_premises),
            "unmatched_premises_count": max(len(gold_premises) - len(matched_premises), 0),
            "simulator_answered_count": simulator_answered_count,
            "simulator_unknown_or_unimportant_count": len(user_responses) - simulator_answered_count,
            "simulator_answer_rate": simulator_answered_count / len(user_responses) if user_responses else 0.0,
            "efficiency_ratio": len(matched_premises) / n_asked if n_asked else 0.0,
            "atc": float(n_asked),
            "total_required_clarifications": len(gold_premises),
            "agent_question_turns": n_asked,
            "unresolved": unresolved,
        }

        return RunResult(
            task_id=task.task_id,
            scenario=scenario,
            fuzzy_type=task.fuzzy_type,
            difficulty=task.difficulty,
            task_group=_task_group(task),
            dialogue=dialogue,
            asked_questions=asked_questions,
            generated_code=generated_code,
            unresolved=unresolved,
            matched_premises=matched_premises,
            evaluation_details=evaluation_details,
            metrics=metrics,
            turn_details=turn_details,
        )

    def _decide_action(self, task: ClarEvalTask, dialogue: list[DialogueTurn]) -> dict:
        history = [{"role": t.role, "content": t.content} for t in dialogue]
        user_msg = (
            f"Original requirement:\n{task.instruction}\n\n"
            f"Clarification dialogue so far:\n"
            f"{json.dumps(history, ensure_ascii=False, indent=2)}"
        )
        payload = complete_json_with_retry(
            self.backend,
            DIRECT_ACTION_SYSTEM_PROMPT,
            user_msg,
            self.config.temperature,
            context=f"Direct action decision for {task.task_id}",
            validate=_validate_direct_action_payload,
        )
        payload["action"] = payload["action"].strip().lower()
        return payload


def _format_simulator_user_message(task: ClarEvalTask, question: str) -> str:
    premises_text = "\n".join(
        f"{index + 1}. {premise.description}"
        for index, premise in enumerate(task.missing_premises)
    ) or "(none specified)"
    return (
        f"Original ground-truth requirement:\n{task.original_prompt_source}\n\n"
        f"Ground-truth missing premises, copy one verbatim if it answers the question:\n"
        f"{premises_text}\n\n"
        f"Clarification question asked:\n{question}"
    )


def _task_group(task: ClarEvalTask) -> str:
    return f"{task.fuzzy_type} / {task.difficulty}"


def _validate_direct_action_payload(payload: dict) -> None:
    action = payload.get("action")
    if not isinstance(action, str) or action.strip().lower() not in {"ask", "answer"}:
        raise ValueError("Expected field 'action' to be 'ask' or 'answer'.")
    action = action.strip().lower()
    if action == "ask":
        question = payload.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Ask action must include a non-empty 'question'.")
    else:
        code = payload.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("Answer action must include non-empty 'code'.")
