# Ambig-SWE Useful-Information 10 个任务实验设计

## 目标

本实验只使用当前 Ambig-SWE pilot 数据中的前 10 个 task，比较 **Direct** 与 **BED** 两种澄清策略。

核心问题是：当 agent 初始只能看到压缩后的 Ambig-SWE issue 时，BED 风格的自适应澄清是否比直接让 LLM 追问更高效地恢复普通 issue reporter 可回答的、有用的额外 issue 信息？

本实验只评价澄清问答行为，不运行下游代码修复 agent，也不评价补丁是否通过测试。最终指标来自 proxy 回答中恢复出的、普通 issue reporter 可回答的 useful extra issue information。

每种方法对每个数据行最多使用 **5 个澄清轮次**，由 `--max-turns 5` 控制。如果在 5 轮内已经覆盖该行的全部 useful-info 项，则提前停止。

默认配置：

```text
max_turns = 5
num_hypotheses = 4
num_candidates = 4
```

| 运行 | 方法 | 被评估模型 | Proxy selector |
|---|---|---|---|
| 1 | Direct | `ds/deepseek-v4-flash` | `ds/deepseek-v4-pro` |
| 2 | BED | `ds/deepseek-v4-flash` | `ds/deepseek-v4-pro` |
| 3 | Direct | `ds/deepseek-v4-pro` | `ds/deepseek-v4-pro` |
| 4 | BED | `ds/deepseek-v4-pro` | `ds/deepseek-v4-pro` |

被评估模型负责生成 Direct 问题和完整的单次 BED planning payload。Proxy selector 模型判断最新问题是否直接命中某条剩余 useful-info。覆盖率由代码确定，因为可见 proxy 回答被强制为某条 useful-info 原文或固定 IDK。

## 数据集

当前实验只保留 10-task 数据：

```text
ambig_swe_10_raw.jsonl
ambig_swe_10_clean.jsonl
ambig_swe_10_clean_with_useful_info.jsonl
```

`ambig_swe_10_raw.jsonl` 保存 pilot 列表中的前 10 个原始行。`ambig_swe_10_clean.jsonl` 只保留本实验使用的字段。`ambig_swe_10_clean_with_useful_info.jsonl` 是实际运行数据集，由 `ds/deepseek-v4-pro` 基于 clean 文件生成。

这 10 行不做去重，但当前切片没有重复 task：

- 总行数：10
- 唯一 task ID 数：10
- 主要分析单位：数据行

清洗后的字段：

- `task_id`：Ambig-SWE / SWE-Bench 实例 ID。
- `repo`：仓库名，例如 `django/django`。
- `hidden_issue`：agent 初始可见的压缩 issue。
- `full_issue`：原始完整 issue，作为普通 issue reporter 可回答 useful-info 抽取和评价的来源。

`base_commit`、`version`、`hints_text`、`files`、补丁、测试补丁、fail-to-pass、pass-to-pass 等本实验不用的字段只保留在 raw 文件中。

实际运行使用的 `*_with_useful_info.jsonl` 额外包含：

- `useful_info_items`：由 `ds/deepseek-v4-pro` 生成的、普通 issue reporter 可回答的 useful-info 目标。
- `useful_info_explanations`：与每条 useful-info 对齐的审计解释，包括信息类型、原始 issue 证据、相对 hidden issue 的缺口、对修 bug/写回归测试的用途、普通 reporter 为什么能回答，以及抽象/拆分理由。
- `useful_info_sufficiency`：原始 issue 相对 `hidden_issue` 新增的、用户可回答 useful 信息的简短总结。

## 数据统计

10 行 clean 数据覆盖 4 个上游仓库：

| 仓库 | 行数 |
|---|---:|
| `django/django` | 5 |
| `matplotlib/matplotlib` | 2 |
| `scikit-learn/scikit-learn` | 1 |
| `sympy/sympy` | 2 |

任务顺序：

```text
django__django-13112
django__django-15375
django__django-13297
matplotlib__matplotlib-26466
matplotlib__matplotlib-23314
scikit-learn__scikit-learn-15100
sympy__sympy-20428
sympy__sympy-15345
django__django-11239
django__django-13279
```

