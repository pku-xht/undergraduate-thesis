"""Useful extra issue information extraction and deterministic coverage utilities."""

from __future__ import annotations

from ambig_swe_useful_info.bed.utils import safe_json_loads
from ambig_swe_useful_info.llm.base import LLMBackend


EXTRACT_SYSTEM_PROMPT = """\
You are a software requirements analyst designing an ordinary issue-reporter clarification \
benchmark. Given an original GitHub issue and a shortened "problem statement" visible to an \
agent, compare them and extract only the information that appears in the original issue but not \
in the shortened problem statement, where that extra information is both USEFUL for fixing the \
bug or writing a regression test and ANSWERABLE by an ordinary issue reporter.

Hard requirements:

1. PRIVATE VS HIDDEN DIFFERENCE: Only extract information that is present in the private \
context and absent or substantially less specific in the shortened problem statement. Do not \
restate facts that are already clearly available in the shortened statement. A generic summary \
in the shortened statement does NOT cover concrete reproduction code, exact commands, exact \
tracebacks, exact wrong values, exact expected values, or specific environment/version details \
from the original issue.

2. USEFULNESS FOR BUGFIXING: Keep information if it would help a competent developer fix the \
bug, choose the correct scope, identify the exact failing scenario, or write a better regression \
test. The information does NOT need to be strictly necessary. If it is useful, keep it.

3. ORDINARY-REPORTER ANSWERABILITY: Keep only information an ordinary issue reporter could \
reasonably provide in response to a clarification question because it is observable from their \
experience, environment, input, output, traceback, reproduction steps, expected behavior, or \
reported scope. Exclude information that requires maintainer knowledge, benchmark oracle access, \
patch inspection, implementation diagnosis, regression commit knowledge, PR/issue cross-reference \
knowledge, exact internal code location, or the intended fix strategy. Do not extract commit hashes, \
PR numbers, issue numbers, or suggested fix approaches even if they appear in the original issue, \
unless they are necessary to reproduce the user-observed failure.

4. MINIMUM ABSTRACTION: State each item at the LOWEST specificity that preserves the useful \
bug-fixing information, NOT at the exact surface form used by the reporter. Use general software \
examples as guidance:
- If the report uses a concrete sample input value, keep the structural condition but abstract \
  away arbitrary literals that do not affect the bug.
- If the report uses one specific filename, username, timestamp, host, request ID, or local \
  path only as an example of a broader condition, keep the broader condition instead of the \
  incidental literal.
- If the report shows one concrete reproduction script, preserve only the parts that are \
  actually load-bearing for reproducing the failure or writing the regression test.
- If two candidate items would collapse to the same requirement once abstracted, emit only the \
  abstracted requirement.

5. ATOMIC INFORMATION UNITS: Each item should contain exactly one user-answerable information \
slot. Split combined facts when they could be elicited by different clarification questions or \
are useful independently for debugging or regression testing. In particular, separate version \
information, environment information, reproduction trigger, minimal code/API call, actual wrong \
behavior, exact error/traceback, expected behavior, configuration option names/values, and affected \
user-visible scope. Keep tightly coupled facts together only when separating them would make the \
item ambiguous or not useful.

6. OBSERVABLE FACTS OVER IMPLEMENTATION GUESSES: Prefer concrete facts stated or directly \
demonstrated in the private context, such as exact failing inputs, expected behavior, affected \
scope, reproduction conditions, environment details, exact error messages, concrete API calls, \
and testable success criteria. Do not add inferred implementation strategies.

7. SOURCE LIMIT: Use only the original issue as the private context. Do not use developer hints, \
file annotations, patches, tests, or benchmark metadata as sources for extracted items.

Return only valid JSON (no markdown fences). The lengths of `items` and `explanations` MUST \
match. Each explanation object is audit metadata for the item at the same list index; it is \
not used as recoverable information during the clarification experiment.
{
  "items": ["item content 1", "item content 2", ...],
  "explanations": [
    {
      "category": "version | environment | repro_trigger | api_call | actual_behavior | error_traceback | expected_behavior | config | scope | other",
      "source_evidence": "short quote or close paraphrase from the original issue supporting this item",
      "hidden_issue_gap": "what concrete detail is absent or less specific in the shortened problem statement",
      "bugfix_usefulness": "why this item can help fix the bug, choose scope, reproduce failure, or write a regression test",
      "ordinary_reporter_answerability": "why an ordinary issue reporter could answer this from observed behavior or environment",
      "abstraction_note": "why the item is phrased at this abstraction level and whether literals were generalized"
    }
  ],
  "sufficiency": "<one short paragraph summarizing what additional user-answerable useful bug-fixing information the original issue provides beyond the shortened statement>"
}
"""

