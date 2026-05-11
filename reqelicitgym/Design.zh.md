# ReqElicitGym 三方法实验设计

## 目标

本实验使用从 ReqElicitGym 官方测试集中抽取的 10 类应用任务，比较三种需求澄清提问方法：

- **Direct**：直接澄清提问 baseline。
- **BED**：rolling-belief Bayesian Experimental Design。
- **Aspect-aware**：显式关注 Interaction / Content / Style 三类需求方面的澄清提问方法。

实验关注的问题是：在一个受控的隐式需求获取任务中，显式提醒模型从不同需求方面提问，是否能提升澄清问题命中率和隐式需求获取效率。

每个方法在每个任务上的最多提问轮次数等于该任务的隐式需求数。这个数字只用于本地 runner 控制 episode 长度和 interviewer 最多提问次数，不会写入 `observation()`，也不会出现在任何 LLM prompt 中，因此不会向 LLM 泄露答案数量，不构成作弊。每一轮 interviewer 生成一个澄清问题；随后一个合并的 LLM evaluator/stakeholder 调用判断该问题是否直接命中某个尚未获得的隐式需求，并返回模拟用户回答。任务在以下任一条件满足时停止：

1. 方法主动结束；
2. 达到该任务的提问轮次预算。

本实验不要求模型生成最终代码或最终产品规格；评估对象是澄清问题是否成功获得 benchmark 标注的隐式需求。

不合法的 interviewer 或 evaluator/stakeholder 结构化输出不算作实验结果。每次结构化 LLM 调用必须返回合法 JSON，并通过字段校验。JSON 解析失败或字段校验失败时会重试一次；如果重试后仍失败，该任务直接报错，不会写成普通未命中，也不会使用 fallback 问题或 fallback miss 继续运行。

开放式提问、不提供选项或示例答案等约束属于 prompt-level 指令，不作为本地后处理硬校验条件。若模型返回的 JSON 结构合法，但问题文本在语义上违反这些提问风格约束，该轮仍按真实模型行为保留在实验轨迹中，并作为方法表现的一部分解释。

## 实验运行

三种方法分别在 `ds/deepseek-v4-flash` 和 `ds/deepseek-v4-pro` 上运行一次。Evaluator / Stakeholder 统一使用 `ds/deepseek-v4-pro`。

| 运行 | 方法 | Interviewer 模型 | Evaluator / Stakeholder 模型 |
|---|---|---|---|
| 1 | Direct | `ds/deepseek-v4-flash` | `ds/deepseek-v4-pro` |
| 2 | BED | `ds/deepseek-v4-flash` | `ds/deepseek-v4-pro` |
| 3 | Aspect-aware | `ds/deepseek-v4-flash` | `ds/deepseek-v4-pro` |
| 4 | Direct | `ds/deepseek-v4-pro` | `ds/deepseek-v4-pro` |
| 5 | BED | `ds/deepseek-v4-pro` | `ds/deepseek-v4-pro` |
| 6 | Aspect-aware | `ds/deepseek-v4-pro` | `ds/deepseek-v4-pro` |

## 数据集

当前实验数据文件为：

```text
ReqElicitGym_10.jsonl
```

该文件由原始完整测试集生成：按原始数据顺序，从每个 `application_type` 中选取第一个任务，共得到 10 个任务。生成后，原始完整数据集已从本实验目录删除，避免后续运行误用完整测试集。

每行 JSON 是一个任务，包含：

- `name`：任务名称。
- `application_type`：应用类别。
- `initial_requirements`：interviewer 可见的初始需求。
- `Implicit Requirements`：benchmark 隐藏的隐式需求列表，只给 evaluator/stakeholder 使用。

每条隐式需求包含：

- `Aspect`：隐式需求方面，取值为 `Interaction`、`Content` 或 `Style`。
- `RequirementText`：隐式需求原文。

## 数据统计

10 题子集：

| 任务 | 应用类别 | 隐式需求数 | Interaction | Content | Style |
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

汇总统计：

| 项目 | 数值 |
|---|---:|
| 任务数 | 10 |
| 应用类别数 | 10 |
| 隐式需求总数 | 65 |
| 每题隐式需求数最少值 | 3 |
| 每题隐式需求数最多值 | 11 |
| 每题隐式需求数平均值 | 6.50 |

按需求方面统计：

| 方面 | 隐式需求数 |
|---|---:|
| Interaction | 24 |
| Content | 20 |
| Style | 21 |

## 共享 Episode Loop

三种方法运行在同一套 LLM-backed episode loop 中：

1. 从 `ReqElicitGym_10.jsonl` 加载任务。
2. 将任务的 `initial_requirements` 作为第一条用户消息。
3. interviewer 每轮先判断是否还需要继续澄清。
4. 如果 interviewer 返回 `finish`，episode 结束，不调用 evaluator/stakeholder。
5. 如果 interviewer 返回 `ask`，则必须同时返回一个合法的澄清问题。
6. 合并的 evaluator/stakeholder LLM 调用读取当前问题和尚未获得的隐式需求列表。
7. evaluator 判断该问题是否直接询问了某一条尚未获得的隐式需求。
8. 如果命中一个有效 requirement id，则只标记这一条需求为 elicited，并强制模拟用户回答为该隐式需求原文。
9. 如果未命中，则模拟用户回答固定为：

