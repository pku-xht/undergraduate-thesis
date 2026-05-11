# ClarEval Multi-Turn 30 Experiment Design

## Goal

This experiment compares **Direct** and **BED** on `clareval_multi_turn_30_clean.jsonl`.

Each method may use up to **six agent action turns** (`--max-turns 6`). At the start of every turn, the evaluated model decides whether another clarification question is still needed. If not, it generates the final Python code and the task is `resolved`. If it continues to ask clarification questions through the sixth turn and therefore never emits final code within the limit, the task is `unresolved=true`.

Invalid structured LLM output is not treated as an experimental outcome. JSON parsing or schema validation failures are retried once. The retry appends the previous validation error to the user prompt and asks for exactly one valid JSON object. If the retry still fails, the task raises an error and is not written as `unresolved`. Structured action calls use API JSON mode when available.

The final output is **Python code**. The final evaluator checks the generated code against the complete `ground_truth_missing_premises` list and `original_prompt_source` in one LLM call per generated code sample.

| Run | Method | Agent Model | User Simulator | Final Evaluator |
|---|---|---|---|---|
| 1 | Direct | `ds/deepseek-v4-flash` | `ds/deepseek-v4-flash` | `ds/deepseek-v4-pro` |
| 2 | BED | `ds/deepseek-v4-flash` | `ds/deepseek-v4-flash` | `ds/deepseek-v4-pro` |
| 3 | Direct | `ds/deepseek-v4-pro` | `ds/deepseek-v4-flash` | `ds/deepseek-v4-pro` |
| 4 | BED | `ds/deepseek-v4-pro` | `ds/deepseek-v4-flash` | `ds/deepseek-v4-pro` |

## Dataset

Files:

```text
clareval_multi_turn_30_raw.jsonl
clareval_multi_turn_30_clean.jsonl
```

`clareval_multi_turn_30_raw.jsonl` preserves the original records. `clareval_multi_turn_30_clean.jsonl` is the actual experiment input.

Cleaned fields:

- `task_id`
- `fuzzy_type`
- `difficulty`
- `instruction`
- `ground_truth_missing_premises`
- `original_prompt_source`

Removed fields include source dataset, domain, original description, test cases, ambiguity injection metadata, interaction guidelines, ground-truth solution, reference dialogue, dimensions, and `key_intent_set`.

During cleaning, if a `key_intent_set` item contained information not represented by `ground_truth_missing_premises`, the corresponding reference user answer was appended as an additional missing premise.

Required signature information belongs in `ground_truth_missing_premises`; the evaluated model receives no separate `function_signature` hint.

## Dataset Statistics

The current 30-task subset has a one-to-one mapping between ambiguity type and difficulty, so reports use a single **task group** statistic:

| Task Group | Count |
|---|---:|
| Ambiguous Terms / easy | 10 |
| Missing Goal / medium | 10 |
| Missing Premises / hard | 10 |

Premise count distribution:

| Number of `ground_truth_missing_premises` | Tasks |
|---:|---:|
| 3 | 8 |
| 4 | 18 |
| 5 | 4 |

By task group:

| Task Group | Min | Max | Average |
|---|---:|---:|---:|
| Ambiguous Terms / easy | 3 | 5 | 3.8 |
| Missing Goal / medium | 3 | 4 | 3.7 |
| Missing Premises / hard | 3 | 5 | 4.1 |

The maximum is **5 premises**, appearing in:

- `task4_missing_premises`
- `task6_missing_premises`
- `task6_ambiguous_terms`
- `task7_ambiguous_terms`

## User Simulator

The simulator sees `original_prompt_source`, the full `ground_truth_missing_premises` list, and the current clarification question.

For every question, it must return exactly one of:

1. the single closest `ground_truth_missing_premises` sentence copied verbatim;
2. `irrelevant or unknown`.

The code also constrains simulator output back into this allowed set before storing it.

## Methods

### Direct

