# ReqElicitGym Three-Method Experiment Design

## Goal

This experiment uses a 10-task subset sampled from the official ReqElicitGym test set and compares three requirements-clarification question-asking methods:

- **Direct**: direct clarification prompting.
- **BED**: rolling-belief Bayesian Experimental Design.
- **Aspect-aware**: clarification that explicitly attends to Interaction, Content, and Style.

The central question is whether explicitly prompting the model to ask across different requirement aspects improves hidden-requirement elicitation rate and question efficiency in a controlled benchmark.

For each task, the maximum number of question turns equals that task's number of hidden implicit requirements. This number is used only by the local runner to stop the episode and set the interviewer's maximum question count. It is not included in `observation()` and never appears in any LLM prompt, so it does not reveal the answer count to the LLM and is not cheating. On each turn, the interviewer generates one question. A single combined LLM evaluator/stakeholder call then judges whether the question directly hits one remaining hidden implicit requirement and returns the simulated user response.

An episode stops when:

1. the method finishes voluntarily;
2. the task-specific question budget is reached.

The experiment does not ask the model to generate final code or a final product specification. The evaluated behavior is whether clarification questions elicit the benchmark's hidden implicit requirements.

Invalid structured interviewer or evaluator/stakeholder outputs are not counted as experiment results. Each structured LLM call must return valid JSON and pass field validation. JSON parsing failures or schema validation failures are retried once. If the retry is still invalid, the task errors directly; the runner does not record it as a normal miss and does not continue with fallback questions or fallback misses.

Open-ended questioning and the ban on answer options or example answers are prompt-level instructions, not hard local post-processing checks. If the model returns structurally valid JSON but the question text semantically violates these wording constraints, the turn is preserved as real model behavior and interpreted as part of the method's performance.

## Runs

The three methods are each run once with `ds/deepseek-v4-flash` and once with `ds/deepseek-v4-pro`. The Evaluator / Stakeholder model is always `ds/deepseek-v4-pro`.

| Run | Method | Interviewer model | Evaluator / Stakeholder model |
|---|---|---|---|
| 1 | Direct | `ds/deepseek-v4-flash` | `ds/deepseek-v4-pro` |
| 2 | BED | `ds/deepseek-v4-flash` | `ds/deepseek-v4-pro` |
| 3 | Aspect-aware | `ds/deepseek-v4-flash` | `ds/deepseek-v4-pro` |
| 4 | Direct | `ds/deepseek-v4-pro` | `ds/deepseek-v4-pro` |
| 5 | BED | `ds/deepseek-v4-pro` | `ds/deepseek-v4-pro` |
| 6 | Aspect-aware | `ds/deepseek-v4-pro` | `ds/deepseek-v4-pro` |

## Dataset

The current experiment data file is:

```text
ReqElicitGym_10.jsonl
```

This file was created from the original full test set by selecting the first task for each `application_type` in source order. The original full dataset has been removed from this experiment folder to avoid accidentally running the wrong task set.

Each JSONL row is one task and contains:

- `name`: task name.
- `application_type`: application category.
- `initial_requirements`: the initial request visible to the interviewer.
- `Implicit Requirements`: hidden benchmark requirements visible only to the evaluator/stakeholder.

Each implicit requirement contains:

- `Aspect`: one of `Interaction`, `Content`, or `Style`.
- `RequirementText`: the hidden requirement text.

## Dataset Statistics

10-task subset:

| Task | Application type | Requirements | Interaction | Content | Style |
|---|---|---:|---:|---:|---:|
| Stock Report Generation System | Dashboards | 5 | 2 | 1 | 2 |
| Texas Hold'em Online Poker Platform | Entertainment App | 5 | 1 | 2 | 2 |
| Credit Repair Lead Generation Website | Showcase Websites | 3 | 1 | 0 | 2 |
| customer service call logging system | Enterprise Management | 10 | 2 | 6 | 2 |
| Online Polling System | Community Platforms | 5 | 1 | 2 | 2 |
| Real Estate Property Search and Listings System | E-commerce Web | 5 | 2 | 1 | 2 |
| Email Composition and Delivery Platform | Productivity Tool | 7 | 3 | 2 | 2 |
| Driver Recruitment and Job Posting System | Job Search Platforms | 11 | 6 | 3 | 2 |
| Global Institute of Information Security Course Enrollment Portal | Learning Platforms | 7 | 3 | 2 | 2 |
| Medical Journal Publishing and Access System | Publishing Platforms | 7 | 3 | 1 | 3 |

