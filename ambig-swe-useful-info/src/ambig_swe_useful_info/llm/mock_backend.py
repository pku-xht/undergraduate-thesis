from __future__ import annotations

import json

from ambig_swe_useful_info.llm.base import LLMBackend


class MockBackend(LLMBackend):
    """Pattern-matched canned responses keyed off prompt content.

    Patterns are matched against `system + user` lowercased so that a single
    backend can serve every BED + Direct + proxy call site.
    """

    def complete(self, system: str, user: str, temperature: float = 0.2) -> str:
        lowered = f"{system}\n{user}".lower()

        if "bed software-issue clarification planner" in lowered:
            payload = {
                "hypotheses": [
                    {
                        "id": "H1",
                        "probability": 0.55,
                        "summary": "The issue is a narrow bug in one reported code path.",
                        "evidence": ["The issue describes a concrete failing scenario."],
                    },
                    {
                        "id": "H2",
                        "probability": 0.45,
                        "summary": "The issue reflects a broader behavior gap across related code paths.",
                        "evidence": ["The issue may generalize beyond the single example."],
                    },
                ],
                "disagreement_axes": [
                    {
                        "name": "Scope of fix",
                        "description": "Whether the fix should be narrow or broad.",
                        "positions": [
                            {"hypothesis_ids": ["H1"], "stance": "narrow reported case"},
                            {"hypothesis_ids": ["H2"], "stance": "broader related cases"},
                        ],
                    },
                    {
                        "name": "Target location",
                        "description": "Which implementation layer should change.",
                        "positions": [
                            {"hypothesis_ids": ["H1"], "stance": "method-level patch"},
                            {"hypothesis_ids": ["H2"], "stance": "parsing layer"},
                        ],
                    },
                ],
                "candidates": [
                    {
                        "id": "Q1",
                        "axis_name": "Scope of fix",
                        "question": "Could you clarify the intended scope of the fix?",
                        "rationale": "This distinguishes narrow and broad interpretations.",
                        "possible_answers": [
                            {"id": "A1", "answer": "only the reported case"},
                            {"id": "A2", "answer": "all related cases"},
                        ],
                        "likelihoods": [
                            {"hypothesis_id": "H1", "probs": {"A1": 0.85, "A2": 0.15}},
                            {"hypothesis_id": "H2", "probs": {"A1": 0.2, "A2": 0.8}},
                        ],
                    },
                    {
                        "id": "Q2",
                        "axis_name": "Target location",
                        "question": "Which implementation layer seems most relevant to the failure?",
                        "rationale": "This separates the likely repair location.",
                        "possible_answers": [
                            {"id": "A1", "answer": "method-level code"},
                            {"id": "A2", "answer": "parsing layer"},
                        ],
                        "likelihoods": [
                            {"hypothesis_id": "H1", "probs": {"A1": 0.8, "A2": 0.2}},
                            {"hypothesis_id": "H2", "probs": {"A1": 0.25, "A2": 0.75}},
                        ],
                    },
                ],
            }
            return json.dumps(payload, ensure_ascii=True)

        if "ask the single most important next clarification question" in lowered:
            payload = {
                "question": "Which file is most likely affected?",
                "rationale": "Localises the defect.",
            }
            return json.dumps(payload, ensure_ascii=True)

        if "controlled user proxy" in lowered:
            return json.dumps(
                {
                    "selected_id": "UI1",
                    "reasoning": "mock proxy selects the first remaining useful-info item.",
                },
                ensure_ascii=True,
            )

        if "ordinary issue-reporter clarification" in lowered or "private context" in lowered:
            payload = {
                "items": [
                    "The failure happens when writing an overlong FITS keyword.",
                    "Expected outcome: clearer ValueError on overlong keyword",
                ],
                "explanations": [
                    {
                        "category": "repro_trigger",
                        "source_evidence": "The report describes writing an overlong FITS keyword.",
                        "hidden_issue_gap": "The shortened issue omits the concrete trigger.",
                        "bugfix_usefulness": "This identifies the user-observable trigger condition.",
                        "ordinary_reporter_answerability": "The reporter can describe the input they used.",
                        "abstraction_note": "The item keeps the trigger and abstracts away incidental values.",
                    },
                    {
                        "category": "expected_behavior",
                        "source_evidence": "The report expects a clear ValueError.",
                        "hidden_issue_gap": "The shortened issue omits the expected exception behavior.",
                        "bugfix_usefulness": "This states the expected behavior.",
                        "ordinary_reporter_answerability": "The reporter can state what they expected to happen.",
                        "abstraction_note": "The item keeps the expected behavior as a standalone slot.",
                    },
                ],
                "sufficiency": "The original issue adds the trigger condition and expected behavior.",
            }
            return json.dumps(payload, ensure_ascii=True)

        return "{}"

