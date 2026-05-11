# ClarEval 多轮 30 题实验设计

## 目标

本实验在 `clareval_multi_turn_30_clean.jsonl` 上比较 **Direct** 和 **BED**。

每个方法对每个任务最多使用 **六个 agent 行动轮次**，由 `--max-turns 6` 控制。每一轮开始时，被评估模型先判断是否还需要继续提问。如果不需要，就在这一轮生成最终 Python 代码，并记为已解决。如果直到第六轮仍然选择继续提问、没有在限制内生成最终代码，则记录 `unresolved=true`。

不合法的结构化 LLM 输出不算作实验结果。JSON 解析失败或字段校验失败时会重试一次；重试时会把上一次的校验错误追加到用户提示词末尾，要求模型只返回一个合法 JSON 对象。如果重试后仍失败，该任务直接报错，不会写成 `unresolved`。结构化行动调用会尽量使用接口的 JSON mode。

最终输出为 **Python 代码**。最终评估器对每份生成代码只调用一次 LLM，在同一次判断中查看完整 `ground_truth_missing_premises` 列表和 `original_prompt_source`，然后计算完成率。

| 运行 | 方法 | 被评估模型 | 用户模拟器 | 最终评估器 |
|---|---|---|---|---|
| 1 | Direct | `ds/deepseek-v4-flash` | `ds/deepseek-v4-flash` | `ds/deepseek-v4-pro` |
| 2 | BED | `ds/deepseek-v4-flash` | `ds/deepseek-v4-flash` | `ds/deepseek-v4-pro` |
| 3 | Direct | `ds/deepseek-v4-pro` | `ds/deepseek-v4-flash` | `ds/deepseek-v4-pro` |
| 4 | BED | `ds/deepseek-v4-pro` | `ds/deepseek-v4-flash` | `ds/deepseek-v4-pro` |

## 数据集

保留两个数据文件：

```text
clareval_multi_turn_30_raw.jsonl
clareval_multi_turn_30_clean.jsonl
```

`clareval_multi_turn_30_raw.jsonl` 是原始数据备份；`clareval_multi_turn_30_clean.jsonl` 是本实验实际使用的数据。

清洗后的字段：

- `task_id`：任务编号。
- `fuzzy_type`：模糊类型。
- `difficulty`：难度。
- `instruction`：被评估模型看到的任务需求。
- `ground_truth_missing_premises`：标准缺失前提列表。
- `original_prompt_source`：原始完整需求，只给用户模拟器和最终评估器使用。

已删除字段包括：来源数据集、领域、原始描述、测试用例、模糊注入细节、注入质量、交互指南、标准解、参考多轮对话、维度字段，以及 `key_intent_set`。

清洗时，如果 `key_intent_set` 中有未被标准缺失前提覆盖的信息，则从参考对话中取对应用户回答，追加为新的标准缺失前提。

必要的函数签名信息应放入 `ground_truth_missing_premises`；被评估模型不会收到单独的 `function_signature` 提示。

## 数据统计

当前 30 题子集中，难度和模糊类型完全一一对应，因此报告统一使用 **任务组** 作为统计口径：

| 任务组 | 数量 |
|---|---:|
| Ambiguous Terms / easy | 10 |
| Missing Goal / medium | 10 |
| Missing Premises / hard | 10 |

标准缺失前提数量分布：

| 每题标准缺失前提数 | 任务数 |
|---:|---:|
| 3 | 8 |
| 4 | 18 |
| 5 | 4 |

按任务组统计：

| 任务组 | 最少 | 最多 | 平均 |
|---|---:|---:|---:|
| Ambiguous Terms / easy | 3 | 5 | 3.8 |
| Missing Goal / medium | 3 | 4 | 3.7 |
| Missing Premises / hard | 3 | 5 | 4.1 |

最多为 **5 条标准缺失前提**，对应任务：

- `task4_missing_premises`
- `task6_missing_premises`
- `task6_ambiguous_terms`
- `task7_ambiguous_terms`

## 用户模拟器

用户模拟器可以看到：

- `original_prompt_source`
- 完整的 `ground_truth_missing_premises`
- 当前澄清问题

每次回答只能是以下两类之一：

1. 从 `ground_truth_missing_premises` 中逐字复制一条最接近当前问题的原句；
2. `irrelevant or unknown`。

