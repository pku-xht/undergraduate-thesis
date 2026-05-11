from __future__ import annotations

import json
import re

from clareval_experiment.bed.utils import UNKNOWN_OR_IRRELEVANT_ANSWER
from clareval_experiment.llm.base import LLMBackend


class MockBackend(LLMBackend):
    def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        *,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> str:
        lowered = f"{system}\n{user}".lower()

        if "choose exactly one action" in lowered and '"action"' in lowered:
            turns = lowered.count("agent:") + lowered.count('"role": "agent"')
            if turns < 2:
                if "candidate_questions" in lowered and "likelihoods" in lowered:
                    payload = {
                        "action": "ask",
                        "rationale": "Mock asks while clarification is still missing.",
                        "hypotheses": [
                            {
                                "id": "H1",
                                "complete_requirement": "The user wants the function contract, expected output, and edge-case behavior clarified.",
                                "probability": 0.25,
                            },
                            {
                                "id": "H2",
                                "complete_requirement": "The main uncertainty is the high-level goal of the function.",
                                "probability": 0.25,
                            },
                            {
                                "id": "H3",
                                "complete_requirement": "The task mixes missing premises with vague terminology.",
                                "probability": 0.25,
                            },
                            {
                                "id": "H4",
                                "complete_requirement": "The user may already have provided enough detail.",
                                "probability": 0.25,
                            },
                        ],
                        "candidate_questions": [
                            {
                                "id": "Q1",
                                "question": "What exact input and output behavior should this function have?",
                                "rationale": "Directly clarifies the task contract.",
                                "possible_answers": [
                                    {"id": "A1", "answer": "It should take a list of floats and a threshold, and return a boolean."},
                                    {"id": "A2", "answer": "It should clarify the main goal before implementation."},
                                    {"id": "A3", "answer": "It should handle vague input and result terms explicitly."},
                                ],
                                "likelihoods": [
                                    {"hypothesis_id": "H1", "probs": {"A1": 0.8, "A2": 0.1, "A3": 0.1}},
                                    {"hypothesis_id": "H2", "probs": {"A1": 0.1, "A2": 0.8, "A3": 0.1}},
                                    {"hypothesis_id": "H3", "probs": {"A1": 0.1, "A2": 0.1, "A3": 0.8}},
                                    {"hypothesis_id": "H4", "probs": {"A1": 0.34, "A2": 0.33, "A3": 0.33}},
                                ],
                            },
                            {
                                "id": "Q2",
                                "question": "Are there any edge cases or constraints the function must handle?",
                                "rationale": "Targets remaining acceptance criteria.",
                                "possible_answers": [
                                    {"id": "A1", "answer": "It should include examples in the docstring."},
                                    {"id": "A2", "answer": "No additional constraints are important."},
                                ],
                                "likelihoods": [
                                    {"hypothesis_id": "H1", "probs": {"A1": 0.7, "A2": 0.3}},
                                    {"hypothesis_id": "H2", "probs": {"A1": 0.3, "A2": 0.7}},
                                    {"hypothesis_id": "H3", "probs": {"A1": 0.5, "A2": 0.5}},
                                    {"hypothesis_id": "H4", "probs": {"A1": 0.2, "A2": 0.8}},
                                ],
                            },
                            {
                                "id": "Q3",
                                "question": "What is the main purpose of the function?",
                                "rationale": "Clarifies the intended goal.",
                                "possible_answers": [
                                    {"id": "A1", "answer": "The function should compare close numeric pairs."},
                                    {"id": "A2", "answer": "The function should transform the input."},
                                ],
                                "likelihoods": [
                                    {"hypothesis_id": "H1", "probs": {"A1": 0.8, "A2": 0.2}},
                                    {"hypothesis_id": "H2", "probs": {"A1": 0.3, "A2": 0.7}},
                                    {"hypothesis_id": "H3", "probs": {"A1": 0.5, "A2": 0.5}},
                                    {"hypothesis_id": "H4", "probs": {"A1": 0.5, "A2": 0.5}},
                                ],
                            },
                            {
                                "id": "Q4",
                                "question": "What should happen for invalid or empty inputs?",
                                "rationale": "Clarifies boundary behavior.",
                                "possible_answers": [
                                    {"id": "A1", "answer": "Return false for empty or single-element inputs."},
                                    {"id": "A2", "answer": "Raise an exception for invalid inputs."},
                                ],
                                "likelihoods": [
                                    {"hypothesis_id": "H1", "probs": {"A1": 0.6, "A2": 0.4}},
                                    {"hypothesis_id": "H2", "probs": {"A1": 0.5, "A2": 0.5}},
                                    {"hypothesis_id": "H3", "probs": {"A1": 0.4, "A2": 0.6}},
                                    {"hypothesis_id": "H4", "probs": {"A1": 0.7, "A2": 0.3}},
                                ],
                            },
                        ],
                    }
                else:
                    payload = {
                        "action": "ask",
                        "question": (
                            "What exact input and output behavior should this function have?"
                            if turns == 0
                            else "Are there any edge cases or constraints the function must handle?"
                        ),
                        "rationale": "Mock asks while clarification is still missing.",
                    }
            else:
                payload = {
                    "action": "answer",
                    "code": (
                        "from typing import List\n\n"
                        "def has_close_elements(numbers: List[float], threshold: float) -> bool:\n"
                        "    return any(abs(a - b) < threshold for i, a in enumerate(numbers) for b in numbers[i + 1:])\n"
                    ),
                    "rationale": "Mock answers after two clarification questions.",
                }
            return json.dumps(payload, ensure_ascii=True)

        if "simulate a software developer" in lowered:
            premises = re.findall(r"^\d+\.\s*(.+)$", user, flags=re.MULTILINE)
            match = re.search(
                r"Clarification question asked:\s*([^\r\n]+)",
                user,
                re.IGNORECASE,
            )
            question = match.group(1) if match else user
            if "input and output" in question.lower():
                return premises[0] if premises else UNKNOWN_OR_IRRELEVANT_ANSWER
            if "main purpose" in question.lower():
                return premises[min(1, len(premises) - 1)] if premises else UNKNOWN_OR_IRRELEVANT_ANSWER
            if "edge cases" in question.lower():
                return premises[-1] if premises else UNKNOWN_OR_IRRELEVANT_ANSWER
            return UNKNOWN_OR_IRRELEVANT_ANSWER

        if "evaluating whether generated code satisfies" in lowered:
            gold_match = re.search(
                r"Ground-truth missing premises:\s*(.*?)\n\nGenerated Python code:",
                user,
                re.IGNORECASE | re.DOTALL,
            )
            candidate = re.search(
                r"Generated Python code:\s*(.*?)\n\nFor each",
                user,
                re.IGNORECASE | re.DOTALL,
            )
            candidate_tokens = set(re.findall(r"\w+", candidate.group(1).lower())) if candidate else set()
            try:
                premises = json.loads(gold_match.group(1)) if gold_match else []
            except json.JSONDecodeError:
                premises = []
            premise_results = []
            for premise in premises:
                gold_tokens = set(re.findall(r"\w+", str(premise).lower()))
                covered = bool(gold_tokens) and len(gold_tokens & candidate_tokens) >= max(1, len(gold_tokens) // 4)
                premise_results.append(
                    {
                        "premise": premise,
                        "covered": covered,
                        "reasoning": "Mock lexical overlap.",
                    }
                )
            return json.dumps({"premise_results": premise_results})

        return "{}"
