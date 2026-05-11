from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ambig_swe_useful_info.bed.utils import safe_json_loads
from ambig_swe_useful_info.config import BEDConfig
from ambig_swe_useful_info.direct.prompts import DIRECT_QUESTION_SYSTEM_PROMPT
from ambig_swe_useful_info.llm.base import LLMBackend
from ambig_swe_useful_info.proxy.simulator import call_proxy
from ambig_swe_useful_info.schemas import AmbigSWETask, DialogueTurn, RunResult, TurnDetail


class DirectAmbigRunner:
    """Baseline: agent asks clarification questions directly, no BED machinery."""

    def __init__(
        self,
        backend: LLMBackend,
        config: BEDConfig,
        proxy_backend: LLMBackend | None = None,
    ) -> None:
        self.backend = backend
        self.proxy_backend = proxy_backend or backend
        self.config = config

    def run_task(
        self,
        task: AmbigSWETask,
        progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> RunResult:
        dialogue: list[DialogueTurn] = [
            DialogueTurn(turn_index=0, role="user", content=task.hidden_issue)
        ]
        asked_questions: list[str] = []
        turn_details: list[TurnDetail] = []
        turn_count = 0

        useful_items = list(task.useful_info_items)
        covered_items: list[str] = []
        stop_reason = "max_turns_reached"

        for turn_num in range(self.config.max_turns):
            turn_index = turn_num + 1
            _emit_progress(
                progress_callback,
                "turn_start",
                runner="direct",
                task_id=task.task_id,
                turn=turn_index,
                max_turns=self.config.max_turns,
                covered=len(covered_items),
                total=len(useful_items),
            )
            system = DIRECT_QUESTION_SYSTEM_PROMPT
            if turn_num == 0:
                user_msg = (
                    f"Issue:\n{task.hidden_issue}\n\n"
                    "Dialogue so far:\n(none)"
                )
            else:
                user_msg = (
                    f"Issue:\n{task.hidden_issue}\n\n"
                    f"Dialogue so far:\n{_format_dialogue(dialogue)}"
                )

            _emit_progress(
                progress_callback,
                "agent_request",
                runner="direct",
                task_id=task.task_id,
                turn=turn_index,
            )
            raw = self.backend.complete(system, user_msg, self.config.temperature)
            parsed = safe_json_loads(raw, {})
            question = parsed.get("question", "").strip()
            if not question:
                stop_reason = "no_question"
                _emit_progress(
                    progress_callback,
                    "no_question",
                    runner="direct",
                    task_id=task.task_id,
                    turn=turn_index,
                    stop_reason=stop_reason,
                )
                break
            asked_questions.append(question)
            rationale = str(parsed.get("rationale", "")).strip()
            _emit_progress(
                progress_callback,
                "agent_question",
                runner="direct",
                task_id=task.task_id,
                turn=turn_index,
                question=question,
            )

            pending = [it for it in useful_items if it not in covered_items]
            _emit_progress(
                progress_callback,
                "proxy_request",
                runner="direct",
                task_id=task.task_id,
                turn=turn_index,
                remaining=len(pending),
            )
            proxy_result = call_proxy(self.proxy_backend, question, pending)
            answer = proxy_result.answer

            dialogue.append(
                DialogueTurn(turn_index=turn_count + 1, role="agent", content=question)
            )
            dialogue.append(
                DialogueTurn(turn_index=turn_count + 2, role="user", content=answer)
            )
            turn_count += 2

            # Early stop on full useful-info coverage (matches the BED runner).
            newly_covered: list[str] = []
            if useful_items:
                if answer in pending and answer not in covered_items:
                    covered_items.append(answer)
                    newly_covered.append(answer)
                if len(covered_items) >= len(useful_items):
                    stop_reason = "all_useful_info_covered"
                elif turn_num == self.config.max_turns - 1:
                    stop_reason = "max_turns_reached"
            elif turn_num == self.config.max_turns - 1:
                stop_reason = "max_turns_reached"

            turn_details.append(
                TurnDetail(
                    turn_number=len(turn_details) + 1,
                    selected_question=question,
                    question_rationale=rationale,
                    simulated_answer=answer,
                    remaining_useful_info_before=proxy_result.remaining_items_before,
                    proxy_selected_id=proxy_result.selected_id,
                    proxy_reasoning=proxy_result.reasoning,
                    selected_useful_info=proxy_result.selected_item,
                    newly_covered=newly_covered,
                    covered_items_after=list(covered_items),
                    coverage_ratio_after=(
                        len(covered_items) / len(useful_items) if useful_items else 0.0
                    ),
                    early_stop_reason=(
                        stop_reason
                        if stop_reason in {"all_useful_info_covered", "max_turns_reached"}
                        and (
                            stop_reason == "all_useful_info_covered"
                            or turn_num == self.config.max_turns - 1
                        )
                        else ""
                    ),
                )
            )

            _emit_progress(
                progress_callback,
                "turn_done",
                runner="direct",
                task_id=task.task_id,
                turn=turn_index,
                selected_id=proxy_result.selected_id,
                idk=(not proxy_result.selected_item),
                newly_covered=len(newly_covered),
                covered=len(covered_items),
                total=len(useful_items),
                coverage_ratio=(
                    len(covered_items) / len(useful_items) if useful_items else 0.0
                ),
                stop_reason=(
                    stop_reason
                    if stop_reason == "all_useful_info_covered"
                    or turn_num == self.config.max_turns - 1
                    else ""
                ),
            )
            if stop_reason == "all_useful_info_covered":
                break

        final_summary = _proxy_answer_summary(dialogue)

        metrics = {
            "atc": float(len(asked_questions)),
            "n_idk_responses": _count_idk(dialogue),
            "stop_reason": stop_reason,
        }

        return RunResult(
            task_id=task.task_id,
            runner="direct",
            dialogue=dialogue,
            asked_questions=asked_questions,
            final_summary=final_summary,
            metrics=metrics,
            turn_details=turn_details,
            metadata={
                "max_turns": self.config.max_turns,
                "num_hypotheses": self.config.num_hypotheses,
                "num_candidates": self.config.num_candidates,
            },
        )


def _format_dialogue(turns: list[DialogueTurn]) -> str:
    return "\n".join(
        f"{'User' if t.role == 'user' else 'Agent'}: {t.content}" for t in turns
    )


def _count_idk(turns: list[DialogueTurn]) -> int:
    return sum(
        1
        for t in turns
        if t.role == "user" and "i don't have that information" in t.content.lower()
    )


def _proxy_answer_summary(turns: list[DialogueTurn]) -> str:
    answers = [t.content.strip() for t in turns[1:] if t.role == "user" and t.content.strip()]
    return "\n".join(answers)


def _emit_progress(
    callback: Callable[[str, dict[str, Any]], None] | None,
    event: str,
    **payload: Any,
) -> None:
    if callback is not None:
        callback(event, payload)

