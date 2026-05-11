from __future__ import annotations

import json
import os
from typing import Any

from clareval_experiment.bed.prompts import (
    BED_ACTION_SYSTEM_PROMPT,
    SIMULATOR_SYSTEM_PROMPT,
)
from clareval_experiment.bed.utils import (
    UNKNOWN_OR_IRRELEVANT_ANSWER,
    complete_json_with_retry,
    constrain_simulator_answer,
    entropy,
    normalize,
)
from clareval_experiment.config import BEDConfig
from clareval_experiment.eval.judge import coverage_ratio
from clareval_experiment.llm.base import LLMBackend
from clareval_experiment.schemas import (
    AnswerDistribution,
    CandidateEIGDetail,
    CandidateQuestion,
    ClarEvalTask,
    DialogueTurn,
    Hypothesis,
    RankedQuestion,
    RunResult,
    TurnDetail,
)


class BEDClarEvalRunner:
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
        dialogue = [DialogueTurn(turn_index=0, role="user", content=task.instruction)]
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

            hypotheses = _extract_hypotheses_from_action(
                action,
                self.config.num_hypotheses,
            )
            candidate_rows = _extract_candidate_rows_from_action(
                action,
                hypotheses,
                self.config.num_candidates,
            )
            ranked, candidate_details = self._rank_questions(hypotheses, candidate_rows)
            if not ranked:
                raise ValueError(f"BED produced no candidate questions for {task.task_id}.")

            best = ranked[0]
            if not best.question.question:
                raise ValueError(f"BED selected an empty question for {task.task_id}.")
            asked_questions.append(best.question.question)

            for detail in candidate_details:
                if detail.question == best.question.question:
                    detail.selected = True

            hyp_before = [
                Hypothesis(
                    hid=h.hid,
                    summary=h.summary,
                    prior=h.prior,
                    evidence=list(h.evidence),
                )
                for h in hypotheses
            ]

            dialogue.append(
                DialogueTurn(
                    turn_index=turn_count + 1,
                    role="agent",
                    content=best.question.question,
                )
            )
            raw_answer, answer = self._simulate_answer(task, best.question.question)
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
                    action="ask",
                    rationale=str(action.get("rationale", "")).strip(),
                    question=best.question.question,
                    hypotheses=hyp_before,
                    candidates_ranked=candidate_details,
                    selected_question=best.question.question,
                    simulator_raw_answer=raw_answer.strip(),
                    simulated_answer=answer,
                )
            )

        gold_premises = [item.description for item in task.missing_premises]
        user_responses = [
            turn.content
            for turn in dialogue[1:]
            if turn.role == "user"
        ]
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

    def _rank_questions(
        self,
        hypotheses: list[Hypothesis],
        candidate_rows: list[tuple[CandidateQuestion, list[dict[str, float]]]],
    ) -> tuple[list[RankedQuestion], list[CandidateEIGDetail]]:
        ranked: list[RankedQuestion] = []
        candidate_details: list[CandidateEIGDetail] = []

        for candidate, h_dists in candidate_rows:
            predictive: dict[str, float] = {}
            for answer in candidate.candidate_answers:
                predictive[answer] = sum(
                    dist.get(answer, 0.0) * hyp.prior
                    for dist, hyp in zip(h_dists, hypotheses)
                )
            predictive = normalize(predictive)

            predictive_entropy = entropy(predictive.values())
            expected_conditional_entropy = sum(
                hyp.prior * entropy(dist.values())
                for hyp, dist in zip(hypotheses, h_dists)
            )
            eig = predictive_entropy - expected_conditional_entropy

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
                    candidate_answers=candidate.candidate_answers,
                    candidate_answer_texts=candidate.candidate_answer_texts,
                    per_hypothesis_answer_distributions=[
                        AnswerDistribution(hypothesis_id=hyp.hid, distribution=dist)
                        for hyp, dist in zip(hypotheses, h_dists)
                    ],
                    predictive_distribution=predictive,
                    predictive_entropy=predictive_entropy,
                    expected_conditional_entropy=expected_conditional_entropy,
                    eig=eig,
                    selected=False,
                )
            )

        combined = sorted(
            zip(ranked, candidate_details), key=lambda pair: pair[0].eig, reverse=True
        )
        if combined:
            ranked, candidate_details = map(list, zip(*combined))
        return ranked, candidate_details

    def _simulate_answer(self, task: ClarEvalTask, question: str) -> tuple[str, str]:
        premises_text = "\n".join(
            f"{index + 1}. {premise.description}"
            for index, premise in enumerate(task.missing_premises)
        ) or "(none specified)"
        user = (
            f"Original ground-truth requirement:\n{task.original_prompt_source}\n\n"
            "Ground-truth missing premises, copy one verbatim if it answers the question:\n"
            f"{premises_text}\n\n"
            f"Clarification question asked:\n{question}"
        )
        raw_answer = self.simulator_backend.complete(SIMULATOR_SYSTEM_PROMPT, user, temperature=0.0)
        answer = constrain_simulator_answer(
            raw_answer,
            [premise.description for premise in task.missing_premises],
        )
        return raw_answer, answer

    def _decide_action(self, task: ClarEvalTask, dialogue: list[DialogueTurn]) -> dict[str, Any]:
        history = [{"role": t.role, "content": t.content} for t in dialogue]
        user = (
            f"Original requirement:\n{task.instruction}\n\n"
            f"Clarification dialogue so far:\n"
            f"{json.dumps(history, ensure_ascii=False, indent=2)}"
        )
        payload = complete_json_with_retry(
            self.backend,
            BED_ACTION_SYSTEM_PROMPT,
            user,
            self.config.temperature,
            context=f"BED action decision for {task.task_id}",
            validate=lambda row: _validate_bed_action_payload(
                row,
                num_hypotheses=self.config.num_hypotheses,
                num_candidates=self.config.num_candidates,
            ),
            max_tokens=_bed_action_max_tokens(),
        )
        payload["action"] = payload["action"].strip().lower()
        return payload


