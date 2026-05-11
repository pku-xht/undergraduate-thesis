"""LLM-backed ReqElicitGym-style environment for one or more tasks."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .llm_client import LLMClient


def load_tasks(data_path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    with data_path.open("r", encoding="utf-8") as f:
        if data_path.suffix == ".jsonl":
            tasks = [json.loads(line) for line in f if line.strip()]
        else:
            tasks = json.load(f)
    return tasks[:limit] if limit is not None else tasks


def history_to_text(history: List[Dict[str, str]]) -> str:
    return "\n".join(f"{item['role'].title()}: {item['content']}" for item in history)


@dataclass
class RequirementState:
    id: str
    aspect: str
    text: str
    elicited: bool = False


class InvalidEvaluatorResponse(ValueError):
    """Raised when the evaluator/stakeholder response fails schema validation."""


class LLMReqElicitEpisode:
    """One episode using a combined LLM evaluator/stakeholder simulator."""

    NO_PREFERENCE_RESPONSE = "I do not have a strong preference about that, or it is not important to me."

    def __init__(
        self,
        task: Dict[str, Any],
        llm: LLMClient,
        step_budget: Optional[int] = None,
        *,
        judge_llm: Optional[LLMClient] = None,
    ):
        self.task = task
        self.llm = llm
        self.evaluator_llm = judge_llm or llm
        self.step_budget = step_budget if step_budget is not None else len(task.get("Implicit Requirements", []))
        self.step_count = 0
        self.conversation: List[Dict[str, str]] = [
            {"role": "user", "content": task.get("initial_requirements", "")}
        ]
        self.requirements = [
            RequirementState(
                id=f"IR{i + 1}",
                aspect=req.get("Aspect", ""),
                text=req.get("RequirementText", ""),
            )
            for i, req in enumerate(task.get("Implicit Requirements", []))
        ]
        self.hit_sequence: List[int] = []
        self.turn_records: List[Dict[str, Any]] = []

    @property
    def remaining(self) -> List[RequirementState]:
        return [req for req in self.requirements if not req.elicited]

    @property
    def elicited(self) -> List[RequirementState]:
        return [req for req in self.requirements if req.elicited]

    def observation(self) -> Dict[str, Any]:
        return {
            "task_name": self.task.get("name", ""),
            "application_type": self.task.get("application_type", ""),
            "initial_requirements": self.task.get("initial_requirements", ""),
            "conversation_history": list(self.conversation),
            "conversation_text": history_to_text(self.conversation),
            "step_count": self.step_count,
            "elicitation_ratio": self.elicitation_ratio(),
        }

    def step(self, action: str, decision_trace: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any], bool]:
        self.step_count += 1
        self.conversation.append({"role": "interviewer", "content": action})
        judgement = self._evaluate_and_respond(action)
        relevant_ids = judgement.get("relevant_implied_requirements_ids") or []
        if isinstance(relevant_ids, str):
            relevant_ids = [relevant_ids]

        elicited_now: List[RequirementState] = []
        valid_ids: List[str] = []
        for req_id in relevant_ids:
            for req in self.remaining:
                if req.id == req_id:
                    valid_ids.append(req_id)
                    req.elicited = True
                    elicited_now.append(req)
                    break
            if valid_ids:
                break
        if len(relevant_ids) > 1:
            judgement["trace_warning"] = (
                "Evaluator returned multiple requirement ids; only the first valid remaining id was used."
            )
        if relevant_ids and not valid_ids:
            judgement["trace_warning"] = "Evaluator returned no valid remaining requirement id."

        is_hit = bool(elicited_now)
        self.hit_sequence.append(1 if is_hit else 0)
        user_response = elicited_now[0].text if is_hit else self.NO_PREFERENCE_RESPONSE
        judgement["response"] = user_response
        self.conversation.append({"role": "user", "content": user_response})
        action_type = "clarify" if is_hit else "probe"

        turn_record = {
            "turn": self.step_count,
            "interviewer": action,
            "user": user_response,
            "action_type": action_type,
            "elicited_requirement_ids": [req.id for req in elicited_now],
            "elicited_requirements": [req.text for req in elicited_now],
            "judge": judgement,
            "evaluator": judgement,
            "bed_decision_trace": decision_trace,
            "elicitation_ratio": self.elicitation_ratio(),
        }
        self.turn_records.append(turn_record)

        done = self.step_count >= self.step_budget
        return user_response, turn_record, done

    def finish(self, decision_trace: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """End the episode without sending a synthetic finish utterance to judge/user."""
        turn_record = {
            "turn": self.step_count + 1,
            "interviewer": None,
            "user": None,
            "action_type": "finish",
            "elicited_requirement_ids": [],
            "elicited_requirements": [],
            "judge": None,
            "evaluator": None,
            "bed_decision_trace": decision_trace,
            "elicitation_ratio": self.elicitation_ratio(),
            "finish_without_judge": True,
        }
        self.turn_records.append(turn_record)
        return turn_record

    def _evaluate_and_respond(self, action: str) -> Dict[str, Any]:
        remaining_text = "\n".join(
            f"{req.id}: Aspect={req.aspect}; Requirement={req.text}" for req in self.remaining
        )
        system = (
            "You are an expert requirements-elicitation evaluator and simulated stakeholder.\n\n"
            "Your task has two parts:\n"
            "1. Judge whether the interviewer's latest question directly asks about exactly one "
            "of the remaining hidden implicit requirements.\n"
            "2. Return the simulated stakeholder response for the next dialogue turn.\n\n"
            "Return JSON only with this format:\n"
            "{\n"
            "  \"is_relevant_to_implied_requirements\": true,\n"
            "  \"relevant_implied_requirements_ids\": [\"IR1\"],\n"
            "  \"reasoning\": \"brief explanation\",\n"
            "  \"response\": \"the simulated user response\"\n"
            "}\n\n"
            "Rules:\n"
            "- Mark at most one requirement id.\n"
            "- Mark a requirement only if the latest question directly asks about that remaining hidden implicit requirement.\n"
            "- If multiple requirements seem relevant, choose the single most directly asked one.\n"
            "- If no requirement is elicited, set \"relevant_implied_requirements_ids\" to [].\n"
            "- If a requirement is elicited, the response must include the exact text of that hidden implicit requirement in natural first-person wording.\n"
            f"- If no requirement is elicited, the response must be exactly: \"{self.NO_PREFERENCE_RESPONSE}\"\n"
            "- Do not invent new requirements or preferences."
        )
        user = (
            "Initial user requirement:\n"
            f"{self.task.get('initial_requirements', '')}\n\n"
            "Conversation so far:\n"
            f"{history_to_text(self.conversation[:-1])}\n\n"
            "Interviewer's latest question:\n"
            f"{action}\n\n"
            "Remaining hidden implicit requirements:\n"
            f"{remaining_text if remaining_text else 'None'}"
        )
        return self._call_evaluator_json(system, user)

    def _call_evaluator_json(self, system: str, user: str) -> Dict[str, Any]:
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
                result = self.evaluator_llm.json(
                    system + system_suffix,
                    user,
                    temperature=0.0,
                    max_tokens=self.evaluator_llm.max_tokens,
                )
                self._validate_evaluator_response(result)
                return result
            except Exception as exc:
                last_error = str(exc)
        raise InvalidEvaluatorResponse(last_error)

    def _validate_evaluator_response(self, result: Dict[str, Any]) -> None:
        if not isinstance(result, dict):
            raise InvalidEvaluatorResponse("Evaluator response must be a JSON object.")
        required = {
            "is_relevant_to_implied_requirements",
            "relevant_implied_requirements_ids",
            "reasoning",
            "response",
        }
        missing = sorted(required - set(result))
        if missing:
            raise InvalidEvaluatorResponse(f"Evaluator response is missing fields: {', '.join(missing)}.")
        if not isinstance(result["is_relevant_to_implied_requirements"], bool):
            raise InvalidEvaluatorResponse("`is_relevant_to_implied_requirements` must be boolean.")
        relevant_ids = result["relevant_implied_requirements_ids"]
        if not isinstance(relevant_ids, list) or not all(isinstance(item, str) for item in relevant_ids):
            raise InvalidEvaluatorResponse("`relevant_implied_requirements_ids` must be a list of strings.")
        if not isinstance(result["reasoning"], str) or not result["reasoning"].strip():
            raise InvalidEvaluatorResponse("`reasoning` must be a non-empty string.")
        if not isinstance(result["response"], str) or not result["response"].strip():
            raise InvalidEvaluatorResponse("`response` must be a non-empty string.")

    def elicitation_ratio(self) -> float:
        total = len(self.requirements)
        return len(self.elicited) / total if total else 0.0

    def tkqr(self) -> float:
        n = len(self.hit_sequence)
        k = len(self.requirements)
        if n == 0 or k == 0:
            return 0.0
        dcg = sum(hit / math.log2(i + 1) for i, hit in enumerate(self.hit_sequence, start=1))
        idcg = sum(1.0 / math.log2(i + 1) for i in range(1, min(n, k) + 1))
        return dcg / idcg if idcg else 0.0

    def ora(self) -> float:
        optimal = len(self.requirements)
        sigma = 0.425 * optimal
        return math.exp(-((self.step_count - optimal) ** 2) / (2 * sigma**2)) if optimal else 0.0

    def metrics(self) -> Dict[str, Any]:
        by_aspect: Dict[str, Dict[str, int]] = {}
        for req in self.requirements:
            stats = by_aspect.setdefault(req.aspect, {"total": 0, "elicited": 0})
            stats["total"] += 1
            stats["elicited"] += 1 if req.elicited else 0
        aspect_metrics = {
            aspect: {
                **stats,
                "elicitation_ratio": stats["elicited"] / stats["total"] if stats["total"] else 0.0,
            }
            for aspect, stats in by_aspect.items()
        }
        return {
            "task_name": self.task.get("name", ""),
            "application_type": self.task.get("application_type", ""),
            "total_requirements": len(self.requirements),
            "total_elicited": len(self.elicited),
            "elicitation_ratio": self.elicitation_ratio(),
            "tkqr": self.tkqr(),
            "ora": self.ora(),
            "num_rounds": self.step_count,
            "step_budget": self.step_budget,
            "optimal_rounds": len(self.requirements),
            "aspect_type_elicitation": aspect_metrics,
            "turns": self.turn_records,
        }


def aggregate_metrics(task_metrics: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    metrics = list(task_metrics)
    if not metrics:
        return {}
    total_requirements = sum(m["total_requirements"] for m in metrics)
    total_elicited = sum(m["total_elicited"] for m in metrics)
    return {
        "total_tasks": len(metrics),
        "total_requirements": total_requirements,
        "total_elicited": total_elicited,
        "total_elicitation_ratio": total_elicited / total_requirements if total_requirements else 0.0,
        "average_elicitation_ratio": sum(m["elicitation_ratio"] for m in metrics) / len(metrics),
        "average_tkqr": sum(m["tkqr"] for m in metrics) / len(metrics),
        "average_ora": sum(m["ora"] for m in metrics) / len(metrics),
        "average_rounds": sum(m["num_rounds"] for m in metrics) / len(metrics),
    }