评价阶段仍使用 `(task_id, row_occurrence)` 作为行级 key。因此如果未来 10-task 切片中出现重复 task，结果仍能按行区分。

## Useful Information 定义

对每个数据行，`ds/deepseek-v4-pro` 预先从原始 issue 相对 `hidden_issue` 的增量中抽取 useful extra issue information。来源上下文是：

```text
full_issue
```

一条信息项会被保留，当且仅当它：

- 出现在 `full_issue` 中；
- 在 `hidden_issue` 中不存在，或明显不够具体；
- 对修 bug、确定修复范围、复现失败、编写回归测试有帮助；
- 普通 issue reporter 可以根据自己观察到的输入、输出、环境、traceback、复现步骤、期望行为或影响范围自然回答。

抽取结果直接写入：

```text
ambig_swe_10_clean_with_useful_info.jsonl
```

BED、Direct 和最终 evaluate 都从数据集字段读取同一份 useful-info 目标。

## Useful Information 抽取核查

重新生成 `ambig_swe_10_clean_with_useful_info.jsonl` 后，需要做字段级结构检查和逐行人工核查。每行应至少有 1 条 `useful_info_items`；每个 `useful_info_items` 列表都应有等长的 `useful_info_explanations` 列表；每行都应有非空的 `useful_info_sufficiency`。

人工核查时重点确认四点：抽取项确实来自 `full_issue`；相对 `hidden_issue` 提供了具体新增信息；这些信息对调试、确定修复范围、复现失败或编写回归测试有实际帮助；并且普通 issue reporter 可以自然回答。

## Useful-Info 人工审核

当前状态：useful-info 目标已经生成并完成一轮人工修订，但还没有运行 Direct 或 BED 实验。

本轮人工审核保持 proxy 机制不变。Proxy 每个澄清轮次仍最多选择一条 item，并返回该 item 原文或固定 IDK。这是有意设计：它近似普通 reporter 不会总是完美回答宽泛问题的现象，也避免奖励一个宽泛兜底问题一次覆盖大量 item。

人工修订原则：

- 每条可恢复 item 应是一个精确、用户可回答的信息槽。
- 优先保留一个好澄清问题可以直接问到的 item，避免“环境信息”这类宽泛打包。
- 弱环境/版本信息只有在明显有助于复现或界定范围时才保留。
- 长复现代码保留在审计 evidence 中；用于计分的 item 改写成紧凑的自然语言复现条件。
- 对 `hidden_issue` 中已经基本出现的信息，不再作为计分 item；除非 full issue 提供了明显更具体、用户实际观察到的细节。

人工修订摘要：

| Task | 修订前 | 修订后 | 审核说明 |
|---|---:|---:|---|
| `django__django-13112` | 4 | 4 | 将错误信息 item 改写为“完整错误显示 lazy reference 中 app label 被小写化”的用户观察细节。 |
| `django__django-15375` | 2 | 2 | 保持生成结果。 |
| `django__django-13297` | 2 | 2 | 保持生成结果。 |
| `matplotlib__matplotlib-26466` | 3 | 3 | 将环境大包拆成 Matplotlib version 和 backend；删除 `.copy()` workaround 的计分 item。 |
| `matplotlib__matplotlib-23314` | 4 | 3 | 删除 Python version；保留 Matplotlib version、backend 和聚焦后的 3D axes 复现条件。 |
| `scikit-learn__scikit-learn-15100` | 5 | 5 | 将环境 item 缩减为 scikit-learn version；保留 NFKD、具体输入、实际输出和期望输出。 |
| `sympy__sympy-20428` | 6 | 5 | 将超长复现脚本压缩为 EX domain 下 `clear_denoms()` 的复现条件；删除 earlier-version `ZeroDivisionError` 计分项；保留更具体的 `bad_poly.rep` 表示。 |
| `sympy__sympy-15345` | 3 | 3 | 保持生成结果。 |
| `django__django-11239` | 1 | 1 | 保持生成结果。 |
| `django__django-13279` | 1 | 1 | 保持生成结果。 |

生成文件原本包含 31 条可恢复 item。人工审核后，`ambig_swe_10_clean_with_useful_info.jsonl` 包含 29 条可恢复 item。