1. At each agent action turn, make one Direct action call.
2. The action call returns either `ask` with one clarification question, or `answer` with final Python code.
3. Simulate the user answer.
4. Repeat until the model chooses to stop and generate final code, or reaches six agent action turns.
5. If final code is generated within six turns, mark the task as resolved.
6. If the sixth turn is still a clarification question and no final code is generated within the limit, mark `unresolved=true`.
7. Evaluate the generated code; unresolved tasks have empty generated code and zero completion.

### BED

1. At each agent action turn, make one BED action call.
2. If the action call returns `answer`, use its Python code as the final answer.
3. If the action call returns `ask`, the same response must include hypotheses, candidate clarification questions, stable candidate-answer IDs, candidate-answer text, and per-hypothesis distributions over those answer IDs.
4. Rank candidate questions by expected information gain using the returned probabilities, then ask the highest-ranked candidate.
5. Simulate the user answer.
6. Repeat until the model chooses to stop and generate final code, or six agent action turns are reached.
7. If final code is generated within six turns, mark the task as resolved.
8. If the sixth turn is still a clarification question and no final code is generated within the limit, mark `unresolved=true`.
9. Evaluate the generated code; unresolved tasks have empty generated code and zero completion.

BED configuration:

```text
--num-hypotheses 4
--num-candidates 4
--max-turns 6
```

BED's internal response space is generated inside the single BED action call. When the action is `ask`, the response includes hypotheses, candidate questions, candidate-answer IDs and text, and the probability that each hypothesis would produce each candidate-answer ID. The local runner computes EIG from those probabilities and asks the highest-ranked candidate. Candidate answers are only used for internal ranking; they are never shown to the user simulator.

## Prompts

### Direct Agent Action

System prompt:

```text
You are a requirements engineer and Python programmer.

Choose exactly one action:
- ask: ask one clarification question if important implementation-relevant information is still missing.
- answer: write the final Python code if the dialogue is sufficient to implement the function.

Clarification questions must be open-ended. Do not include answer options, multiple-choice choices, suggested answers, examples of possible answers, or "choose one" wording.

Return only valid JSON (no markdown fences):
{"action": "ask", "question": "...", "rationale": "..."}
or
{"action": "answer", "code": "...", "rationale": "..."}
```

User prompt:

```text
Original requirement:
{instruction}

Clarification dialogue so far:
{dialogue_json}
```

### BED Agent Action

System prompt:

```text
You are a requirements engineer and Python programmer.

Choose exactly one action:
- ask: ask one clarification question if important implementation-relevant information is still missing.
- answer: write the final Python code if the dialogue is sufficient to implement the function.

Clarification questions must be open-ended. Do not include answer options, multiple-choice choices, suggested answers, examples of possible answers, or "choose one" wording.

For ask, generate exactly 4 distinct plausible hypotheses and exactly 4 candidate clarification questions based on disagreements among those hypotheses. For each candidate question, generate compact possible answer types with stable IDs such as A1 and A2. Then estimate the probability that each hypothesis would produce each answer ID. The local runner will compute expected information gain from these probabilities and choose the exact question.

Return only valid JSON (no markdown fences):
{"action": "ask", "rationale": "...", "hypotheses": [{"id": "H1", "probability": 0.25, "complete_requirement": "..."}, {"id": "H2", "probability": 0.25, "complete_requirement": "..."}, {"id": "H3", "probability": 0.25, "complete_requirement": "..."}, {"id": "H4", "probability": 0.25, "complete_requirement": "..."}], "candidate_questions": [{"id": "Q1", "question": "...", "rationale": "...", "possible_answers": [{"id": "A1", "answer": "..."}, {"id": "A2", "answer": "..."}], "likelihoods": [{"hypothesis_id": "H1", "probs": {"A1": 0.6, "A2": 0.4}}, {"hypothesis_id": "H2", "probs": {"A1": 0.5, "A2": 0.5}}, {"hypothesis_id": "H3", "probs": {"A1": 0.4, "A2": 0.6}}, {"hypothesis_id": "H4", "probs": {"A1": 0.3, "A2": 0.7}}]}, {"id": "Q2", "question": "...", "rationale": "...", "possible_answers": [{"id": "A1", "answer": "..."}, {"id": "A2", "answer": "..."}], "likelihoods": [{"hypothesis_id": "H1", "probs": {"A1": 0.6, "A2": 0.4}}, {"hypothesis_id": "H2", "probs": {"A1": 0.5, "A2": 0.5}}, {"hypothesis_id": "H3", "probs": {"A1": 0.4, "A2": 0.6}}, {"hypothesis_id": "H4", "probs": {"A1": 0.3, "A2": 0.7}}]}, {"id": "Q3", "question": "...", "rationale": "...", "possible_answers": [{"id": "A1", "answer": "..."}, {"id": "A2", "answer": "..."}], "likelihoods": [{"hypothesis_id": "H1", "probs": {"A1": 0.6, "A2": 0.4}}, {"hypothesis_id": "H2", "probs": {"A1": 0.5, "A2": 0.5}}, {"hypothesis_id": "H3", "probs": {"A1": 0.4, "A2": 0.6}}, {"hypothesis_id": "H4", "probs": {"A1": 0.3, "A2": 0.7}}]}, {"id": "Q4", "question": "...", "rationale": "...", "possible_answers": [{"id": "A1", "answer": "..."}, {"id": "A2", "answer": "..."}], "likelihoods": [{"hypothesis_id": "H1", "probs": {"A1": 0.6, "A2": 0.4}}, {"hypothesis_id": "H2", "probs": {"A1": 0.5, "A2": 0.5}}, {"hypothesis_id": "H3", "probs": {"A1": 0.4, "A2": 0.6}}, {"hypothesis_id": "H4", "probs": {"A1": 0.3, "A2": 0.7}}]}]}
or
{"action": "answer", "code": "...", "rationale": "..."}
```