Aggregate statistics:

| Item | Value |
|---|---:|
| Tasks | 10 |
| Application types | 10 |
| Hidden implicit requirements | 65 |
| Minimum requirements per task | 3 |
| Maximum requirements per task | 11 |
| Average requirements per task | 6.50 |

Aspect counts:

| Aspect | Hidden requirements |
|---|---:|
| Interaction | 24 |
| Content | 20 |
| Style | 21 |

## Shared Episode Loop

All three methods run in the same LLM-backed episode loop:

1. Load tasks from `ReqElicitGym_10.jsonl`.
2. Use `initial_requirements` as the first user message.
3. The interviewer first decides whether further clarification is needed.
4. If the interviewer returns `finish`, the episode stops and no evaluator/stakeholder call is made.
5. If the interviewer returns `ask`, it must also return one valid clarification question.
6. The combined evaluator/stakeholder LLM call receives the latest question and the remaining hidden implicit requirements.
7. The evaluator decides whether the question directly asks about one remaining hidden requirement.
8. If a valid requirement id is hit, exactly that requirement is marked elicited and the simulated user answer is forced to the original hidden requirement text.
9. If no requirement is hit, the simulated user answer is fixed to:

```text
I do not have a strong preference about that, or it is not important to me.
```

10. The loop repeats until the method finishes or the task-specific question budget is reached.

To reduce evaluator noise, at most one requirement id is accepted per turn. If the LLM returns multiple ids, the code uses only the first valid remaining id and records a trace warning.

## Methods

### Direct

Implementation class: `DirectBaseline`

Direct is a prompting baseline. It does not maintain explicit hypotheses, compute information gain, or explicitly distinguish Interaction / Content / Style.

Per turn:

1. Provide task name, application type, initial requirement, and visible conversation history to the LLM.
2. Ask the LLM to choose either `ask` or `finish`.
3. If it returns `finish`, stop the task.
4. If it returns `ask`, the response must include one targeted clarification question.
5. Send that question to the shared episode loop.
6. Retry once on JSON parsing or field validation failure; error if the retry is still invalid.
7. Local validation checks structured fields only; it does not rule-filter question wording. Wording deviations are preserved as model behavior.

### BED

Implementation class: `BEDInterviewer`

BED maintains a rolling belief state and selects questions using pure local EIG.

The belief state contains:

- `hypotheses`: exactly `num_hypotheses` complete requirement hypotheses and probabilities.
- `hypothesis_disagreements`: unresolved disagreement dimensions among hypotheses.
- `asked_questions`: questions previously selected by BED.
- `update_notes`: short belief-update notes.

Per turn:

1. Call one BED planner LLM.
2. The planner chooses either `ask` or `finish`.
3. If it returns `finish`, stop the task.
4. If it returns `ask`, the planner initializes or updates `belief_state`.
5. The same response returns exactly `num_candidates` candidate questions.
6. Each candidate includes possible answer types and hypothesis-conditioned answer likelihoods.
7. Local code computes expected information gain:

```text
EIG(q)=H[p(h)] - sum_a p(a|q) H[p(h|a,q)]
```

8. Select the candidate with the largest `EIG(q)`.
9. Write the selected question back into the belief state.
10. Send the selected question to the shared episode loop.
11. Retry once on JSON parsing failure, field validation failure, wrong hypothesis/candidate counts, or incomplete likelihoods; error if the retry is still invalid.
12. Local validation checks structured fields and BED EIG scoring fields only; it does not rule-filter question wording. Wording deviations are preserved as model behavior.

BED configuration:

```text
--num-hypotheses 4
--num-candidates 4
```