代码会在保存前再次约束用户模拟器输出，确保结果只属于这两类。

## 方法

### Direct

1. 每个 agent 行动轮次进行一次 Direct 行动调用。
2. 这次调用要么返回 `ask` 和一个澄清问题，要么返回 `answer` 和最终 Python 代码。
3. 用户模拟器回答一条标准缺失前提原句，或回答 `irrelevant or unknown`。
4. 重复以上过程，直到模型选择停止并生成最终代码，或达到六个 agent 行动轮次。
5. 如果六轮内生成最终代码，则记为已解决。
6. 如果第六轮仍然是澄清问题，并且没有在限制内生成最终代码，则记录 `unresolved=true`。
7. 评估生成代码完成了多少标准缺失前提；未解决任务的生成代码为空，完成率为零。

### BED

1. 每个 agent 行动轮次进行一次 BED 行动调用。
2. 如果行动调用返回 `answer`，就把其中的 Python 代码作为最终答案。
3. 如果行动调用返回 `ask`，同一次响应必须包含假设、候选澄清问题、带稳定编号的候选回答，以及每个假设下产生各候选回答编号的概率分布。
4. 代码根据这些概率计算期望信息增益，并选择最高的问题。
5. 用户模拟器回答一条标准缺失前提原句，或回答 `irrelevant or unknown`。
6. 重复以上过程，直到模型选择停止并生成最终代码，或达到六个 agent 行动轮次。
7. 如果六轮内生成最终代码，则记为已解决。
8. 如果第六轮仍然是澄清问题，并且没有在限制内生成最终代码，则记录 `unresolved=true`。
9. 评估生成代码完成了多少标准缺失前提；未解决任务的生成代码为空，完成率为零。

BED 配置：

```text
--num-hypotheses 4
--num-candidates 4
--max-turns 6
```

BED 的内部回答空间由单次 BED 行动调用生成。行动为 `ask` 时，响应中包含假设、候选问题、候选回答编号和文本，以及每个假设产生各候选回答编号的概率。代码根据这些概率计算期望信息增益，并询问排序最高的问题。候选回答只用于内部排序，不会展示给用户模拟器。

## 提示词

本节同时列出系统提示词和实际用户提示词模板。实际运行时以源码中的英文文本为准。

### Direct 行动调用

系统提示词：

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

用户提示词：

```text
Original requirement:
{instruction}

Clarification dialogue so far:
{dialogue_json}
```

### BED 行动调用

系统提示词：

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

用户提示词：

```text
Original requirement:
{instruction}

Clarification dialogue so far:
{dialogue_json}
```

### 用户模拟器

系统提示词：

```text
You simulate a software developer answering a clarification question about their requirements.

You will receive the complete list of ground-truth missing premises. For each clarification question, return exactly one of the following:
1. The single closest ground-truth missing premise copied verbatim.
2. irrelevant or unknown

Do not paraphrase a premise. Do not combine multiple premises. Return only the answer text, with no preamble or explanation.
```

用户提示词：

```text
Original ground-truth requirement:
{original_prompt_source}

Ground-truth missing premises, copy one verbatim if it answers the question:
{numbered_ground_truth_missing_premises}

Clarification question asked:
{question}
```

### 最终代码评估器

系统提示词：

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

用户提示词：

```text
Original full ground-truth prompt:
{original_prompt_source}

Ground-truth missing premises:
{ground_truth_missing_premises_json}

Generated Python code:
{generated_code}

For each ground-truth missing premise, decide whether the generated code satisfies it.
```

## 指标

每个任务记录：

- `completion_rate`：生成代码真正完成的标准缺失前提数量 / 标准缺失前提总数。
- `simulator_answered_count`：用户模拟器返回标准缺失前提原句的次数，不包括 `irrelevant or unknown`。
- `simulator_answer_rate`：`simulator_answered_count / atc`。
- `efficiency_ratio`：代码完成的标准缺失前提数量 / 提问次数。
- `atc`：实际提问次数。
- `unresolved`：在 `max_turns` 个 agent 行动轮次内没有生成最终代码时为真。

报告给出总体指标和按任务组统计的指标。

## 轨迹记录

每条结果会保存完整交互和后续分析需要的结构化决策信息：