User prompt:

```text
Original requirement:
{instruction}

Clarification dialogue so far:
{dialogue_json}
```

### User Simulator

System prompt:

```text
You simulate a software developer answering a clarification question about their requirements.

You will receive the complete list of ground-truth missing premises. For each clarification question, return exactly one of the following:
1. The single closest ground-truth missing premise copied verbatim.
2. irrelevant or unknown

Do not paraphrase a premise. Do not combine multiple premises. Return only the answer text, with no preamble or explanation.
```

User prompt:

```text
Original ground-truth requirement:
{original_prompt_source}

Ground-truth missing premises, copy one verbatim if it answers the question:
{numbered_ground_truth_missing_premises}

Clarification question asked:
{question}
```

### Final Code Evaluator

System prompt:

```text
You are an expert Python code reviewer evaluating whether generated code satisfies a complete set of ground-truth requirement premises.

You will receive:
- the original full ground-truth prompt;
- the complete list of ground-truth missing premises;
- the generated Python code.

For each premise, mark covered only if the generated code itself implements or clearly satisfies that premise. Docstrings and examples may count only when the premise is specifically about documentation or examples. Do not give credit merely because the original prompt contains the premise. Include every premise exactly once, copied verbatim.

Return only valid JSON (no markdown fences):
{"premise_results": [{"premise": "...", "covered": true or false, "reasoning": "one concise sentence"}]}
```

User prompt:

```text
Original full ground-truth prompt:
{original_prompt_source}

Ground-truth missing premises:
{ground_truth_missing_premises_json}

Generated Python code:
{generated_code}

For each ground-truth missing premise, decide whether the generated code satisfies it.
```

## Metrics

Each completed task records:

- `completion_rate`: matched premises in generated code divided by total `ground_truth_missing_premises`.
- `simulator_answered_count`: number of simulator answers that were copied premises, excluding `irrelevant or unknown`.
- `simulator_answer_rate`: `simulator_answered_count / atc`.
- `efficiency_ratio`: matched code premises divided by asked questions.
- `atc`: actual number of clarification questions asked.
- `unresolved`: true if no final code is generated within `max_turns` agent action turns.

Reports include overall metrics and metrics by task group.

## Trace Records

Every result row stores the full interaction and the structured decisions needed for later analysis:

- `dialogue`: the visible conversation, starting with the task instruction and then alternating agent questions and simulator answers.
- `asked_questions`: the clarification questions actually shown to the simulator.
- `turn_details`: one record per agent action turn.
- `evaluation_details`: one final evaluator judgment per ground-truth missing premise.

Direct `turn_details` records:

- `turn_number`
- `action`: `ask` or `answer`
- `rationale`
- `question`, when the action is `ask`
- `code`, when the action is `answer`
- `simulator_raw_answer`, when the action is `ask`
- `simulated_answer`, after constraining the simulator output to the allowed answer set

BED `turn_details` records the same action-level fields. For `ask` turns, it also records:

- `hypotheses`
- `candidates_ranked`
- `selected_question`
- each candidate question's candidate-answer IDs, candidate-answer text, per-hypothesis distributions over answer IDs, predictive distribution, entropy terms, EIG, and selected flag

`evaluation_details` records:

- `premise`
- `covered`
- `reasoning`

## Running The Experiment

Make the package importable:

```powershell
python -m pip install -e .
```

or:

```powershell
$env:PYTHONPATH = "src"
```

Set credentials:

```powershell
$env:OPENAI_BASE_URL = "https://llm.xmcp.ltd/"
$env:OPENAI_API_KEY = "<your-api-key>"
```

Create output directory:

```powershell
New-Item -ItemType Directory -Force results | Out-Null
```

Recommended runs:

```powershell
python -m clareval_experiment.cli run --dataset clareval_multi_turn_30_clean.jsonl --output results/direct_flash_results.jsonl --runner direct --backend openai --model ds/deepseek-v4-flash --simulator-model ds/deepseek-v4-flash --evaluator-model ds/deepseek-v4-pro --max-turns 6 --concurrency 1 --summary-interval 5 --progress-file results/direct_flash_progress.json

python -m clareval_experiment.cli run --dataset clareval_multi_turn_30_clean.jsonl --output results/bed_flash_results.jsonl --runner bed --backend openai --model ds/deepseek-v4-flash --simulator-model ds/deepseek-v4-flash --evaluator-model ds/deepseek-v4-pro --num-hypotheses 4 --num-candidates 4 --max-turns 6 --concurrency 1 --summary-interval 5 --progress-file results/bed_flash_progress.json

python -m clareval_experiment.cli run --dataset clareval_multi_turn_30_clean.jsonl --output results/direct_pro_results.jsonl --runner direct --backend openai --model ds/deepseek-v4-pro --simulator-model ds/deepseek-v4-flash --evaluator-model ds/deepseek-v4-pro --max-turns 6 --concurrency 1 --summary-interval 5 --progress-file results/direct_pro_progress.json

python -m clareval_experiment.cli run --dataset clareval_multi_turn_30_clean.jsonl --output results/bed_pro_results.jsonl --runner bed --backend openai --model ds/deepseek-v4-pro --simulator-model ds/deepseek-v4-flash --evaluator-model ds/deepseek-v4-pro --num-hypotheses 4 --num-candidates 4 --max-turns 6 --concurrency 1 --summary-interval 5 --progress-file results/bed_pro_progress.json
```

Use `--resume` with the same command to continue an interrupted run.

## Monitoring Progress

Console output includes completion rate, asked questions, simulator answered count, unresolved status, elapsed time, ETA, and rolling task-group summaries.

Progress file monitoring example:

```powershell
while ($true) {
  Clear-Host
  Get-Content results/direct_flash_progress.json -Raw
  Start-Sleep -Seconds 10
}
```

## Evaluation Commands

```powershell
python -m clareval_experiment.cli evaluate --predictions results/direct_flash_results.jsonl --report results/direct_flash_report.txt
python -m clareval_experiment.cli evaluate --predictions results/bed_flash_results.jsonl --report results/bed_flash_report.txt
python -m clareval_experiment.cli evaluate --predictions results/direct_pro_results.jsonl --report results/direct_pro_report.txt
python -m clareval_experiment.cli evaluate --predictions results/bed_pro_results.jsonl --report results/bed_pro_report.txt
```
