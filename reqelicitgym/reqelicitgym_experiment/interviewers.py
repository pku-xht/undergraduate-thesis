"""LLM-backed interviewer policies for Direct, BED, and Aspect-aware runs."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
from typing import Any, Dict, List, Optional, Tuple

from .llm_client import LLMClient
from .llm_gym import history_to_text


class InvalidInterviewerResponse(ValueError):
    """Raised when an interviewer LLM response fails schema validation."""


@dataclass
class CandidateScore:
    question: str
    rationale: str
    possible_answers: List[Dict[str, str]]
    answer_likelihoods: List[List[float]]
    expected_answer_probs: List[float]
    prior_entropy: float
    expected_posterior_entropy: float
    eig: float


def entropy(probs: List[float]) -> float:
    return -sum(p * math.log2(p) for p in probs if p > 0)


def normalize(probs: List[float]) -> List[float]:
    total = sum(max(0.0, p) for p in probs)
    if total <= 0:
        return [1.0 / len(probs)] * len(probs)
    return [max(0.0, p) / total for p in probs]


def json_like(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)


def call_validated_json(
    llm: LLMClient,
    system: str,
    user: str,
    validator,
    *,
    temperature: float,
    max_tokens: int,
) -> Dict[str, Any]:
    """Call an LLM, validate the JSON object, and retry once on parse/schema failure."""
    last_error = ""
    for attempt in range(2):
        system_suffix = ""
        if attempt:
            system_suffix = (
                "\n\nYour previous response had invalid JSON or did not match the required schema. "
                f"Validation error: {last_error}\n"
                "Return exactly one valid JSON object following the schema. No Markdown."
            )
        try:
            result = llm.json_once(system + system_suffix, user, temperature=temperature, max_tokens=max_tokens)
            validator(result)
            return result
        except Exception as exc:
            last_error = str(exc)
    raise InvalidInterviewerResponse(last_error)


def require_action(result: Dict[str, Any], *, valid_actions: Tuple[str, ...] = ("ask", "finish")) -> str:
    action = str(result.get("action") or "").strip()
    if action not in valid_actions:
        raise InvalidInterviewerResponse(f"`action` must be one of {valid_actions}.")
    rationale = str(result.get("rationale") or "").strip()
    if not rationale:
        raise InvalidInterviewerResponse("`rationale` must be a non-empty string.")
    return action


def require_exact_keys(result: Dict[str, Any], allowed_keys: Tuple[str, ...], *, action: str) -> None:
    unexpected = sorted(set(result) - set(allowed_keys))
    if unexpected:
        raise InvalidInterviewerResponse(
            f"Unexpected top-level field(s) for action {action}: {', '.join(unexpected)}."
        )


def validate_direct_response(result: Dict[str, Any]) -> None:
    action = require_action(result)
    if action == "finish":
        require_exact_keys(result, ("action", "rationale"), action=action)
        return
    require_exact_keys(result, ("action", "question", "rationale"), action=action)
    if not str(result.get("question") or "").strip():
        raise InvalidInterviewerResponse("`question` must be a non-empty string when action is ask.")


def validate_aspect_response(result: Dict[str, Any], valid_aspects: Dict[str, str]) -> None:
    action = require_action(result)
    if action == "finish":
        require_exact_keys(result, ("action", "rationale"), action=action)
        return
    require_exact_keys(result, ("action", "selected_aspect", "question", "rationale"), action=action)
    if not str(result.get("question") or "").strip():
        raise InvalidInterviewerResponse("`question` must be a non-empty string when action is ask.")
    selected_aspect = str(result.get("selected_aspect") or "").strip()
    if selected_aspect not in valid_aspects:
        raise InvalidInterviewerResponse(
            f"`selected_aspect` must be one of {sorted(valid_aspects)} when action is ask."
        )


def validate_bed_response(result: Dict[str, Any], *, num_hypotheses: int, num_candidates: int) -> None:
    action = require_action(result)
    if action == "finish":
        require_exact_keys(result, ("action", "rationale"), action=action)
        return
    require_exact_keys(result, ("action", "rationale", "belief_state", "candidates"), action=action)
    belief_state = result.get("belief_state")
    if not isinstance(belief_state, dict):
        raise InvalidInterviewerResponse("`belief_state` must be an object when action is ask.")
    hypotheses = belief_state.get("hypotheses")
    if not isinstance(hypotheses, list) or len(hypotheses) != num_hypotheses:
        raise InvalidInterviewerResponse(f"`belief_state.hypotheses` must contain exactly {num_hypotheses} items.")
    hypothesis_ids: List[str] = []
    for idx, hypothesis in enumerate(hypotheses, start=1):
        if not isinstance(hypothesis, dict):
            raise InvalidInterviewerResponse(f"hypothesis {idx} must be an object.")
        hypothesis_id = str(hypothesis.get("id") or "").strip()
        if not hypothesis_id:
            raise InvalidInterviewerResponse(f"hypothesis {idx} must have a non-empty `id`.")
        if not str(hypothesis.get("complete_requirement") or "").strip():
            raise InvalidInterviewerResponse(f"hypothesis {idx} must have `complete_requirement`.")
        try:
            float(hypothesis.get("probability"))
        except (TypeError, ValueError):
            raise InvalidInterviewerResponse(f"hypothesis {idx} must have numeric `probability`.")
        hypothesis_ids.append(hypothesis_id)

    candidates = result.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != num_candidates:
        raise InvalidInterviewerResponse(f"`candidates` must contain exactly {num_candidates} items.")
    for idx, candidate in enumerate(candidates, start=1):
        if not isinstance(candidate, dict):
            raise InvalidInterviewerResponse(f"candidate {idx} must be an object.")
        if not str(candidate.get("id") or "").strip():
            raise InvalidInterviewerResponse(f"candidate {idx} must have a non-empty `id`.")
        if not str(candidate.get("question") or "").strip():
            raise InvalidInterviewerResponse(f"candidate {idx} must have a non-empty `question`.")
        possible_answers = candidate.get("possible_answers")
        if not isinstance(possible_answers, list) or not possible_answers:
            raise InvalidInterviewerResponse(f"candidate {idx} must include non-empty `possible_answers`.")
        answer_ids = []
        for answer in possible_answers:
            if not isinstance(answer, dict) or not str(answer.get("id") or "").strip():
                raise InvalidInterviewerResponse(f"candidate {idx} possible answers must have ids.")
            answer_ids.append(str(answer["id"]))
        likelihoods = candidate.get("likelihoods")
        if not isinstance(likelihoods, list) or len(likelihoods) != num_hypotheses:
            raise InvalidInterviewerResponse(
                f"candidate {idx} must include likelihood rows for exactly {num_hypotheses} hypotheses."
            )
        likelihood_ids = []
        for row in likelihoods:
            if not isinstance(row, dict):
                raise InvalidInterviewerResponse(f"candidate {idx} likelihood rows must be objects.")
            hypothesis_id = str(row.get("hypothesis_id") or "").strip()
            likelihood_ids.append(hypothesis_id)
            probs = row.get("probs")
            if not isinstance(probs, dict):
                raise InvalidInterviewerResponse(f"candidate {idx} likelihood row must include `probs`.")
            for answer_id in answer_ids:
                try:
                    float(probs[answer_id])
                except (KeyError, TypeError, ValueError):
                    raise InvalidInterviewerResponse(
                        f"candidate {idx} likelihood row for {hypothesis_id} is missing numeric prob {answer_id}."
                    )
        if sorted(likelihood_ids) != sorted(hypothesis_ids):
            raise InvalidInterviewerResponse(f"candidate {idx} likelihood hypothesis ids must match hypotheses.")


class DirectBaseline:
    """Direct clarification-prompting baseline."""

    name = "direct"

    def __init__(self, llm: LLMClient, max_questions: int = 5):
        self.llm = llm
        self.max_questions = max_questions
        self.turn = 0

    def reset(self) -> None:
        self.turn = 0

    def ask_question(self, observation: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        self.turn += 1
        if self.turn > self.max_questions:
            return "", {
                "method": self.name,
                "turn": self.turn,
                "decision": "finish",
                "finish": True,
                "finish_reason": "max_questions_reached",
            }

        system = (
            "You are a requirements elicitation interviewer.\n\n"
            "Choose exactly one action:\n"
            "- ask: ask one clarification question if important requirement information is still missing.\n"
            "- finish: stop asking if the visible dialogue is already sufficient or further clarification is unlikely to help.\n\n"
            "Clarification questions must be open-ended. Do not include answer options, multiple-choice choices, "
            "suggested answers, examples of possible answers, or \"choose one\" wording.\n\n"
            "Return only valid JSON with no Markdown:\n"
            "{\"action\": \"ask\", \"question\": \"...\", \"rationale\": \"...\"}\n"
            "or\n"
            "{\"action\": \"finish\", \"rationale\": \"...\"}"
        )
        user = (
            f"Task name: {observation.get('task_name')}\n"
            f"Application type: {observation.get('application_type')}\n"
            f"Initial requirement: {observation.get('initial_requirements')}\n\n"
            "Conversation:\n"
            f"{history_to_text(observation.get('conversation_history', []))}"
        )
        result = call_validated_json(
            self.llm,
            system,
            user,
            validate_direct_response,
            temperature=0.2,
            max_tokens=self.llm.max_tokens,
        )
        action = str(result.get("action"))
        if action == "finish":
            return "", {
                "method": self.name,
                "turn": self.turn,
                "decision": "finish",
                "finish": True,
                "finish_reason": "model_decided_no_more_clarification",
                **result,
            }
        question = str(result["question"]).strip()
        return question, {"method": self.name, "turn": self.turn, **result}


class AspectAwareClarifier:
    """Interaction/Content/Style-aware clarification baseline."""

    name = "aspect_aware"

    ASPECT_DEFINITIONS = {
        "Interaction": "how users operate, input, select, navigate, configure, submit, or trigger actions",
        "Content": "what information, fields, records, views, reports, or details the system should show or collect",
        "Style": "visual or presentation preferences such as layout, color, responsive behavior, or overall look",
    }

    def __init__(self, llm: LLMClient, max_questions: int = 5):
        self.llm = llm
        self.max_questions = max_questions
        self.reset()

    def reset(self) -> None:
        self.turn = 0
        self.asked_questions: List[str] = []
        self.selected_aspects: List[str] = []

    def ask_question(self, observation: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        self.turn += 1
        if self.turn > self.max_questions:
            return "", {
                "method": self.name,
                "turn": self.turn,
                "decision": "finish",
                "finish": True,
                "finish_reason": "max_questions_reached",
                "asked_questions": list(self.asked_questions),
                "selected_aspects_so_far": list(self.selected_aspects),
            }

        result = self._generate_aspect_question(observation)
        action = str(result.get("action"))
        if action == "finish":
            return "", {
                "method": self.name,
                "turn": self.turn,
                "decision": "finish",
                "finish": True,
                "finish_reason": "model_decided_no_more_clarification",
                "asked_questions": list(self.asked_questions),
                "selected_aspects_so_far": list(self.selected_aspects),
                **result,
            }
        question = str(result["question"]).strip()
        selected_aspect = str(result.get("selected_aspect") or "").strip()
        self.asked_questions.append(question)
        self.selected_aspects.append(selected_aspect)
        trace = {
            "method": self.name,
            "turn": self.turn,
            "aspect_definitions": dict(self.ASPECT_DEFINITIONS),
            "selected_aspect": selected_aspect,
            "selected_question": question,
            "rationale": result.get("rationale", ""),
            "asked_questions": list(self.asked_questions),
            "selected_aspects_so_far": list(self.selected_aspects),
            "selection_reason": "The model selected one of Interaction/Content/Style from visible context.",
        }
        return question, trace

    def _generate_aspect_question(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        system = (
            "You are a requirements elicitation interviewer.\n\n"
            "Choose exactly one action:\n"
            "- ask: ask one clarification question if important requirement information is still missing.\n"
            "- finish: stop asking if the visible dialogue is already sufficient or further clarification is unlikely to help.\n\n"
            "For ask, choose one requirement aspect and ask exactly one concise clarification question. "
            "You should pay balanced attention to three requirement aspects:\n"
            "- Interaction: how users operate, input, select, navigate, configure, submit, or trigger actions.\n"
            "- Content: what information, fields, records, views, reports, or details the system should show or collect.\n"
            "- Style: visual or presentation preferences such as layout, color, responsive behavior, or overall look.\n\n"
            "Choose the aspect yourself based only on the visible task and conversation. "
            "Clarification questions must be open-ended. Do not include answer options, multiple-choice choices, "
            "suggested answers, examples of possible answers, or \"choose one\" wording.\n\n"
            "Return only valid JSON with no Markdown:\n"
            "{\"action\": \"ask\", \"selected_aspect\": \"Interaction\", \"question\": \"...\", \"rationale\": \"...\"}\n"
            "or\n"
            "{\"action\": \"finish\", \"rationale\": \"...\"}"
        )
        user = (
            f"Task name: {observation.get('task_name')}\n"
            f"Application type: {observation.get('application_type')}\n"
            f"Initial requirement: {observation.get('initial_requirements')}\n\n"
            "Conversation:\n"
            f"{history_to_text(observation.get('conversation_history', []))}\n\n"
            "Already asked questions:\n"
            f"{json_like(self.asked_questions)}\n\n"
            "Previously selected aspects:\n"
            f"{json_like(self.selected_aspects)}\n\n"
            "Generate the next single clarification question."
        )
        return call_validated_json(
            self.llm,
            system,
            user,
            lambda result: validate_aspect_response(result, self.ASPECT_DEFINITIONS),
            temperature=0.2,
            max_tokens=self.llm.max_tokens,
        )


class BEDInterviewer:
    """Rolling-belief BED interviewer with a combined planner call per turn."""

    name = "bed"

    def __init__(self, llm: LLMClient, max_questions: int = 5, num_hypotheses: int = 4, num_candidates: int = 4):
        self.llm = llm
        self.max_questions = max_questions
        self.num_hypotheses = num_hypotheses
        self.num_candidates = num_candidates
        self.reset()

    def reset(self) -> None:
        self.turn = 0
        self.belief_state: Dict[str, Any] = {
            "hypotheses": [],
            "hypothesis_disagreements": [],
            "asked_questions": [],
            "update_notes": [],
        }

    def ask_question(self, observation: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        self.turn += 1
        if self.turn > self.max_questions:
            return "", {
                "method": self.name,
                "turn": self.turn,
                "decision": "finish",
                "finish": True,
                "finish_reason": "max_questions_reached",
                "belief_state": self.belief_state,
            }

        previous_belief = self._copy_belief_state(self.belief_state)
        planner_result = self._plan_belief_candidates_and_likelihoods(observation, previous_belief)
        if planner_result.get("action") == "finish":
            return "", {
                "method": self.name,
                "turn": self.turn,
                "decision": "finish",
                "finish": True,
                "finish_reason": "model_decided_no_more_clarification",
                "previous_belief_state": previous_belief,
                "belief_state": self.belief_state,
                "combined_planner_call": True,
                **planner_result,
            }

        self.belief_state = self._coerce_belief_state(planner_result.get("belief_state") or {})
        hypotheses = self.belief_state["hypotheses"]
        belief_before_selection = self._copy_belief_state(self.belief_state)
        candidates = self._coerce_planner_candidates(planner_result.get("candidates"))
        likelihoods = self._planner_likelihood_data(candidates, hypotheses)
        scored = [
            self._score_candidate(candidate, hypotheses, likelihoods.get(candidate.get("id", "")))
            for candidate in candidates
        ]
        scored_items = [
            {
                "candidate": candidate,
                "score": score,
                "eig": score.eig,
            }
            for candidate, score in zip(candidates, scored)
        ]
        best = max(scored_items, key=lambda item: item["eig"])
        selected_question = best["score"].question
        self.belief_state.setdefault("asked_questions", []).append(selected_question)
        belief_after_selection = self._copy_belief_state(self.belief_state)

        trace = {
            "method": self.name,
            "turn": self.turn,
            "combined_planner_call": True,
            "previous_belief_state": previous_belief,
            "belief_state_before_selection": belief_before_selection,
            "belief_state_after_selection": belief_after_selection,
            "belief_state": belief_after_selection,
            "latent_complete_requirement_hypotheses": hypotheses,
            "candidate_questions": candidates,
            "eig_formula": (
                "EIG(q)=H[p(h)] - sum_a p(a|q) H[p(h|a,q)], "
                "with rolling hypotheses from the evolving belief state."
            ),
            "scored_candidates": [
                {
                    **item["score"].__dict__,
                    "candidate": item["candidate"],
                    "selection_score": item["eig"],
                }
                for item in scored_items
            ],
            "selected_question": selected_question,
            "selection_reason": "Selected the candidate with the largest EIG.",
        }
        return selected_question, trace

    def _plan_belief_candidates_and_likelihoods(
        self,
        observation: Dict[str, Any],
        previous_belief: Dict[str, Any],
    ) -> Dict[str, Any]:
        system = (
            "You are a BED requirements interviewer.\n\n"
            "Choose exactly one action:\n"
            "- ask: continue clarification if important requirement information is still missing.\n"
            "- finish: stop asking if the visible dialogue is already sufficient or further clarification is unlikely to help.\n\n"
            "For ask, in one JSON response, update the rolling belief state, propose candidate questions, "
            "and estimate answer likelihoods needed for EIG scoring. Use only the visible task and "
            "conversation information.\n\n"
            "Clarification questions must be open-ended. Do not include answer options, multiple-choice choices, "
            "suggested answers, examples of possible answers, or \"choose one\" wording.\n\n"
            "Return only valid JSON with no Markdown.\n\n"
            "For finish:\n"
            "{\"action\": \"finish\", \"rationale\": \"why no more clarification is needed\"}\n\n"
            "For ask:\n"
            "{\n"
            "  \"action\": \"ask\",\n"
            "  \"rationale\": \"why another clarification question is useful\",\n"
            "  \"belief_state\": {\n"
            "    \"hypotheses\": [\n"
            "      {\n"
            "        \"id\": \"H1\",\n"
            "        \"probability\": 0.20,\n"
            "        \"complete_requirement\": \"plausible complete requirement\"\n"
            "      }\n"
            "    ],\n"
            "    \"hypothesis_disagreements\": [\"unresolved dimension\"],\n"
            "    \"asked_questions\": [],\n"
            "    \"update_notes\": [\"brief note\"]\n"
            "  },\n"
            "  \"candidates\": [\n"
            "    {\n"
            "      \"id\": \"Q1\",\n"
            "      \"question\": \"one focused question\",\n"
            "      \"rationale\": \"what uncertainty this question should reduce\",\n"
            "      \"possible_answers\": [\n"
            "        {\"id\": \"A1\", \"answer\": \"possible answer type\"},\n"
            "        {\"id\": \"A2\", \"answer\": \"another possible answer type\"}\n"
            "      ],\n"
            "      \"likelihoods\": [\n"
            "        {\n"
            "          \"hypothesis_id\": \"H1\",\n"
            "          \"probs\": {\"A1\": 0.6, \"A2\": 0.4},\n"
            "          \"rationale\": \"brief\"\n"
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}"
        )
        user = (
            f"Task name: {observation.get('task_name')}\n"
            f"Application type: {observation.get('application_type')}\n"
            f"Initial requirement: {observation.get('initial_requirements')}\n\n"
            "Conversation:\n"
            f"{history_to_text(observation.get('conversation_history', []))}\n\n"
            "Previous belief state:\n"
            f"{json_like(previous_belief)}\n\n"
            "Instructions:\n"
            "- If this is the first turn, initialize hypotheses and unresolved disagreements.\n"
            "- If this is a later turn, update the prior belief state using the latest user answer.\n"
            f"- Keep exactly {self.num_hypotheses} diverse hypotheses.\n"
            "- Hypothesis probabilities must sum to 1 before normalization.\n"
            "- Preserve prior asked_questions in the belief state.\n"
            f"- Generate exactly {self.num_candidates} focused one-at-a-time candidate questions.\n"
            "- Candidate questions should distinguish plausible hypotheses.\n"
            "- For each candidate, define compact possible answer types for that question.\n"
            "- For each hypothesis, estimate probabilities over that candidate's possible answer types."
        )
        return call_validated_json(
            self.llm,
            system,
            user,
            lambda result: validate_bed_response(
                result,
                num_hypotheses=self.num_hypotheses,
                num_candidates=self.num_candidates,
            ),
            temperature=0.25,
            max_tokens=self.llm.max_tokens,
        )

    def _score_candidate(
        self,
        candidate: Dict[str, Any],
        hypotheses: List[Dict[str, Any]],
        likelihood_data: Optional[Dict[str, Any]],
    ) -> CandidateScore:
        priors = normalize([float(h.get("probability", 0.0)) for h in hypotheses])
        prior_entropy = entropy(priors)
        if not likelihood_data:
            raise InvalidInterviewerResponse("Missing likelihood data for candidate.")

        possible_answers = likelihood_data.get("possible_answers", [])
        likelihoods = likelihood_data.get("matrix", [])
        if not possible_answers or len(likelihoods) != len(hypotheses):
            raise InvalidInterviewerResponse("Invalid likelihood data for candidate.")

        num_answers = len(possible_answers)
        expected_answer_probs = [
            sum(priors[h_idx] * likelihoods[h_idx][a_idx] for h_idx in range(len(hypotheses)))
            for a_idx in range(num_answers)
        ]
        expected_posterior_entropy = 0.0
        for a_idx, answer_prob in enumerate(expected_answer_probs):
            if answer_prob <= 0:
                continue
            posterior = [
                priors[h_idx] * likelihoods[h_idx][a_idx] / answer_prob
                for h_idx in range(len(hypotheses))
            ]
            expected_posterior_entropy += answer_prob * entropy(posterior)
        eig = prior_entropy - expected_posterior_entropy
        return CandidateScore(
            question=candidate.get("question", ""),
            rationale=candidate.get("rationale", ""),
            possible_answers=possible_answers,
            answer_likelihoods=likelihoods,
            expected_answer_probs=expected_answer_probs,
            prior_entropy=prior_entropy,
            expected_posterior_entropy=expected_posterior_entropy,
            eig=eig,
        )

    def _coerce_planner_candidates(self, value: Any) -> List[Dict[str, Any]]:
        candidates = value if isinstance(value, list) else []
        coerced: List[Dict[str, Any]] = []
        for idx, candidate in enumerate(candidates[: self.num_candidates], start=1):
            if not isinstance(candidate, dict):
                continue
            candidate = dict(candidate)
            candidate["id"] = candidate.get("id") or f"Q{idx}"
            candidate["question"] = str(candidate.get("question") or "").strip()
            if not candidate["question"]:
                continue
            candidate["rationale"] = str(candidate.get("rationale") or "")
            coerced.append(candidate)
        return coerced[: self.num_candidates]

    def _planner_likelihood_data(
        self,
        candidates: List[Dict[str, Any]],
        hypotheses: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        parsed: Dict[str, Dict[str, Any]] = {}
        for candidate in candidates:
            candidate_id = candidate.get("id", "")
            possible_answers = candidate.get("possible_answers", [])
            answer_ids = [
                str(answer.get("id", ""))
                for answer in possible_answers
                if isinstance(answer, dict) and answer.get("id")
            ]
            by_id = {
                row.get("hypothesis_id"): row
                for row in candidate.get("likelihoods", [])
                if isinstance(row, dict)
            }
            matrix: List[List[float]] = []
            for hypothesis in hypotheses:
                probs_obj = by_id.get(hypothesis.get("id"), {}).get("probs", {})
                matrix.append(normalize([float(probs_obj.get(answer_id, 0.0)) for answer_id in answer_ids]))
            parsed[candidate_id] = {
                "possible_answers": possible_answers,
                "matrix": matrix,
            }
        return parsed

    def _coerce_belief_state(self, result: Dict[str, Any]) -> Dict[str, Any]:
        hypotheses = list(result.get("hypotheses") or [])
        hypotheses = hypotheses[: self.num_hypotheses]
        probs = normalize([float(h.get("probability", 0.0)) for h in hypotheses])
        for idx, (hypothesis, prob) in enumerate(zip(hypotheses, probs), start=1):
            hypothesis["id"] = hypothesis.get("id") or f"H{idx}"
            hypothesis["probability"] = prob

        return {
            "hypotheses": hypotheses,
            "hypothesis_disagreements": self._coerce_string_list(result.get("hypothesis_disagreements")),
            "asked_questions": list(self.belief_state.get("asked_questions", [])),
            "update_notes": self._coerce_string_list(result.get("update_notes")),
        }

    def _coerce_string_list(self, value: Any) -> List[str]:
        if not value:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item) for item in value if item]
        return []

    def _clamped_float(self, value: Any, *, default: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = default
        return min(1.0, max(0.0, number))

    def _copy_belief_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "hypotheses": deepcopy(state.get("hypotheses", [])),
            "hypothesis_disagreements": list(state.get("hypothesis_disagreements", [])),
            "asked_questions": list(state.get("asked_questions", [])),
            "update_notes": list(state.get("update_notes", [])),
        }


def build_interviewer(
    method: str,
    llm: LLMClient,
    *,
    max_questions: int,
    num_hypotheses: int = 4,
    num_candidates: int = 4,
):
    if method == "bed":
        return BEDInterviewer(
            llm,
            max_questions=max_questions,
            num_hypotheses=num_hypotheses,
            num_candidates=num_candidates,
        )
    if method == "aspect_aware":
        return AspectAwareClarifier(llm, max_questions=max_questions)
    if method == "direct":
        return DirectBaseline(llm, max_questions=max_questions)
    raise ValueError(f"Unknown method: {method}")
