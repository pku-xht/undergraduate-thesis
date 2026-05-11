# ClarEval Complete Experimental Results and Trace Analysis

> **Current status: all four experiment runs are complete.** `direct_flash`, `bed_flash`, `direct_pro`, and `bed_pro` each contain **30/30** unique task records; no duplicate or missing tasks were found. All conclusions in this document are based on the complete Flash + Pro results.

## 1. Experimental Setup

This experiment compares two clarification strategies on the 30-task ClarEval subset in `clareval_multi_turn_30_clean.jsonl`:

- **Direct**: the evaluated model directly decides whether to ask another clarification question or stop and generate final Python code.
- **BED**: the evaluated model generates 4 requirement hypotheses and 4 candidate clarification questions; the local runner selects the question with the highest expected information gain.

Shared settings:

| Item | Setting |
|---|---|
| Dataset | `clareval_multi_turn_30_clean.jsonl` |
| Number of tasks | 30 |
| Max agent action turns | `max-turns = 6` |
| User simulator | `ds/deepseek-v4-flash` |
| Final evaluator | `ds/deepseek-v4-pro` |
| Flash evaluated model | `ds/deepseek-v4-flash` |
| Pro evaluated model | `ds/deepseek-v4-pro` |
| BED hypotheses | `num-hypotheses = 4` |
| BED candidate questions | `num-candidates = 4` |

Primary sources:

- `results/direct_flash_report.txt`
- `results/bed_flash_report.txt`
- `results/direct_pro_report.txt`
- `results/bed_pro_report.txt`
- `results/direct_flash_results.jsonl`
- `results/bed_flash_results.jsonl`
- `results/direct_pro_results.jsonl`
- `results/bed_pro_results.jsonl`

## 2. Main Results

### 2.1 Overall Results

| Method | n | Completion | Efficiency | ATC | Sim Answer Rate | Unresolved |
|---|---:|---:|---:|---:|---:|---:|
| Direct Flash | 30 | **0.644** | **1.582** | **2.600** | **0.906** | **0.133** |
| BED Flash | 30 | 0.494 | 1.003 | 3.600 | 0.697 | 0.300 |
| Direct Pro | 30 | **0.705** | **1.772** | **2.067** | **0.883** | **0.067** |
| BED Pro | 30 | 0.662 | 1.255 | 2.967 | 0.735 | 0.133 |

The complete results show that Direct remains ahead under both Flash and Pro model strengths. Direct Pro has the highest completion and efficiency and the lowest unresolved rate among the four settings. BED Pro improves substantially over BED Flash, but it still does not surpass Direct Pro.

The stronger model mainly narrows BED's gap against Direct rather than changing the ranking. Under Flash, BED's mean completion difference against Direct is **-0.150**; under Pro, it narrows to **-0.043**. This suggests that Pro's stronger reasoning helps mitigate BED's over-questioning and unresolved failures, but does not remove the information-efficiency loss caused by the current BED candidate-question generation.

### 2.2 Results by Task Group

| Task Group | Method | n | Completion | Efficiency | ATC | Sim Answer Rate | Unresolved |
|---|---|---:|---:|---:|---:|---:|---:|
| Ambiguous Terms / easy | Direct Flash | 10 | **0.652** | **1.383** | **2.800** | **0.850** | **0.100** |
| Ambiguous Terms / easy | BED Flash | 10 | 0.285 | 0.467 | 4.800 | 0.592 | 0.600 |
| Ambiguous Terms / easy | Direct Pro | 10 | **0.735** | **1.600** | **2.400** | **0.850** | **0.100** |
| Ambiguous Terms / easy | BED Pro | 10 | 0.572 | 0.873 | 3.800 | 0.697 | 0.300 |
| Missing Goal / medium | Direct Flash | 10 | **0.533** | **1.133** | **2.700** | **0.883** | 0.200 |
| Missing Goal / medium | BED Flash | 10 | 0.425 | 0.583 | 3.500 | 0.717 | 0.200 |
| Missing Goal / medium | Direct Pro | 10 | **0.658** | **1.650** | **1.700** | **0.950** | **0.000** |
| Missing Goal / medium | BED Pro | 10 | **0.658** | 1.067 | 2.700 | 0.733 | 0.100 |
| Missing Premises / hard | Direct Flash | 10 | 0.747 | **2.230** | **2.300** | **0.983** | 0.100 |
| Missing Premises / hard | BED Flash | 10 | **0.772** | 1.958 | 2.500 | 0.783 | 0.100 |
| Missing Premises / hard | Direct Pro | 10 | 0.722 | **2.067** | **2.100** | **0.850** | 0.100 |
| Missing Premises / hard | BED Pro | 10 | **0.755** | 1.825 | 2.400 | 0.775 | **0.000** |