EXTRACT_USER_TEMPLATE = """\
Original issue:
{full_issue}

Summarized problem statement:
{hidden_issue}
"""


def extract_useful_extra_info_full(
    backend: LLMBackend,
    full_issue: str,
    hidden_issue: str,
    temperature: float = 0.0,
) -> dict:
    """Returns the full structured payload: items + explanations + sufficiency."""
    user = EXTRACT_USER_TEMPLATE.format(
        full_issue=full_issue or "(none)",
        hidden_issue=hidden_issue,
    )
    payload = safe_json_loads(
        backend.complete(EXTRACT_SYSTEM_PROMPT, user, temperature),
        {"items": [], "explanations": [], "sufficiency": ""},
    )
    items = [str(it).strip() for it in payload.get("items", []) if str(it).strip()]
    raw_explanations = payload.get("explanations", [])
    explanations = [
        item if isinstance(item, dict) else {"bugfix_usefulness": str(item).strip()}
        for item in raw_explanations
    ]
    if len(explanations) < len(items):
        explanations += [{} for _ in range(len(items) - len(explanations))]
    elif len(explanations) > len(items):
        explanations = explanations[: len(items)]
    return {
        "items": items,
        "explanations": explanations,
        "sufficiency": str(payload.get("sufficiency", "")).strip(),
    }


def extract_useful_extra_info(
    backend: LLMBackend,
    full_issue: str,
    hidden_issue: str,
    temperature: float = 0.0,
) -> list[str]:
    return extract_useful_extra_info_full(
        backend=backend,
        full_issue=full_issue,
        hidden_issue=hidden_issue,
        temperature=temperature,
    )["items"]


def info_coverage(
    user_responses: str,
    items: list[str],
) -> tuple[list[str], float]:
    if not items or not user_responses.strip():
        return [], 0.0

    response_lines = {line.strip() for line in user_responses.splitlines() if line.strip()}
    matched = [item for item in items if item in response_lines]
    return matched, len(matched) / len(items)


def info_coverage_per_turn(
    dialogue: list[dict],
    items: list[str],
    max_turns: int,
) -> list[dict]:
    """Cumulative per-turn useful-info coverage."""
    n_pairs = max(0, (len(dialogue) - 1) // 2)
    n_pairs = min(n_pairs, max_turns)

    n_items = len(items)
    covered: list[str] = []
    out: list[dict] = []

    for k in range(1, n_pairs + 1):
        user_text = "\n".join(
            t["content"] for t in dialogue[1 : 1 + 2 * k] if t["role"] == "user"
        )
        pending = [it for it in items if it not in covered]
        if not pending or not user_text.strip():
            out.append(
                {
                    "turn": k,
                    "newly_covered": [],
                    "cumulative_covered": list(covered),
                    "cumulative_ratio": (len(covered) / n_items) if n_items else 0.0,
                }
            )
            continue
        matched, _ = info_coverage(user_text, pending)
        for it in matched:
            if it not in covered:
                covered.append(it)
        out.append(
            {
                "turn": k,
                "newly_covered": list(matched),
                "cumulative_covered": list(covered),
                "cumulative_ratio": (len(covered) / n_items) if n_items else 0.0,
            }
        )
    return out

