from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PremiseItem:
    description: str


@dataclass
class ClarEvalTask:
    task_id: str
    fuzzy_type: str
    difficulty: str
    instruction: str
    missing_premises: list[PremiseItem]
    original_prompt_source: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Hypothesis:
    hid: str
    summary: str
    prior: float
    evidence: list[str] = field(default_factory=list)


@dataclass
class CandidateQuestion:
    question: str
    rationale: str
    # Stable answer IDs used as the EIG response space, e.g. A1/A2.
    candidate_answers: list[str] = field(default_factory=list)
    # Human-readable text for each answer ID. These labels are trace-only; EIG
    # distributions use the stable IDs above.
    candidate_answer_texts: dict[str, str] = field(default_factory=dict)


@dataclass
class RankedQuestion:
    question: CandidateQuestion
    predictive_entropy: float
    expected_conditional_entropy: float
    eig: float


@dataclass
class DialogueTurn:
    turn_index: int
    role: str
    content: str


@dataclass
class AnswerDistribution:
    """P(candidate_answer | hypothesis_i) for one hypothesis."""
    hypothesis_id: str
    distribution: dict[str, float]


@dataclass
class CandidateEIGDetail:
    """Full EIG decomposition for a single candidate clarification question."""
    question: str
    rationale: str
    # Hypothesis-conditioned candidate answers used as the EIG response space.
    candidate_answers: list[str]
    candidate_answer_texts: dict[str, str]
    # P(Y | H_i) for each hypothesis
    per_hypothesis_answer_distributions: list[AnswerDistribution]
    # P(Y) = sum_i P(H_i) * P(Y|H_i)
    predictive_distribution: dict[str, float]
    # H(Y) = H(P(Y))
    predictive_entropy: float
    # E_H[H(Y|H)] = sum_i P(H_i) * H(P(Y|H_i))
    expected_conditional_entropy: float
    # EIG = H(Y) - E_H[H(Y|H)]
    eig: float
    # True when this candidate was actually selected and asked
    selected: bool


@dataclass
class TurnDetail:
    """Complete trace for one agent action turn."""
    turn_number: int
    action: str
    rationale: str = ""
    question: str = ""
    code: str = ""
    simulator_raw_answer: str = ""
    simulated_answer: str = ""
    hypotheses: list[Hypothesis] = field(default_factory=list)
    candidates_ranked: list[CandidateEIGDetail] = field(default_factory=list)
    selected_question: str = ""


@dataclass
class EvaluationDetail:
    """Final evaluator judgment for one ground-truth missing premise."""
    premise: str
    covered: bool
    reasoning: str = ""


@dataclass
class RunResult:
    task_id: str
    scenario: str
    fuzzy_type: str
    difficulty: str
    task_group: str
    dialogue: list[DialogueTurn]
    asked_questions: list[str]
    generated_code: str
    unresolved: bool
    matched_premises: list[str]
    evaluation_details: list[EvaluationDetail]
    metrics: dict[str, Any]
    # Per-turn action trace. BED turns additionally include hypotheses and EIG values.
    turn_details: list[TurnDetail] = field(default_factory=list)