BED's main weakness still comes from **Ambiguous Terms / easy**. Under Flash, BED reaches only **0.285** completion, far below Direct's **0.652**, and its unresolved rate reaches **0.600**. Under Pro, BED improves to **0.572**, but Direct Pro also improves to **0.735**, so the gap remains clear.

The only task group where BED is consistently ahead is **Missing Premises / hard**. Under Flash, BED completion is **0.772**, slightly above Direct's **0.747**; under Pro, BED reaches **0.755**, also slightly above Direct's **0.722**. However, Direct has higher efficiency under both model strengths, meaning BED's gains come from more interaction and higher cost rather than better information efficiency.

### 2.3 Pairwise Task Results

Using the per-task completion difference `BED - Direct`:

| Model Strength | BED Better Than Direct | Tied | BED Worse Than Direct | Mean Difference |
|---|---:|---:|---:|---:|
| Flash | 5 | 15 | 10 | -0.150 |
| Pro | 8 | 14 | 8 | -0.043 |

The Flash results show that BED loses more often than it wins, with a sizable average gap. The Pro results are much closer: BED wins and loses 8 tasks each, and the average gap shrinks to **-0.043**. This means BED is not useless; with a stronger model, it has more opportunities to turn its structured hypothesis space into executable code. Still, Direct remains the more stable baseline because it achieves higher overall completion and efficiency with fewer turns.

## 3. Deep Trace Analysis

### 3.1 BED Asks More but Has a Lower Useful-Information Rate

| Method | Total Questions | Valid Simulator Answers | `irrelevant or unknown` | Unknown Rate |
|---|---:|---:|---:|---:|
| Direct Flash | 78 | 66 | 12 | 0.154 |
| BED Flash | 108 | 65 | 43 | 0.398 |
| Direct Pro | 62 | 49 | 13 | 0.210 |
| BED Pro | 89 | 55 | 34 | 0.382 |

Under Flash, BED asks **30** more questions than Direct but receives **1** fewer valid answer. Under Pro, BED asks **27** more questions and receives **6** more valid answers, but also receives **21** more unknown answers. In other words, Pro makes BED's extra questions more likely to produce information, but much of the extra interaction still lands on questions that the simulator cannot answer with a gold premise.

This explains the central pattern in the main table: BED has higher ATC, but its completion and efficiency do not rise accordingly. The current BED bottleneck is not mainly the local EIG calculation itself; it is the candidate-question distribution, which often favors questions that are internally discriminative but hard to map to answerable gold premises.

### 3.2 Question Form: BED Is More Closed and Edge-Case-Oriented

| Method or Candidate Pool | Open WH Questions | Yes/No or Closed Questions | Other |
|---|---:|---:|---:|
| Direct Flash actual questions | **62.8%** | 26.9% | 10.3% |
| BED Flash actual questions | 38.0% | **57.4%** | 4.6% |
| All BED Flash candidate questions | 36.1% | **60.0%** | 3.9% |
| Direct Pro actual questions | **58.1%** | 37.1% | 4.8% |
| BED Pro actual questions | 41.6% | **51.7%** | 6.7% |
| All BED Pro candidate questions | 34.8% | **55.3%** | 9.8% |

