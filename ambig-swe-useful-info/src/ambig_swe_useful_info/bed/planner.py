from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ambig_swe_useful_info.bed.prompts import (
    BED_PLANNER_SYSTEM_PROMPT,
)
from ambig_swe_useful_info.bed.utils import entropy, normalize, safe_json_loads
from ambig_swe_useful_info.config import BEDConfig
from ambig_swe_useful_info.llm.base import LLMBackend
from ambig_swe_useful_info.proxy.simulator import call_proxy
from ambig_swe_useful_info.schemas import (
    AmbigSWETask,
    AnswerDistribution,
    CandidateEIGDetail,
    CandidateQuestion,
    DialogueTurn,
    DisagreementAxis,
    Hypothesis,
    RankedQuestion,
    RunResult,
    TurnDetail,
)

class BEDAmbigRunner:
    """BED-LLM runner adapted to Ambig-SWE.

    Uses one planner LLM call per turn to produce hypotheses, disagreement
    axes, candidate questions, internal answer states, and answer-state
    likelihoods. TTR and useful-info coverage are computed post-hoc in
    ``eval/``.
    """

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
        dialogue = [DialogueTurn(turn_index=0, role="user", content=task.hidden_issue)]
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
                runner="bed",
                task_id=task.task_id,
                turn=turn_index,
                max_turns=self.config.max_turns,
                covered=len(covered_items),
                total=len(useful_items),
            )
            _emit_progress(
                progress_callback,
                "planner_request",
                runner="bed",
                task_id=task.task_id,
                turn=turn_index,
            )
            hypotheses, ranked, candidate_details, axes, plan_meta = self._plan_turn(task, dialogue)
            _emit_progress(
                progress_callback,
                "planner_done",
                runner="bed",
                task_id=task.task_id,
                turn=turn_index,
                hypotheses=len(hypotheses),
                candidates=len(candidate_details),
                used_fallback=bool(plan_meta["used_fallback"]),
            )
            if not ranked:
                stop_reason = "no_question"
                _emit_progress(
                    progress_callback,
                    "no_question",
                    runner="bed",
                    task_id=task.task_id,
                    turn=turn_index,
                    stop_reason=stop_reason,
                )
                break
            best = ranked[0]
            asked_questions.append(best.question.question)
            _emit_progress(
                progress_callback,
                "agent_question",
                runner="bed",
                task_id=task.task_id,
                turn=turn_index,
                question=best.question.question,
                eig=best.eig,
            )

            for cd in candidate_details:
                if cd.question == best.question.question:
                    cd.selected = True

            hyp_before = [
                Hypothesis(hid=h.hid, summary=h.summary, prior=h.prior, evidence=list(h.evidence))
                for h in hypotheses
            ]

            dialogue.append(
                DialogueTurn(
                    turn_index=turn_count + 1,
                    role="agent",
                    content=best.question.question,
                )
            )
            pending = [it for it in useful_items if it not in covered_items]
            _emit_progress(
                progress_callback,
                "proxy_request",
                runner="bed",
                task_id=task.task_id,
                turn=turn_index,
                remaining=len(pending),
            )
            proxy_result = call_proxy(self.proxy_backend, best.question.question, pending)
            answer = proxy_result.answer
            dialogue.append(
                DialogueTurn(
                    turn_index=turn_count + 2,
                    role="user",
                    content=answer,
                )
            )
            turn_count += 2

            turn_details.append(
                TurnDetail(
                    turn_number=len(turn_details) + 1,
                    hypotheses_before=hyp_before,
                    candidates_ranked=candidate_details,
                    selected_question=best.question.question,
                    question_rationale=best.question.rationale,
                    simulated_answer=answer,
                    disagreement_axes=axes,
                    planner_parse_warnings=list(plan_meta["planner_parse_warnings"]),
                    num_hypotheses_returned=int(plan_meta["num_hypotheses_returned"]),
                    num_candidates_returned=int(plan_meta["num_candidates_returned"]),
                    used_fallback=bool(plan_meta["used_fallback"]),
                )
            )

            # Early stop once all useful items are covered by proxy answers.
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

            turn_details[-1].remaining_useful_info_before = proxy_result.remaining_items_before
            turn_details[-1].proxy_selected_id = proxy_result.selected_id
            turn_details[-1].proxy_reasoning = proxy_result.reasoning
            turn_details[-1].selected_useful_info = proxy_result.selected_item
            turn_details[-1].newly_covered = newly_covered
            turn_details[-1].covered_items_after = list(covered_items)
            turn_details[-1].coverage_ratio_after = (
                len(covered_items) / len(useful_items) if useful_items else 0.0
            )
            turn_details[-1].early_stop_reason = (
                stop_reason
                if stop_reason in {"all_useful_info_covered", "max_turns_reached"}
                and (
                    stop_reason == "all_useful_info_covered"
                    or turn_num == self.config.max_turns - 1
                )
                else ""
            )

            _emit_progress(
                progress_callback,
                "turn_done",
                runner="bed",
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
            runner="bed",
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

    # ------------------------------------------------------------------ #
    #  Single-call BED planning                                           #
    # ------------------------------------------------------------------ #

    def _plan_turn(
        self,
        task: AmbigSWETask,
        dialogue: list[DialogueTurn],
    ) -> tuple[
        list[Hypothesis],
        list[RankedQuestion],
        list[CandidateEIGDetail],
        list[DisagreementAxis],
        dict[str, object],
    ]:
        history = [{"role": turn.role, "content": turn.content} for turn in dialogue]
        user = (
            f"Issue:\n{task.hidden_issue}\n\n"
            f"Dialogue history:\n{json.dumps(history, ensure_ascii=False)}\n\n"
            "Planner configuration:\n"
            f"- num_hypotheses: {self.config.num_hypotheses}\n"
            f"- num_candidates: {self.config.num_candidates}"
        )
        payload = safe_json_loads(
            self.backend.complete(BED_PLANNER_SYSTEM_PROMPT, user, self.config.temperature),
            {"hypotheses": [], "disagreement_axes": [], "candidates": []},
        )

        hypotheses = self._parse_hypotheses(payload.get("hypotheses", []))
        axes = self._parse_axes(payload.get("disagreement_axes", []))
        candidates_raw = list(payload.get("candidates", []))[: self.config.num_candidates]
        plan_meta: dict[str, object] = {
            "planner_parse_warnings": [],
            "num_hypotheses_returned": len(payload.get("hypotheses", []) or []),
            "num_candidates_returned": len(payload.get("candidates", []) or []),
            "used_fallback": False,
        }

        if not hypotheses:
            plan_meta["planner_parse_warnings"] = list(plan_meta["planner_parse_warnings"]) + [
                "planner returned no parseable hypotheses; using fallback hypothesis"
            ]
            plan_meta["used_fallback"] = True
            hypotheses = [
                Hypothesis(
                    hid="H1",
                    summary="The issue is missing details about scope, expected behavior, or affected files.",
                    prior=1.0,
                    evidence=["Issue is underspecified"],
                )
            ]

        if not candidates_raw:
            plan_meta["planner_parse_warnings"] = list(plan_meta["planner_parse_warnings"]) + [
                "planner returned no parseable candidates; using fallback candidate"
            ]
            plan_meta["used_fallback"] = True
            fallback_axis = DisagreementAxis(
                name="fallback_localisation",
                description="Fallback when no disagreement axes were returned.",
                positions=[
                    {"hypothesis_ids": [h.hid for h in hypotheses],
                     "stance": "no axis available; fallback question"},
                ],
            )
            axes = [fallback_axis]
            candidates_raw = [
                {
                    "axis_name": fallback_axis.name,
                    "question": "Which file is most likely affected by this issue?",
                    "rationale": "Fallback localisation question.",
                    "possible_answers": [
                        {"id": "A1", "answer": "no axis available; fallback answer state"}
                    ],
                    "likelihoods": [
                        {
                            "hypothesis_id": h.hid,
                            "probs": {"A1": 1.0},
                        }
                        for h in hypotheses
                    ],
                }
            ]

        axis_by_name = {axis.name: axis for axis in axes}

        ranked: list[RankedQuestion] = []
        candidate_details: list[CandidateEIGDetail] = []

        for item in candidates_raw:
            candidate, id_to_label = self._parse_candidate(item)
            axis_name = str(item.get("axis_name", "")).strip()
            axis = axis_by_name.get(axis_name)
            if axis is None:
                axis = DisagreementAxis(
                    name=axis_name or "unlabeled_axis",
                    description="Axis returned only on the candidate record.",
                    positions=[],
                )
                axes.append(axis)
                axis_by_name[axis.name] = axis

            h_dists, predictive, predictive_entropy, expected_conditional_entropy, eig = (
                self._eig_from_likelihoods(
                    hypotheses,
                    candidate.eig_stances,
                    item.get("likelihoods", []),
                    id_to_label,
                )
            )

            ranked.append(
                RankedQuestion(
                    question=candidate,
                    predictive_entropy=predictive_entropy,
                    expected_conditional_entropy=expected_conditional_entropy,
                    eig=eig,
                )
            )
            candidate_details.append(
                CandidateEIGDetail(
                    question=candidate.question,
                    rationale=candidate.rationale,
                    eig_stances=candidate.eig_stances,
                    per_hypothesis_distributions=[
                        AnswerDistribution(hypothesis_id=hyp.hid, distribution=dist)
                        for hyp, dist in zip(hypotheses, h_dists)
                    ],
                    predictive_distribution=predictive,
                    predictive_entropy=predictive_entropy,
                    expected_conditional_entropy=expected_conditional_entropy,
                    eig=eig,
                    selected=False,
                    axis_name=axis.name,
                )
            )

        combined = sorted(
            zip(ranked, candidate_details), key=lambda pair: pair[0].eig, reverse=True
        )
        if combined:
            ranked, candidate_details = map(list, zip(*combined))
        return hypotheses, ranked, candidate_details, axes, plan_meta

    def _parse_hypotheses(self, items: list[dict]) -> list[Hypothesis]:
        raw = list(items)[: self.config.num_hypotheses]
        priors: dict[str, float] = {}
        hypotheses: list[Hypothesis] = []
        for idx, item in enumerate(raw):
            hid = str(item.get("id") or item.get("hid") or f"H{idx + 1}").strip()
            if not hid:
                hid = f"H{idx + 1}"
            try:
                prior = float(item.get("probability", item.get("prior", 0.0)))
            except (TypeError, ValueError):
                prior = 0.0
            priors[hid] = max(0.0, prior)
            hypotheses.append(
                Hypothesis(
                    hid=hid,
                    summary=str(item.get("summary", "")).strip(),
                    prior=0.0,
                    evidence=[str(ev) for ev in item.get("evidence", [])],
                )
            )
        if not hypotheses:
            return []
        total = sum(priors.values())
        if total <= 0:
            uniform = 1.0 / len(hypotheses)
            return [
                Hypothesis(hid=h.hid, summary=h.summary, prior=uniform, evidence=h.evidence)
                for h in hypotheses
            ]
        return [
            Hypothesis(
                hid=h.hid,
                summary=h.summary,
                prior=priors.get(h.hid, 0.0) / total,
                evidence=h.evidence,
            )
            for h in hypotheses
        ]

    def _parse_axes(self, items: list[dict]) -> list[DisagreementAxis]:
        return [
            DisagreementAxis(
                name=str(item.get("name", "")).strip(),
                description=str(item.get("description", "")).strip(),
                positions=item.get("positions", []) or [],
            )
            for item in items
            if item.get("name")
        ]

    def _parse_candidate(self, item: dict) -> tuple[CandidateQuestion, dict[str, str]]:
        answers = item.get("possible_answers", []) or []
        labels: list[str] = []
        id_to_label: dict[str, str] = {}
        for idx, answer in enumerate(answers):
            if isinstance(answer, dict):
                aid = str(answer.get("id") or f"A{idx + 1}").strip()
                text = str(answer.get("answer") or answer.get("text") or "").strip()
            else:
                aid = f"A{idx + 1}"
                text = str(answer).strip()
            label = f"{aid}: {text}" if text else aid
            labels.append(label)
            id_to_label[aid] = label
            id_to_label[label] = label
        if not labels:
            labels = ["A1: unspecified answer state"]
            id_to_label = {"A1": labels[0], labels[0]: labels[0]}
        question = str(item.get("question", "")).strip()
        if not question:
            question = "Could you clarify the intended behavior or repair scope?"
        return (
            CandidateQuestion(
                question=question,
                rationale=str(item.get("rationale", "")).strip(),
                eig_stances=labels,
            ),
            id_to_label,
        )

    def _eig_from_likelihoods(
        self,
        hypotheses: list[Hypothesis],
        answer_labels: list[str],
        likelihoods: list[dict],
        id_to_label: dict[str, str],
    ) -> tuple[list[dict[str, float]], dict[str, float], float, float, float]:
        """EIG from LLM-estimated P(answer_state | hypothesis)."""
        by_hyp: dict[str, dict] = {
            str(item.get("hypothesis_id", "")).strip(): item
            for item in likelihoods
            if item.get("hypothesis_id")
        }

        h_dists: list[dict[str, float]] = []
        for h in hypotheses:
            dist = {label: 0.0 for label in answer_labels}
            raw_probs = by_hyp.get(h.hid, {}).get("probs", {})
            if isinstance(raw_probs, dict):
                for key, value in raw_probs.items():
                    label = id_to_label.get(str(key), str(key))
                    if label in dist:
                        try:
                            dist[label] = max(0.0, float(value))
                        except (TypeError, ValueError):
                            dist[label] = 0.0
            if sum(dist.values()) <= 0 and answer_labels:
                uniform = 1.0 / len(answer_labels)
                dist = {label: uniform for label in answer_labels}
            else:
                dist = normalize(dist)
            h_dists.append(dist)

        predictive: dict[str, float] = {label: 0.0 for label in answer_labels}
        for hyp, dist in zip(hypotheses, h_dists):
            for label in answer_labels:
                predictive[label] += hyp.prior * dist[label]
        predictive = normalize(predictive)

        h_pred = entropy(predictive.values())
        e_h_cond = sum(
            hyp.prior * entropy(dist.values()) for hyp, dist in zip(hypotheses, h_dists)
        )
        return h_dists, predictive, h_pred, e_h_cond, h_pred - e_h_cond


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