BED traces include `combined_planner_call: true`. Candidate questions are used only for local ranking; only the question with the highest `EIG(q)` is shown to the simulated user. The local selector uses no heuristic adjustment beyond EIG.

### Aspect-aware

Implementation class: `AspectAwareClarifier`

Aspect-aware clarification explicitly asks the model to consider Interaction, Content, and Style. It does not use BED, EIG, hidden answers, fixed benchmark answer positions, or task-specific blacklist rules. The model chooses the aspect each turn from only visible task and dialogue context.

Aspect definitions:

- **Interaction**: how users operate, input, select, navigate, configure, submit, or trigger actions.
- **Content**: what information, fields, records, views, reports, or details the system should show or collect.
- **Style**: visual or presentation preferences such as layout, color, responsive behavior, or overall look.

Per turn:

1. Provide task name, application type, initial requirement, visible dialogue, already asked questions, and previously selected aspects.
2. Ask the LLM to choose either `ask` or `finish`.
3. If it returns `finish`, stop the task.
4. If it returns `ask`, the LLM must choose one of `Interaction`, `Content`, or `Style`.
5. The LLM generates one targeted clarification question for that aspect.
6. Send the question to the shared episode loop.
7. Retry once on JSON parsing or field validation failure, including invalid aspect or empty question; error if the retry is still invalid.
8. Local validation checks structured fields only; it does not rule-filter question wording. Wording deviations are preserved as model behavior.

## Prompts

This section lists the original English prompt templates implemented in `reqelicitgym_experiment/interviewers.py` and `reqelicitgym_experiment/llm_gym.py`. Expressions inside braces are runtime substitutions.

### Direct Question Call

System prompt:

```text
You are a requirements elicitation interviewer.

Choose exactly one action:
- ask: ask one clarification question if important requirement information is still missing.
- finish: stop asking if the visible dialogue is already sufficient or further clarification is unlikely to help.

Clarification questions must be open-ended. Do not include answer options, multiple-choice choices, suggested answers, examples of possible answers, or "choose one" wording.

Return only valid JSON with no Markdown:
{"action": "ask", "question": "...", "rationale": "..."}
or
{"action": "finish", "rationale": "..."}
```

User prompt template:

```text
Task name: {observation.get('task_name')}
Application type: {observation.get('application_type')}
Initial requirement: {observation.get('initial_requirements')}

Conversation:
{history_to_text(observation.get('conversation_history', []))}
```

### BED Planner Call

System prompt:

```text
You are a BED requirements interviewer.

Choose exactly one action:
- ask: continue clarification if important requirement information is still missing.
- finish: stop asking if the visible dialogue is already sufficient or further clarification is unlikely to help.

For ask, in one JSON response, update the rolling belief state, propose candidate questions, and estimate answer likelihoods needed for EIG scoring. Use only the visible task and conversation information.

Clarification questions must be open-ended. Do not include answer options, multiple-choice choices, suggested answers, examples of possible answers, or "choose one" wording.

Return only valid JSON with no Markdown.

For finish:
{"action": "finish", "rationale": "why no more clarification is needed"}

For ask:
{
  "action": "ask",
  "rationale": "why another clarification question is useful",
  "belief_state": {
    "hypotheses": [
      {
        "id": "H1",
        "probability": 0.20,
        "complete_requirement": "plausible complete requirement"
      }
    ],
    "hypothesis_disagreements": ["unresolved dimension"],
    "asked_questions": [],
    "update_notes": ["brief note"]
  },
  "candidates": [
    {
      "id": "Q1",
      "question": "one focused question",
      "rationale": "what uncertainty this question should reduce",
      "possible_answers": [
        {"id": "A1", "answer": "possible answer type"},
        {"id": "A2", "answer": "another possible answer type"}
      ],
      "likelihoods": [
        {
          "hypothesis_id": "H1",
          "probs": {"A1": 0.6, "A2": 0.4},
          "rationale": "brief"
        }
      ]
    }
  ]
}
```

User prompt template:

```text
Task name: {observation.get('task_name')}
Application type: {observation.get('application_type')}
Initial requirement: {observation.get('initial_requirements')}

Conversation:
{history_to_text(observation.get('conversation_history', []))}

Previous belief state:
{json_like(previous_belief)}

Instructions:
- If this is the first turn, initialize hypotheses and unresolved disagreements.
- If this is a later turn, update the prior belief state using the latest user answer.
- Keep exactly {self.num_hypotheses} diverse hypotheses.
- Hypothesis probabilities must sum to 1 before normalization.
- Preserve prior asked_questions in the belief state.
- Generate exactly {self.num_candidates} focused one-at-a-time candidate questions.
- Candidate questions should distinguish plausible hypotheses.
- For each candidate, define compact possible answer types for that question.
- For each hypothesis, estimate probabilities over that candidate's possible answer types.
```

### Aspect-aware Question Call

System prompt:

```text
You are a requirements elicitation interviewer.

Choose exactly one action:
- ask: ask one clarification question if important requirement information is still missing.
- finish: stop asking if the visible dialogue is already sufficient or further clarification is unlikely to help.

For ask, choose one requirement aspect and ask exactly one concise clarification question. You should pay balanced attention to three requirement aspects:
- Interaction: how users operate, input, select, navigate, configure, submit, or trigger actions.
- Content: what information, fields, records, views, reports, or details the system should show or collect.
- Style: visual or presentation preferences such as layout, color, responsive behavior, or overall look.

Choose the aspect yourself based only on the visible task and conversation.
Clarification questions must be open-ended. Do not include answer options, multiple-choice choices, suggested answers, examples of possible answers, or "choose one" wording.

Return only valid JSON with no Markdown:
{"action": "ask", "selected_aspect": "Interaction", "question": "...", "rationale": "..."}
or
{"action": "finish", "rationale": "..."}
```

User prompt template:

```text
Task name: {observation.get('task_name')}
Application type: {observation.get('application_type')}
Initial requirement: {observation.get('initial_requirements')}

Conversation:
{history_to_text(observation.get('conversation_history', []))}

Already asked questions:
{json_like(self.asked_questions)}

Previously selected aspects:
{json_like(self.selected_aspects)}

Generate the next single clarification question.
```

### Evaluator / Stakeholder Call

System prompt:

```text
You are an expert requirements-elicitation evaluator and simulated stakeholder.

Your task has two parts:
1. Judge whether the interviewer's latest question directly asks about exactly one of the remaining hidden implicit requirements.
2. Return the simulated stakeholder response for the next dialogue turn.

Return JSON only with this format:
{
  "is_relevant_to_implied_requirements": true,
  "relevant_implied_requirements_ids": ["IR1"],
  "reasoning": "brief explanation",
  "response": "the simulated user response"
}

Rules:
- Mark at most one requirement id.
- Mark a requirement only if the latest question directly asks about that remaining hidden implicit requirement.
- If multiple requirements seem relevant, choose the single most directly asked one.
- If no requirement is elicited, set "relevant_implied_requirements_ids" to [].
- If a requirement is elicited, the response must include the exact text of that hidden implicit requirement in natural first-person wording.
- If no requirement is elicited, the response must be exactly: "{self.NO_PREFERENCE_RESPONSE}"
- Do not invent new requirements or preferences.
```

User prompt template:

```text
Initial user requirement:
{self.task.get('initial_requirements', '')}

Conversation so far:
{history_to_text(self.conversation[:-1])}

Interviewer's latest question:
{action}

Remaining hidden implicit requirements:
{remaining_text if remaining_text else 'None'}
```

### Structured Output Retry Suffix

When an interviewer `ask` / `finish` action call or evaluator/stakeholder call fails JSON parsing or field validation on the first attempt, the second call appends the following English text to the system prompt:

```text
Your previous response had invalid JSON or did not match the required schema. Validation error: {last_error}
Return exactly one valid JSON object following the schema. No Markdown.
```

Before saving evaluator/stakeholder results, code constrains the answer again: hits use the original hidden requirement text, and misses use the fixed no-preference answer. The evaluator/stakeholder does not use fallback misses; if the retry still fails to return valid JSON or pass field validation, the task errors directly.