Direct more often asks open-ended questions about input type, output form, overall transformation logic, and constraints. These questions are better aligned with the user simulator, which can only copy one closest `ground_truth_missing_premises` item or return `irrelevant or unknown`.

BED's candidate pool and final selections are more biased toward closed, yes/no, or edge-case questions, such as whether to handle a certain invalid input, how to interpret a symbol, or whether there is a threshold or special case. These questions may be useful in real requirement interviews, but under this simulator constraint, they receive a valid answer only when they map almost directly to a gold premise.

### 3.3 Late-Turn Questioning Remains Risky

| BED Question Position | Flash Unknown / Total | Flash Unknown Rate | Pro Unknown / Total | Pro Unknown Rate |
|---:|---:|---:|---:|---:|
| 1 | 6 / 30 | 0.200 | 11 / 30 | 0.367 |
| 2 | 5 / 25 | 0.200 | 7 / 26 | 0.269 |
| 3 | 11 / 21 | 0.524 | 6 / 13 | 0.462 |
| 4 | 6 / 14 | 0.429 | 5 / 9 | 0.556 |
| 5 | 8 / 9 | **0.889** | 3 / 7 | **0.429** |
| 6 | 7 / 9 | **0.778** | 2 / 4 | **0.500** |

BED Flash is almost in a repeated-unanswerable-detail state by its fifth and sixth questions, where unknown rates reach **0.889** and **0.778**. With `max-turns = 6`, this is especially damaging: if the sixth turn is still a question, the task is marked unresolved, generated code is empty, and completion is 0.

BED Pro has far fewer late-turn samples, which means Pro more often stops earlier and generates code. However, once it reaches questions 4 to 6, the unknown rate remains high. Model strength therefore mitigates over-questioning, but does not eliminate BED's tendency to spend later turns on closed or edge-case questions.

### 3.4 Representative Cases

#### `task4_ambiguous_terms`

Under Flash, Direct recovered the core information through three open-ended questions: the return condition, the initial balance, and the integer-list deposit/withdrawal input format. Its completion was **1.0**. BED Flash also obtained key semantics in the first two questions, but then shifted to asking how integer signs should be interpreted and how positive and negative numbers correspond to deposits and withdrawals. The simulator could only repeat the input premise or return unknown; BED was still asking on the sixth turn, so it ended unresolved with completion **0.0**.

Under Pro, this failure mode is clearly mitigated. Direct Pro generated code after two questions, and BED Pro also stopped after two questions; both reached **1.0** completion. This shows that Pro can better turn incomplete but sufficient answers into an implementation instead of continuing to spend turns on symbol-boundary details.

#### `task5_ambiguous_terms`

After receiving "the input is a list of floats" and the Mean Absolute Deviation formula, BED Flash kept asking whether there is a threshold, whether the function should make a conditional decision based on MAD, and whether the threshold is passed as an argument. None of these are gold premises, so the simulator repeatedly returned unknown; BED was still not generating code by the sixth turn, with completion **0.0**.

BED Pro still shows similar early drift: it first asks about empty strings, branching logic, fixed thresholds, and whether the return value is boolean. But after obtaining the return type and input type in questions 4 and 5, Pro generates code and reaches **1.0** completion. This demonstrates Pro's tolerance for BED's noisy question selection: even when candidate quality is unstable, the model can sometimes converge once enough partial information is available.

#### `task9_ambiguous_terms`

Direct Flash and Direct Pro both receive "return a tuple consisting of the sum and product of all integers in the list" on the first question and then generate code; both reach **1.0** completion. BED Flash obtains the tuple output in question 1 and that the sum of an empty list should be 0 in question 2, but then asks about non-integer elements, string inputs, and whether all elements are guaranteed to be integers. These are non-gold edge cases, so the task ends unresolved with completion **0.0**.

BED Pro still asks about non-integers, strings, and booleans, but after question 5 obtains that the product of an empty list should be 1 and then generates code, reaching **1.0** completion. Again, Pro reduces the "ask until failure" pattern, but BED's question path remains more circuitous and turn-expensive than Direct's.