## 用户模拟器

普通 issue reporter 风格的用户模拟器 proxy 可以看到：

- 当前澄清问题
- 剩余 `useful_info_items`

proxy selector 返回一个 JSON 决策，最多选择一条 useful-info id。当澄清问题询问的是某条 item 对应的同一类用户可观察信息槽时，proxy 可以选择该 item。如果一个问题直接询问了多条剩余 item，proxy 仍然只选择一条：优先选择被最直接询问的 item；若并列，选择更具体的 item；若仍并列，选择问题中更早被问到的 item。只有“请提供更多细节”“所有相关信息”、完整复现器或没有可映射信息槽的一般上下文请求才返回 IDK。随后代码强制生成可见用户回答：

- 如果选中一条剩余 useful-info，用户回答就是该条 item 原文。
- 如果没有选中 item，用户回答固定为：

```text
I don't have that information.
```

这与 ReqElicitGym 的受控 stakeholder 设计一致：LLM 可以判断哪条用户可回答的隐藏 item 被问到，但不能改写、合并或编造信息。某条 item 一旦被选中，后续 proxy 调用的 remaining list 中就会移除它。Proxy 每轮永远不会返回超过一条 useful-info，因此宽泛问题不会获得多 item 覆盖奖励。

## 方法

### Direct

Direct runner 每轮让被评估模型根据 `hidden_issue` 和已有澄清对话生成一个澄清问题。

1. 第一轮使用统一的 Direct question prompt。
2. 后续轮次继续使用同一个 Direct prompt，但 user message 中会包含已有对话历史。
3. 每轮生成一个开放式自然语言问题和一个 rationale。
4. proxy selector 接收该问题和剩余 useful-info items。
5. 如果 proxy 选中一条 item，代码把该 item 原文作为用户回答；否则代码返回 `I don't have that information.`
6. 如果全部 useful-info 项已覆盖，则早停；否则继续到 `max_turns`。
7. 保存的 `final_summary` 由代码本地拼接 proxy 回答得到，只用于轨迹阅读，不触发额外 LLM 调用，也不参与指标计算。

### BED

BED runner 使用假设驱动的期望信息增益排序来选择澄清问题。

1. 当前轮次进行一次 BED planner LLM 调用。
2. 这一次响应同时生成 `num_hypotheses` 个假设、分歧轴、`num_candidates` 个候选澄清问题、内部 possible answer states，以及每个假设下的答案概率。
3. possible answer states 只用于内部 EIG 计算，不作为选项发给 proxy。
4. 根据返回的 likelihoods 在本地计算预测熵、条件熵和期望信息增益。
5. 选择 EIG 最高的开放式问题询问 proxy。
6. 进入下一轮时，基于更新后的对话历史重新进行一次单次 planner 调用。
7. proxy selector 接收选中的问题和剩余 useful-info items；代码强制返回原文 item 或固定 IDK。
8. 如果全部 useful-info 项已覆盖，则早停；否则继续到 `max_turns`。
9. 保存的 `final_summary` 由代码本地拼接 proxy 回答得到，只用于轨迹阅读，不触发额外 LLM 调用，也不参与指标计算。

Runner 按任务和轮次顺序执行。每次 proxy 回答后，代码用精确匹配更新覆盖情况。

启用 `--verbose-turns` 时，CLI 会输出单个 task 内部的逐轮进度：planner/question 请求阶段、被选中的问题、proxy 调用、选中的 useful-info id 或 IDK、当前覆盖率和早停状态。长时间网络运行时建议开启，因为单个 BED task 可能需要数分钟。

## 提示词

实际运行以 `src/ambig_swe_useful_info/` 下的英文提示词为准。以下内容呈现当前代码使用的完整英文提示词和用户模板。

对于结构化输出，所需 JSON schema 只出现在 system prompt 中；user message 只提供任务上下文。`OpenAIBackend` 会在 system prompt 要求 JSON 输出时启用 OpenAI-compatible JSON mode，即 `response_format={"type": "json_object"}`。

### Useful-info 抽取提示词

来源：`src/ambig_swe_useful_info/eval/useful_info.py`

`EXTRACT_SYSTEM_PROMPT`