```text
I do not have a strong preference about that, or it is not important to me.
```

10. 重复以上过程，直到方法主动结束，或达到该任务的提问轮次预算。

为了降低评估噪声，evaluator 最多接受一个 requirement id。如果 LLM 返回多个 id，代码只使用第一个仍未获得的有效 id，并在 trace 中记录 warning。

## 方法

### Direct

实现类：`DirectBaseline`

Direct 是直接 prompting baseline。它不维护显式假设、不计算信息增益，也不显式区分 Interaction / Content / Style。

每轮流程：

1. 向 LLM 提供任务名称、应用类别、初始需求和可见对话历史。
2. 要求 LLM 在 `ask` 和 `finish` 中选择一个行动。
3. 如果返回 `finish`，该任务停止提问。
4. 如果返回 `ask`，响应中必须包含一个 targeted clarification question。
5. 将该问题交给共享 episode loop。
6. 如果 JSON 解析失败或字段校验失败，则重试一次；重试后仍失败则报错。
7. 本地只校验结构化输出字段，不对提问风格做规则过滤；风格偏离会保留为模型行为。

### BED

实现类：`BEDInterviewer`

BED 维护 rolling belief state，并用本地计算的纯 EIG 选择问题。

belief state 包含：

- `hypotheses`：恰好 `num_hypotheses` 个完整需求假设及其概率。
- `hypothesis_disagreements`：不同假设之间尚未解决的分歧维度。
- `asked_questions`：BED 已经选中过的问题。
- `update_notes`：belief 更新说明。

每轮流程：

1. 调用一次 BED planner LLM。
2. planner 在 `ask` 和 `finish` 中选择一个行动。
3. 如果返回 `finish`，该任务停止提问。
4. 如果返回 `ask`，planner 必须初始化或更新 `belief_state`。
5. 同一次 planner 响应返回恰好 `num_candidates` 个候选问题。
6. 每个候选问题包含 possible answer types 和各 hypothesis 下的 answer likelihoods。
7. 本地代码计算期望信息增益：

```text
EIG(q)=H[p(h)] - sum_a p(a|q) H[p(h|a,q)]
```

8. 选择 `EIG(q)` 最高的候选问题。
9. 将选中的 question 写回 belief state。
10. 将该问题交给共享 episode loop。
11. 如果 JSON 解析失败、字段校验失败、hypotheses 数量不等于 `num_hypotheses`、candidate 数量不等于 `num_candidates`，或 likelihoods 不完整，则重试一次；重试后仍失败则报错。
12. 本地只校验结构化输出字段和 BED 所需的 EIG 计分字段，不对提问风格做规则过滤；风格偏离会保留为模型行为。

BED 配置：

```text
--num-hypotheses 4
--num-candidates 4
```

BED trace 中会记录 `combined_planner_call: true`。候选问题只用于本地排序，最终只把 `EIG(q)` 最高的问题展示给模拟用户。除 EIG 外，本地不使用其它启发式修正项。

### Aspect-aware

实现类：`AspectAwareClarifier`

Aspect-aware 是 Interaction / Content / Style 感知的澄清提问方法。它不使用 BED、EIG、隐藏答案、固定 benchmark 答案位置或任务特定 blacklist 规则。模型每轮只根据可见任务与对话，自行选择一个方面并生成一个问题。

三个方面定义为：

- **Interaction**：用户如何操作、输入、选择、导航、配置、提交或触发动作。
- **Content**：系统需要展示或收集哪些信息、字段、记录、视图、报告或详情。
- **Style**：视觉或呈现偏好，例如布局、颜色、响应式行为或整体外观。

每轮流程：

1. 向 LLM 提供任务名称、应用类别、初始需求、可见对话历史、已问问题和此前选择过的 aspects。
2. 要求 LLM 在 `ask` 和 `finish` 中选择一个行动。
3. 如果返回 `finish`，该任务停止提问。
4. 如果返回 `ask`，LLM 必须从 `Interaction`、`Content`、`Style` 中自行选择一个方面。
5. LLM 围绕该方面生成一个 targeted clarification question。
6. 将该问题交给共享 episode loop。
7. 如果 JSON 解析失败、字段校验失败、aspect 非法或 question 为空，则重试一次；重试后仍失败则报错。
8. 本地只校验结构化输出字段，不对提问风格做规则过滤；风格偏离会保留为模型行为。

## 提示词

本节列出源码中的原版英文提示词模板。实际运行时以 `reqelicitgym_experiment/interviewers.py` 和 `reqelicitgym_experiment/llm_gym.py` 为准。花括号中的表达式表示运行时插入的变量。

### Direct 提问调用

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

### BED planner 调用

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

### Aspect-aware 提问调用

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

### Evaluator / Stakeholder 调用

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

### 结构化输出重试追加提示

interviewer 的 `ask` / `finish` 行动调用，以及 evaluator/stakeholder 调用，在第一次 JSON 解析失败或字段校验失败时，会在第二次调用的 system prompt 末尾追加以下英文文本：