#### `task7_ambiguous_terms`

This is a representative BED Pro failure. Direct Pro uses four open-ended questions to recover the task purpose, output meaning, input format, and example, reaching **0.8** completion. BED Pro first asks whether the function should modify the input, then obtains the output type and input format, but shifts to unbalanced-parentheses handling and other non-gold details. It is still asking on the sixth turn, ends unresolved, and has completion **0.0**.

This case shows that even with Pro, BED can reproduce the core Flash failure mechanism when late-turn budget is spent on boundary conditions that the evaluator does not reward and the simulator cannot answer.

#### `task10_missing_premises`

BED Flash clearly outperforms Direct Flash on this task. Direct Flash repeatedly asks about the rolling maximum window size and boundary behavior, is still asking on the sixth turn, and has completion **0.0**. BED Flash obtains that the input is a list of integers and the output is a rolling maximum list in two questions, then generates code and reaches **0.75** completion.

Under Pro, however, Direct Pro also solves the task after two questions with **1.0** completion, and BED Pro also reaches **1.0**. This suggests BED's advantage is most visible with weaker models or "reconstruct from almost nothing" tasks; when Direct is strong enough, open-ended clarification can also quickly produce an implementable answer.

### 3.5 Common Failed Premise Types

| Failed Premise Type | Direct Flash | BED Flash | Direct Pro | BED Pro |
|---|---:|---:|---:|---:|
| Function naming | 15 | 15 | 11 | 13 |
| Input / parameters | 20 | 33 | 19 | 20 |
| Return / output | 1 | 2 | 1 | 2 |
| Docstring / examples | 4 | 4 | 3 | 4 |
| Other behavior / constraints | 0 | 1 | 0 | 1 |

Function naming and docstring/examples are stable shared blind spots. Both methods usually prioritize behavior, inputs, and outputs, and rarely ask what the function should be called or whether example documentation is required; even runnable code can lose credit when these interface-surface requirements are wrong.

BED misses input/parameter premises more often than Direct, especially under Flash. This matches the high unknown rate in the Trace analysis: BED spends more turns on thresholds, exception types, non-integer elements, unbalanced parentheses, and other boundary questions, while failing to reliably fill in basic interface information.

## 4. Conclusion

Under the current ClarEval 30-task subset, current prompts, Flash simulator, Pro evaluator, and `max-turns = 6`, **Direct is the stronger, more stable, and more efficient baseline**. It achieves higher overall completion, higher efficiency, lower ATC, and lower unresolved rates under both Flash and Pro model strengths.

BED's structured hypotheses and EIG selection are not valueless. It consistently obtains slightly higher completion on Missing Premises / hard, and the Pro model substantially narrows BED's overall gap against Direct. However, BED's candidate-question distribution remains biased toward closed and edge-case questions, so it often asks questions that the simulator cannot answer with a gold premise, reducing efficiency and increasing unresolved risk.

Therefore, the conclusion should remain scoped: **on this 30-task ClarEval subset and with the current BED prompt/candidate-generation mechanism, BED does not outperform Direct; this should not be generalized into a claim that BED-style clarification is ineffective for all tasks.** A more promising next step is to improve BED candidate-question generation so that it prioritizes basic interfaces and core semantics before boundary conditions.

## 5. Threats to Validity

- The dataset contains only 30 tasks, with 10 tasks per group; the results explain the current experiment and should not be over-generalized.
- The user simulator can only copy one gold premise or return `irrelevant or unknown`, which improves control but penalizes boundary questions that may be valuable in real conversations.
- The final evaluation is performed by `ds/deepseek-v4-pro` in a single judgment of whether the generated code covers each premise, so LLM judge bias may still affect results.
- BED's behavior is tightly coupled to the current prompt format that asks for 4 candidate questions and answer-ID likelihoods. Improving candidate-question generation could change the conclusion.