```text
You are a software requirements analyst designing an ordinary issue-reporter clarification benchmark. Given an original GitHub issue and a shortened "problem statement" visible to an agent, compare them and extract only the information that appears in the original issue but not in the shortened problem statement, where that extra information is both USEFUL for fixing the bug or writing a regression test and ANSWERABLE by an ordinary issue reporter.

Hard requirements:

1. PRIVATE VS HIDDEN DIFFERENCE: Only extract information that is present in the private context and absent or substantially less specific in the shortened problem statement. Do not restate facts that are already clearly available in the shortened statement. A generic summary in the shortened statement does NOT cover concrete reproduction code, exact commands, exact tracebacks, exact wrong values, exact expected values, or specific environment/version details from the original issue.

2. USEFULNESS FOR BUGFIXING: Keep information if it would help a competent developer fix the bug, choose the correct scope, identify the exact failing scenario, or write a better regression test. The information does NOT need to be strictly necessary. If it is useful, keep it.

3. ORDINARY-REPORTER ANSWERABILITY: Keep only information an ordinary issue reporter could reasonably provide in response to a clarification question because it is observable from their experience, environment, input, output, traceback, reproduction steps, expected behavior, or reported scope. Exclude information that requires maintainer knowledge, benchmark oracle access, patch inspection, implementation diagnosis, regression commit knowledge, PR/issue cross-reference knowledge, exact internal code location, or the intended fix strategy. Do not extract commit hashes, PR numbers, issue numbers, or suggested fix approaches even if they appear in the original issue, unless they are necessary to reproduce the user-observed failure.

4. MINIMUM ABSTRACTION: State each item at the LOWEST specificity that preserves the useful bug-fixing information, NOT at the exact surface form used by the reporter. Use general software examples as guidance:
- If the report uses a concrete sample input value, keep the structural condition but abstract away arbitrary literals that do not affect the bug.
- If the report uses one specific filename, username, timestamp, host, request ID, or local path only as an example of a broader condition, keep the broader condition instead of the incidental literal.
- If the report shows one concrete reproduction script, preserve only the parts that are actually load-bearing for reproducing the failure or writing the regression test.
- If two candidate items would collapse to the same requirement once abstracted, emit only the abstracted requirement.

5. ATOMIC INFORMATION UNITS: Each item should contain exactly one user-answerable information slot. Split combined facts when they could be elicited by different clarification questions or are useful independently for debugging or regression testing. In particular, separate version information, environment information, reproduction trigger, minimal code/API call, actual wrong behavior, exact error/traceback, expected behavior, configuration option names/values, and affected user-visible scope. Keep tightly coupled facts together only when separating them would make the item ambiguous or not useful.

6. OBSERVABLE FACTS OVER IMPLEMENTATION GUESSES: Prefer concrete facts stated or directly demonstrated in the private context, such as exact failing inputs, expected behavior, affected scope, reproduction conditions, environment details, exact error messages, concrete API calls, and testable success criteria. Do not add inferred implementation strategies.

7. SOURCE LIMIT: Use only the original issue as the private context. Do not use developer hints, file annotations, patches, tests, or benchmark metadata as sources for extracted items.

Return only valid JSON (no markdown fences). The lengths of `items` and `explanations` MUST match. Each explanation object is audit metadata for the item at the same list index; it is not used as recoverable information during the clarification experiment.
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
```

`EXTRACT_USER_TEMPLATE`

```text
Original issue:
{full_issue}

Summarized problem statement:
{hidden_issue}
```

### Direct 提示词

来源：`src/ambig_swe_useful_info/direct/prompts.py`

`DIRECT_QUESTION_SYSTEM_PROMPT`

```text
You are a software engineer triaging an underspecified GitHub issue. Given the issue and optional clarification dialogue so far, ask the single most important next clarification question that will best resolve remaining ambiguity about the bug, intended fix, scope, or constraints.

Ask an open-ended natural-language question. Do not provide or imply multiple-choice answer options. Do not repeat a question already asked.

Return only valid JSON (no markdown fences):
{"question": "...", "rationale": "..."}
```

Direct 第一轮问题 user message：

```text
Issue:
{hidden_issue}

Dialogue so far:
(none)
```

Direct 后续追问 user message：