def _task_group(task: ClarEvalTask) -> str:
    return f"{task.fuzzy_type} / {task.difficulty}"


def _bed_action_max_tokens() -> int:
    raw = os.environ.get("CLAREVAL_BED_ACTION_MAX_TOKENS")
    if raw is None:
        raw = os.environ.get("CLAREVAL_OPENAI_MAX_TOKENS")
    if raw is None:
        return 8192
    try:
        value = int(raw)
    except ValueError:
        return 8192
    return value if value > 0 else 8192


def _extract_hypotheses_from_action(payload: dict[str, Any], limit: int) -> list[Hypothesis]:
    raw_items = payload.get("hypotheses", [])[:limit]
    raw_priors = [
        _coerce_probability(item.get("probability", item.get("prior")))
        if isinstance(item, dict) else 0.0
        for item in raw_items
    ]
    if sum(raw_priors) > 0:
        priors = list(normalize({str(i): value for i, value in enumerate(raw_priors)}).values())
    else:
        priors = [1.0 / len(raw_items)] * len(raw_items)

    hypotheses: list[Hypothesis] = []
    for index, item in enumerate(raw_items):
        hid = str(item.get("id") or item.get("hid") or f"H{index + 1}").strip()
        summary = str(
            item.get("complete_requirement")
            or item.get("summary")
            or ""
        ).strip()
        hypotheses.append(
            Hypothesis(
                hid=hid or f"H{index + 1}",
                summary=summary,
                prior=priors[index],
                evidence=list(item.get("evidence", [])) if isinstance(item.get("evidence", []), list) else [],
            )
        )
    return hypotheses


def _extract_candidate_rows_from_action(
    payload: dict[str, Any],
    hypotheses: list[Hypothesis],
    limit: int,
) -> list[tuple[CandidateQuestion, list[dict[str, float]]]]:
    rows: list[tuple[CandidateQuestion, list[dict[str, float]]]] = []
    raw_candidates = payload.get("candidate_questions") or payload.get("candidates") or []
    for index, item in enumerate(raw_candidates[:limit], start=1):
        answer_ids, answer_texts = _extract_possible_answers(item)
        candidate = CandidateQuestion(
            question=str(item.get("question", "")).strip(),
            rationale=str(item.get("rationale", "")).strip(),
            candidate_answers=answer_ids,
            candidate_answer_texts=answer_texts,
        )
        h_dists = [
            _distribution_for_hypothesis(item, hypothesis, answer_ids)
            for hypothesis in hypotheses
        ]
        rows.append((candidate, h_dists))
    return rows