- `dialogue`：可见对话，从任务需求开始，之后交替记录 agent 提问和用户模拟器回答。
- `asked_questions`：实际展示给用户模拟器的澄清问题。
- `turn_details`：每个 agent 行动轮次一条记录。
- `evaluation_details`：最终评估器对每条标准缺失前提的一条判断。

Direct 的 `turn_details` 记录：

- `turn_number`
- `action`：`ask` 或 `answer`
- `rationale`
- `question`：当行动为 `ask` 时记录
- `code`：当行动为 `answer` 时记录
- `simulator_raw_answer`：当行动为 `ask` 时记录用户模拟器原始回答
- `simulated_answer`：经过代码约束后的用户模拟器回答

BED 的 `turn_details` 记录同样的行动级字段。对于 `ask` 轮次，还会记录：

- `hypotheses`
- `candidates_ranked`
- `selected_question`
- 每个候选问题的候选回答编号、候选回答文本、各假设下的回答编号概率分布、预测分布、熵项、期望信息增益和是否被选中

`evaluation_details` 记录：

- `premise`
- `covered`
- `reasoning`

## 运行实验

让包可导入：

```powershell
python -m pip install -e .
```

或：

```powershell
$env:PYTHONPATH = "src"
```

设置凭据：

```powershell
$env:OPENAI_BASE_URL = "https://llm.xmcp.ltd/"
$env:OPENAI_API_KEY = "<your-api-key>"
```

创建输出目录：

```powershell
New-Item -ItemType Directory -Force results | Out-Null
```

推荐运行命令：

```powershell
python -m clareval_experiment.cli run --dataset clareval_multi_turn_30_clean.jsonl --output results/direct_flash_results.jsonl --runner direct --backend openai --model ds/deepseek-v4-flash --simulator-model ds/deepseek-v4-flash --evaluator-model ds/deepseek-v4-pro --max-turns 6 --concurrency 1 --summary-interval 5 --progress-file results/direct_flash_progress.json

python -m clareval_experiment.cli run --dataset clareval_multi_turn_30_clean.jsonl --output results/bed_flash_results.jsonl --runner bed --backend openai --model ds/deepseek-v4-flash --simulator-model ds/deepseek-v4-flash --evaluator-model ds/deepseek-v4-pro --num-hypotheses 4 --num-candidates 4 --max-turns 6 --concurrency 1 --summary-interval 5 --progress-file results/bed_flash_progress.json

python -m clareval_experiment.cli run --dataset clareval_multi_turn_30_clean.jsonl --output results/direct_pro_results.jsonl --runner direct --backend openai --model ds/deepseek-v4-pro --simulator-model ds/deepseek-v4-flash --evaluator-model ds/deepseek-v4-pro --max-turns 6 --concurrency 1 --summary-interval 5 --progress-file results/direct_pro_progress.json

python -m clareval_experiment.cli run --dataset clareval_multi_turn_30_clean.jsonl --output results/bed_pro_results.jsonl --runner bed --backend openai --model ds/deepseek-v4-pro --simulator-model ds/deepseek-v4-flash --evaluator-model ds/deepseek-v4-pro --num-hypotheses 4 --num-candidates 4 --max-turns 6 --concurrency 1 --summary-interval 5 --progress-file results/bed_pro_progress.json
```

中断后可用同一命令加 `--resume` 继续。

## 监控进度

控制台会显示完成率、提问次数、用户模拟器有效回答次数、是否未解决、耗时、预计剩余时间，以及按任务组滚动汇总。

进度文件监控示例：

```powershell
while ($true) {
  Clear-Host
  Get-Content results/direct_flash_progress.json -Raw
  Start-Sleep -Seconds 10
}
```

## 评估命令

```powershell
python -m clareval_experiment.cli evaluate --predictions results/direct_flash_results.jsonl --report results/direct_flash_report.txt
python -m clareval_experiment.cli evaluate --predictions results/bed_flash_results.jsonl --report results/bed_flash_report.txt
python -m clareval_experiment.cli evaluate --predictions results/direct_pro_results.jsonl --report results/direct_pro_report.txt
python -m clareval_experiment.cli evaluate --predictions results/bed_pro_results.jsonl --report results/bed_pro_report.txt
```