```text
Issue:
{hidden_issue}

Dialogue so far:
{formatted_dialogue}
```

### BED 提示词

来源：`src/ambig_swe_useful_info/bed/prompts.py`

`BED_PLANNER_SYSTEM_PROMPT`

```text
You are a BED software-issue clarification planner.

Use one JSON response to do all BED planning work for the current turn:
1. Generate distinct latent hypotheses about what the issue reporter actually wants fixed.
2. Identify genuine disagreement axes among the hypotheses.
3. Generate candidate open-ended clarification questions targeting those disagreements.
4. For each candidate question, define compact possible answer states used only for EIG scoring.
5. Estimate P(answer_state | hypothesis) for every candidate question and every hypothesis.

Each hypothesis must represent a self-consistent, plausible interpretation of the reporter's true intent -- different root causes, different scopes, different intended fixes. Hypotheses should differ meaningfully from each other.

An "axis" is a specific dimension where at least two hypotheses take different positions. Typical axes for SWE issues: target file/class/function, scope of the fix (narrow vs broad), expected behavior, implementation strategy, required reproducer shape, failure mode or error signature.

Rules:
- Clarification questions must be open-ended. Do not include answer options, multiple-choice choices, suggested answers, examples of possible answers, or "choose one" wording.
- Candidate possible answers are internal answer states for EIG scoring only. They are never shown to the proxy user.
- Candidate questions should be one-at-a-time questions that a real issue reporter could answer naturally.
- Hypothesis probabilities must sum to 1 before normalization.
- For every candidate, each hypothesis must have a probability distribution over all possible answer state IDs.
- Use only the visible issue and clarification dialogue.

Return only valid JSON (no markdown fences):
{
  "hypotheses": [
    {
      "id": "H1",
      "probability": 0.25,
      "summary": "plausible interpretation",
      "evidence": ["visible evidence"]
    }
  ],
  "disagreement_axes": [
    {
      "name": "short axis name",
      "description": "one sentence",
      "positions": [
        {"hypothesis_ids": ["H1"], "stance": "internal stance description"}
      ]
    }
  ],
  "candidates": [
    {
      "id": "Q1",
      "axis_name": "short axis name",
      "question": "one open-ended clarification question",
      "rationale": "what uncertainty this question should reduce",
      "possible_answers": [
        {"id": "A1", "answer": "internal possible answer state"},
        {"id": "A2", "answer": "another internal possible answer state"}
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

BED planner user message：

```text
Issue:
{hidden_issue}

Dialogue history:
{dialogue_history_json}

Planner configuration:
- num_hypotheses: {num_hypotheses}
- num_candidates: {num_candidates}
```

### Proxy 提示词

来源：`src/ambig_swe_useful_info/proxy/prompts.py`

`PROXY_SYSTEM_PROMPT`

```text
You are a controlled user proxy for a GitHub software-engineering issue.

Your task is to decide whether the agent's latest clarification question semantically asks for one of the remaining useful-information items that an ordinary issue reporter could answer.

Rules:
- Select at most one item id.
- Select an item only if the question asks for the same user-observable information slot as that item.
- If the question directly or clearly asks about multiple remaining items, still select exactly one:
  choose the most directly asked item; if tied, choose the more specific item; if still tied, choose
  the item asked about earliest in the question.
- If the question is only a broad request for "more details", "all information", a full reproducer, or
  general context without a mappable information slot, set selected_id to null.
- Do not invent facts, paraphrase items, or answer from outside the provided item list.

Return only valid JSON (no markdown fences):
{"selected_id": "UI1", "reasoning": "brief explanation"}

If no item is directly asked:
{"selected_id": null, "reasoning": "brief explanation"}
```

`PROXY_USER_TEMPLATE`

```text
Clarification question from the agent:
{question}

Remaining useful-information items:
{remaining_items}
```

## 指标

每个数据行记录：

- `useful_info_coverage`：最终被 proxy 原文返回的 useful-info 比例。
- `coverage_curve`：每一轮之后的平均累计 useful-info 覆盖率。
- `TTR`：累计覆盖率首次达到 1.0 的轮数；如果最大轮数内未达到，则记为 `max_turns + 1`。
- `ATC`：实际提问轮数；一旦 useful-info 全部覆盖就早停。
- `recovery_rate`：最大轮数内达到完整 useful-info 覆盖的数据行比例。
- `idk_per_task`：proxy 返回 `I don't have that information.` 的平均次数。