```text
Your previous response had invalid JSON or did not match the required schema. Validation error: {last_error}
Return exactly one valid JSON object following the schema. No Markdown.
```

保存 evaluator/stakeholder 结果前，代码会再次约束回答：命中时强制使用隐式需求原文，未命中时强制使用固定无偏好回答。Evaluator/stakeholder 不使用 fallback miss；如果重试后仍无法返回合法 JSON 或通过字段校验，该任务直接报错。

## 指标

每个任务记录：

- `total_requirements`：该任务的隐式需求总数。
- `total_elicited`：成功获得的隐式需求数。
- `elicitation_ratio`：`total_elicited / total_requirements`。
- `tkqr`：turn-discounted key question rate，越早命中权重越高。
- `ora`：optimal-round alignment，衡量实际轮数与 benchmark 理想轮数的接近程度。
- `num_rounds`：实际提问轮数。
- `step_budget`：该任务允许的最多提问轮数，等于该任务隐式需求数。该值不提供给 LLM。
- `optimal_rounds`：该任务隐式需求数。
- `aspect_type_elicitation`：按 `Interaction`、`Content`、`Style` 分组的隐式需求命中情况。

汇总报告记录：

- `total_elicitation_ratio`：所有任务中成功获得的隐式需求总数 / 隐式需求总数。
- `average_elicitation_ratio`：任务级 `elicitation_ratio` 平均值。
- `average_tkqr`。
- `average_ora`。
- `average_rounds`。

## 轨迹记录

每个方法会保存完整任务结果和逐轮 trace。

输出结构包括：

- `overall`：方法级汇总指标。
- `task_results`：每个任务的指标和逐轮记录。
- `conversations`：便于人工审计的对话摘要。

每轮记录包括：

- `turn`：轮次编号。
- `interviewer`：本轮提出的问题。
- `user`：模拟用户回答。
- `action_type`：`clarify` 表示命中隐式需求，`probe` 表示未命中，`finish` 表示方法主动结束。
- `elicited_requirement_ids`：本轮命中的隐式需求 id。
- `elicited_requirements`：本轮命中的隐式需求原文。
- `judge` / `evaluator`：LLM evaluator 原始判断。
- `bed_decision_trace`：方法决策 trace。字段名沿用历史实现，Direct、BED 和 Aspect-aware 都会把各自的决策信息放在这里。
- `elicitation_ratio`：截至本轮的任务完成比例。

## Benchmark 解释

ReqElicitGym 更适合作为一个受控的隐式需求获取 benchmark，而不应被视为真实软件工程需求澄清能力的可靠代理。

主要风险来自标注模式。原始完整测试集中，`Style` 隐式需求绝大多数是 color-like 偏好；本 10 题子集中的 Style 需求也主要表现为背景色与界面组件/元素颜色。因此，显式提示模型关注 Style 或颜色相关偏好，可能显著提高 benchmark 分数，但这种提升未必代表模型具备更通用的需求工程提问能力。为避免过度贴合 benchmark，本实验不把 Style 进一步拆成更细的提问类别，仍保持与 Interaction、Content 同一层级。

这对 BED 的解释尤其重要。BED 的目标是降低多个 plausible complete requirements 之间的不确定性。在真实项目中，业务目标、用户角色、工作流变体、数据约束、系统集成、权限、异常情况和非功能需求都可能是高价值澄清问题。但在 ReqElicitGym 中，如果隐藏目标是具体颜色或展示字段，这类真实工程问题经常会被判为 miss。因此，BED 在本 benchmark 上表现不佳时，更应解释为 benchmark mismatch，而不是 EIG-based clarification 本身没有价值。

本实验中的 Aspect-aware 方法应被解释为一种轻量、透明的 benchmark-facing 方法：它不读取隐藏答案，也不使用硬编码规则，但通过显式提醒模型覆盖 Interaction / Content / Style，测试方面感知提问是否能在该类任务上改善命中率和提问效率。

## 运行实验

创建本地 `.env` 文件或在终端中设置环境变量：

```text
OPENAI_BASE_URL="https://llm.xmcp.ltd/"
OPENAI_API_KEY="<your-api-key>"
OPENAI_MODELS="ds/deepseek-v4-flash ds/deepseek-v4-pro"
```

Smoke test：

```powershell
python -B run_experiment.py --methods aspect_aware --models ds/deepseek-v4-flash --max-tasks 1 --judge-model ds/deepseek-v4-pro
```

主实验命令：

```powershell
python -B run_experiment.py --methods direct bed aspect_aware --models ds/deepseek-v4-flash ds/deepseek-v4-pro --max-tasks 10 --num-hypotheses 4 --num-candidates 4 --judge-model ds/deepseek-v4-pro
```

中断后可用同一命令加 `--resume` 继续。

## 输出文件

- `outputs/direct_flash_results.json`
- `outputs/bed_flash_results.json`
- `outputs/aspect_aware_flash_results.json`
- `outputs/direct_pro_results.json`
- `outputs/bed_pro_results.json`
- `outputs/aspect_aware_pro_results.json`
- `outputs/llm_summary.json`