def _extract_possible_answers(item: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    raw_answers = item.get("possible_answers")
    if raw_answers is None:
        raw_answers = item.get("candidate_answers")

    answer_ids: list[str] = []
    answer_texts: dict[str, str] = {}
    if isinstance(raw_answers, list):
        for index, answer in enumerate(raw_answers, start=1):
            if isinstance(answer, dict):
                aid = str(answer.get("id") or f"A{index}").strip()
                text = str(answer.get("answer") or answer.get("text") or "").strip()
            else:
                aid = f"A{index}"
                text = str(answer).strip()
            if not aid or not text:
                continue
            answer_ids.append(aid)
            answer_texts[aid] = text
    return answer_ids, answer_texts


def _distribution_for_hypothesis(
    item: dict[str, Any],
    hypothesis: Hypothesis,
    candidate_answers: list[str],
) -> dict[str, float]:
    raw_dist: Any = {}
    raw_likelihoods = item.get("likelihoods")
    if isinstance(raw_likelihoods, list):
        for row in raw_likelihoods:
            if not isinstance(row, dict):
                continue
            label = row.get("hypothesis_id") or row.get("hid") or row.get("id")
            if label == hypothesis.hid:
                raw_dist = row.get("probs") or row.get("distribution") or row.get("probabilities") or {}
                break
    else:
        raw_distributions = (
            item.get("answer_distributions")
            or item.get("per_hypothesis_answer_distributions")
            or item.get("hypothesis_answer_probabilities")
            or item.get("distributions")
        )
        if isinstance(raw_distributions, dict):
            raw_dist = raw_distributions.get(hypothesis.hid) or raw_distributions.get(hypothesis.summary) or {}

    dist = {
        answer: _coerce_probability(raw_dist.get(answer)) if isinstance(raw_dist, dict) else 0.0
        for answer in candidate_answers
    }
    return normalize(dist)


def _coerce_probability(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(number, 0.0)


def _validate_bed_action_payload(
    payload: dict[str, Any],
    *,
    num_hypotheses: int,
    num_candidates: int,
) -> None:
    action = payload.get("action")
    if not isinstance(action, str) or action.strip().lower() not in {"ask", "answer"}:
        raise ValueError("Expected field 'action' to be 'ask' or 'answer'.")
    action = action.strip().lower()
    if action == "answer":
        code = payload.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("Answer action must include non-empty 'code'.")
        return

    hypotheses = payload.get("hypotheses")
    if not isinstance(hypotheses, list) or len(hypotheses) != num_hypotheses:
        raise ValueError(f"Ask action must include exactly {num_hypotheses} hypotheses.")
    hypothesis_ids: list[str] = []
    for index, item in enumerate(hypotheses, start=1):
        if not isinstance(item, dict):
            raise ValueError("Each hypothesis must be an object.")
        hid = str(item.get("id") or item.get("hid") or "").strip()
        if not hid:
            raise ValueError(f"Hypothesis {index} must include a non-empty id.")
        if hid in hypothesis_ids:
            raise ValueError(f"Duplicate hypothesis id {hid}.")
        hypothesis_ids.append(hid)
        summary = item.get("complete_requirement", item.get("summary"))
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("Each hypothesis must include a non-empty complete_requirement.")
        try:
            float(item.get("probability", item.get("prior")))
        except (TypeError, ValueError):
            raise ValueError(f"Hypothesis {hid} must include numeric probability.") from None

    candidates = payload.get("candidate_questions") or payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != num_candidates:
        raise ValueError(f"Ask action must include exactly {num_candidates} candidate questions.")
    for item in candidates:
        _validate_candidate_question(item, hypothesis_ids)


def _validate_candidate_question(item: Any, hypothesis_ids: list[str]) -> None:
    if not isinstance(item, dict):
        raise ValueError("Each candidate question must be an object.")
    question = item.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Each candidate question must include a non-empty 'question'.")

    answers, _answer_texts = _extract_possible_answers(item)
    if not answers:
        raise ValueError("Each candidate question must include non-empty possible_answers.")
    if len(set(answers)) != len(answers):
        raise ValueError("Candidate answer ids must be unique.")

    likelihoods = item.get("likelihoods")
    if not isinstance(likelihoods, list) or len(likelihoods) != len(hypothesis_ids):
        raise ValueError("Each candidate question must include one likelihood row per hypothesis.")

    seen_hypotheses: list[str] = []
    for row in likelihoods:
        if not isinstance(row, dict):
            raise ValueError("Each likelihood row must be an object.")
        hid = str(row.get("hypothesis_id") or "").strip()
        if not hid:
            raise ValueError("Each likelihood row must include hypothesis_id.")
        seen_hypotheses.append(hid)
        raw_dist = row.get("probs")
        if not isinstance(raw_dist, dict):
            raise ValueError(f"Likelihood row for {hid} must include probs.")
        unexpected = sorted(set(str(key) for key in raw_dist) - set(answers))
        if unexpected:
            raise ValueError(f"Likelihood row for {hid} contains unknown answer ids: {unexpected}.")
        for answer in answers:
            try:
                float(raw_dist[answer])
            except (KeyError, TypeError, ValueError):
                raise ValueError(
                    f"Likelihood row for {hid} is missing numeric probability for answer id {answer}."
                ) from None
        if sum(_coerce_probability(raw_dist.get(answer)) for answer in answers) <= 0:
            raise ValueError(f"Answer distribution for hypothesis {hid} must have positive mass.")

    if sorted(seen_hypotheses) != sorted(hypothesis_ids):
        raise ValueError("Likelihood hypothesis ids must exactly match hypotheses.")