`TTR`、`ATC` 和 `idk_per_task` 越低越好；覆盖率和恢复率越高越好。

## 轨迹记录

每条 runner 输出保存：

- `task_id`
- `runner`
- `dialogue`
- `asked_questions`
- `final_summary`
- `metrics`
- `turn_details`
- `metadata`

`metadata` 记录数据集路径、行内 occurrence、backend、runner、被评估模型、proxy selector 模型、输出路径和配置值。`metrics` 记录 ATC、IDK 次数和 `stop_reason`。

`final_summary` 由代码本地拼接 proxy 回答得到。Direct 和 BED 都会为每个实际提出的问题写入一条 `turn_details`。共享的逐轮字段包括：

- `selected_question`
- `question_rationale`
- `simulated_answer`
- `remaining_useful_info_before`
- `proxy_selected_id`
- `proxy_reasoning`
- `selected_useful_info`
- `newly_covered`
- `covered_items_after`
- `coverage_ratio_after`
- `early_stop_reason`

BED 额外记录 `hypotheses_before`、`disagreement_axes` 和 `candidates_ranked`。每个 `candidates_ranked` 条目会保存开放式问题、rationale、内部 `eig_stances`、各假设下的答案状态分布、预测分布、预测熵、期望条件熵、EIG、selected 标记和 axis name。BED 的逐轮记录还包含 planner 审计字段：`planner_parse_warnings`、`num_hypotheses_returned`、`num_candidates_returned` 和 `used_fallback`。

最终 `per_task_<model>.jsonl` 记录行级评价结果，包括 `row_occurrence`、useful-info 数量、两种方法的覆盖率、逐轮覆盖曲线、TTR、是否 recovered、ATC 和 IDK 次数。

## 运行实验

让包可导入：

```powershell
python -m pip install -e .
```

或只在当前 PowerShell 会话中设置：

```powershell
$env:PYTHONPATH = "src"
```

设置凭据：

```powershell
$env:OPENAI_BASE_URL = "https://llm.xmcp.ltd/"
$env:OPENAI_API_KEY = "<your-api-key>"
```

OpenAI-compatible 请求默认使用 600 秒超时。若某次运行需要不同限制，可以用 `--request-timeout <seconds>` 或 `AMBIG_SWE_REQUEST_TIMEOUT` 环境变量覆盖。

生成 useful-info 目标：

```powershell
python -m ambig_swe_useful_info.cli prepare-useful-info `
  --input ambig_swe_10_clean.jsonl `
  --output ambig_swe_10_clean_with_useful_info.jsonl `
  --backend openai `
  --model ds/deepseek-v4-pro
```

推荐完整运行命令：

```powershell
.\run_experiment.ps1 `
  -Backend openai `
  -FlashModel ds/deepseek-v4-flash `
  -ProModel ds/deepseek-v4-pro `
  -ProxyModel ds/deepseek-v4-pro `
  -MaxTurns 5 `
  -NumHypotheses 4 `
  -NumCandidates 4 `
  -RequestTimeout 600 `
  -VerboseTurns
