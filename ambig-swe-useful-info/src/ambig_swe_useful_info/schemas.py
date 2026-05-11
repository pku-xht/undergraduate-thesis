from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AmbigSWETask:
    task_id: str
    repo: str
    hidden_issue: str               # problem_statement: what BED sees
    full_issue: str                 # original issue, used only for offline useful-info extraction
    useful_info_items: list[str] = field(default_factory=list)
    useful_info_explanations: list[dict[str, Any]] = field(default_factory=list)
    useful_info_sufficiency: str = ""
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
    eig_stances: list[str]


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
    """P(answer | hypothesis_i): the likelihood distribution for one hypothesis."""
    hypothesis_id: str
    distribution: dict[str, float]


@dataclass
class DisagreementAxis:
    """One axis of genuine disagreement among the current hypothesis set."""
    name: str
    description: str
    positions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CandidateEIGDetail:
    """Full EIG decomposition for a single candidate clarification question."""
    question: str
    rationale: str
    eig_stances: list[str]
    per_hypothesis_distributions: list[AnswerDistribution]
    predictive_distribution: dict[str, float]
    predictive_entropy: float
    expected_conditional_entropy: float
    eig: float
    selected: bool
    axis_name: str = ""


@dataclass
class TurnDetail:
    """Complete reasoning and proxy trace for one clarification turn."""
    turn_number: int
    selected_question: str = ""
    question_rationale: str = ""
    simulated_answer: str = ""
    remaining_useful_info_before: list[str] = field(default_factory=list)
    proxy_selected_id: str | None = None
    proxy_reasoning: str = ""
    selected_useful_info: str = ""
    newly_covered: list[str] = field(default_factory=list)
    covered_items_after: list[str] = field(default_factory=list)
    coverage_ratio_after: float = 0.0
    early_stop_reason: str = ""
    hypotheses_before: list[Hypothesis] = field(default_factory=list)
    candidates_ranked: list[CandidateEIGDetail] = field(default_factory=list)
    disagreement_axes: list[DisagreementAxis] = field(default_factory=list)
    planner_parse_warnings: list[str] = field(default_factory=list)
    num_hypotheses_returned: int = 0
    num_candidates_returned: int = 0
    used_fallback: bool = False


@dataclass
class RunResult:
    task_id: str
    runner: str                     # "bed" or "direct"
    dialogue: list[DialogueTurn]
    asked_questions: list[str]
    final_summary: str
    metrics: dict[str, Any]         # per-run: atc, n_idk_responses, stop_reason
    turn_details: list[TurnDetail] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