## Metrics

Per task:

- `total_requirements`: number of hidden implicit requirements.
- `total_elicited`: number of successfully elicited hidden requirements.
- `elicitation_ratio`: `total_elicited / total_requirements`.
- `tkqr`: turn-discounted key question rate; earlier hits receive higher weight.
- `ora`: optimal-round alignment, comparing actual rounds with benchmark ideal rounds.
- `num_rounds`: actual question turns.
- `step_budget`: maximum question turns for the task, equal to the task's hidden requirement count. This value is not shown to the LLM.
- `optimal_rounds`: the task's hidden requirement count.
- `aspect_type_elicitation`: elicitation statistics grouped by `Interaction`, `Content`, and `Style`.

Aggregate report:

- `total_elicitation_ratio`: total elicited hidden requirements divided by total hidden requirements.
- `average_elicitation_ratio`: mean task-level `elicitation_ratio`.
- `average_tkqr`.
- `average_ora`.
- `average_rounds`.

## Traces

Each method saves full task results and turn-level traces.

Output structure:

- `overall`: method-level aggregate metrics.
- `task_results`: per-task metrics and turn records.
- `conversations`: audit-friendly dialogue summaries.

Each turn record includes:

- `turn`
- `interviewer`
- `user`
- `action_type`: `clarify`, `probe`, or `finish`
- `elicited_requirement_ids`
- `elicited_requirements`
- `judge` / `evaluator`
- `bed_decision_trace`: the shared field for method decision traces.
- `elicitation_ratio`

## Benchmark Interpretation

ReqElicitGym is best interpreted as a controlled hidden-requirement elicitation benchmark, not as a faithful proxy for real software-engineering requirements clarification.

The key risk is annotation pattern. In the original full test set, most `Style` hidden requirements are color-like preferences. In this 10-task subset, Style requirements also mostly appear as background-color and interface component/element color preferences. A method can therefore improve benchmark scores by explicitly probing Style or color preferences, without necessarily improving general requirements-engineering question asking. To avoid overfitting the benchmark, this experiment does not split Style into finer prompting categories; Style remains at the same level of granularity as Interaction and Content.

This is especially important for interpreting BED. BED aims to reduce uncertainty among plausible complete requirements. In real projects, questions about business goals, user roles, workflow variants, data constraints, integrations, permissions, exceptions, and non-functional requirements can be highly valuable. In ReqElicitGym, those questions can be judged as misses when the hidden target is a concrete color or display-field preference. Poor BED performance on this benchmark should therefore be read as possible benchmark mismatch, not as evidence that EIG-based clarification lacks value.

Aspect-aware should be read as a lightweight and transparent benchmark-facing method. It does not read hidden answers or use hard-coded rules, but it explicitly asks the model to cover Interaction, Content, and Style to test whether aspect-aware questioning improves elicitation rate and efficiency.

## Run

Create a local `.env` file or set environment variables:

```text
OPENAI_BASE_URL="https://llm.xmcp.ltd/"
OPENAI_API_KEY="<your-api-key>"
OPENAI_MODELS="ds/deepseek-v4-flash ds/deepseek-v4-pro"
```

Smoke test:

```powershell
python -B run_experiment.py --methods aspect_aware --models ds/deepseek-v4-flash --max-tasks 1 --judge-model ds/deepseek-v4-pro
```

Main experiment:

```powershell
python -B run_experiment.py --methods direct bed aspect_aware --models ds/deepseek-v4-flash ds/deepseek-v4-pro --max-tasks 10 --num-hypotheses 4 --num-candidates 4 --judge-model ds/deepseek-v4-pro
```

Add `--resume` to continue after interruption.

## Output Files

- `outputs/direct_flash_results.json`
- `outputs/bed_flash_results.json`
- `outputs/aspect_aware_flash_results.json`
- `outputs/direct_pro_results.json`
- `outputs/bed_pro_results.json`
- `outputs/aspect_aware_pro_results.json`
- `outputs/llm_summary.json`