```

脚本会对每个被评估模型先运行 Direct、再运行 BED，并对该模型下的成对结果做评价。

预期输出目录：

```text
results/ambig_swe_10_usefulinfo_v1/
```

预期输出文件：

```text
results/ambig_swe_10_usefulinfo_v1/bed_flash.jsonl
results/ambig_swe_10_usefulinfo_v1/direct_flash.jsonl
results/ambig_swe_10_usefulinfo_v1/report_flash.txt
results/ambig_swe_10_usefulinfo_v1/per_task_flash.jsonl
results/ambig_swe_10_usefulinfo_v1/bed_pro.jsonl
results/ambig_swe_10_usefulinfo_v1/direct_pro.jsonl
results/ambig_swe_10_usefulinfo_v1/report_pro.txt
results/ambig_swe_10_usefulinfo_v1/per_task_pro.jsonl
```

中断后可在同一命令后添加 `-Resume` 继续。

## 监控进度

运行时控制台会显示当前 runner、数据集、输出文件、任务数、模型角色、平均 ATC、平均 IDK、单任务耗时和 ETA。

结果文件可以直接查看：

```powershell
Get-Content results/ambig_swe_10_usefulinfo_v1/report_flash.txt
Get-Content results/ambig_swe_10_usefulinfo_v1/report_pro.txt
```

## 评估命令

`run_experiment.ps1` 已经自动执行 evaluate。若需要单独重跑某个评价，可以使用：

```powershell
python -m ambig_swe_useful_info.cli evaluate `
  --bed results/ambig_swe_10_usefulinfo_v1/bed_flash.jsonl `
  --direct results/ambig_swe_10_usefulinfo_v1/direct_flash.jsonl `
  --dataset ambig_swe_10_clean_with_useful_info.jsonl `
  --max-turns 5 `
  --report results/ambig_swe_10_usefulinfo_v1/report_flash.txt `
  --per-task-jsonl results/ambig_swe_10_usefulinfo_v1/per_task_flash.jsonl
```

Evaluator 会直接读取正常的 runner 输出文件，不需要额外 compact 或转换步骤：它支持当前 compact JSONL 和早期 pretty-printed 多行 JSON 输出。带有截断或非对象尾部残片的文件会被视为无效输出，应通过 resume 清理或重新运行后再评价。

也可以单独运行某个 runner：

```powershell
python -m ambig_swe_useful_info.cli run `
  --dataset ambig_swe_10_clean_with_useful_info.jsonl `
  --output results/ambig_swe_10_usefulinfo_v1/bed_flash.jsonl `
  --runner bed `
  --backend openai `
  --model ds/deepseek-v4-flash `
  --proxy-model ds/deepseek-v4-pro `
  --max-turns 5 `
  --num-hypotheses 4 `
  --num-candidates 4 `
  --request-timeout 600 `
  --verbose-turns
```

Direct 只需把 `--runner bed` 改成 `--runner direct`，并修改输出文件名。

## 可复现性控制

- 所有运行使用 `ambig_swe_10_clean_with_useful_info.jsonl`。
- 原始切片数据保留为 `ambig_swe_10_raw.jsonl`。
- 清洗后的 issue/proxy 上下文数据保留为 `ambig_swe_10_clean.jsonl`。
- Useful-info 目标存放在实际运行数据集字段中。
- Proxy selector 模型固定为 `ds/deepseek-v4-pro`。
- 评价阶段使用 proxy 回答精确匹配，不调用单独的覆盖判断模型。
- 两个被评估模型共享同一份 useful-info 目标。
- 输出比较按行配对，重复 `task_id` 会通过 `row_occurrence` 区分。
- Runner 输出为 compact JSONL，每行一个完整 JSON 对象。非 resume 运行会先截断已有输出文件；resume 模式会先清理并保留已完成记录再继续追加。如果网络运行被外部杀掉，重跑同一路径前应确认没有旧进程仍在写文件。

## 结果解释边界

这个实验可以支持关于普通 issue reporter 可回答的 Ambig-SWE issue 信息恢复效率的结论。它不能直接说明某个方法会提升真实代码修复成功率，除非后续再加入独立的 coding-agent 评价。

Ambig-SWE 中缺失的信息是 issue report 中的 bug-fixing context，而不是一般产品需求。因此即使 BED 表现更好，也应表述为“更好地恢复有用的 issue reporter 信息”，而不是直接泛化为“更好地完成真实需求澄清”。

## 已知局限

- proxy 是 LLM 模拟用户，不是真实 issue reporter。
- useful-info 抽取在预处理阶段依赖 LLM；实验运行时的 proxy item selection 也依赖 LLM。
- 覆盖判断是严格匹配：只有 proxy 选中 item 且代码返回该 item 原文时才算覆盖。
- 当前数据集只有 10 个 task，结果属于 pilot 规模，只适合方向性解释。
- 实验不评价补丁生成，也不评价测试通过率。
- EIG 目标倾向选择能清晰切分假设的问题；如果具体复现条件没有形成分歧轴，BED 可能不会主动追问这些信息。
