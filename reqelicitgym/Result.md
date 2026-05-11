# Complete ReqElicitGym Results and Trace Analysis

> **Completion status: all planned Flash and Pro runs are complete.** The complete result set now includes `direct_flash`, `bed_flash`, `aspect_aware_flash`, `direct_pro`, `bed_pro`, and `aspect_aware_pro`. Each run covers all 10 tasks and 65 hidden implicit requirements in `ReqElicitGym_10.jsonl`. Before the final BED Pro run, the runner resource parameters were corrected so `--max-tokens` / `--timeout` are actually passed into interviewer and evaluator calls. This only affects Pro call resource limits; it does not change prompts, dataset, task budgets, hypothesis count, candidate count, EIG logic, or evaluator rules.

## Experimental Setup

The experiment uses `ReqElicitGym_10.jsonl`, which contains 10 tasks, one from each application type, with 65 hidden implicit requirements in total. The hidden requirements contain 24 Interaction, 20 Content, and 21 Style requirements. All three methods share the same LLM-backed episode loop: the interviewer asks one clarification question per turn, and `ds/deepseek-v4-pro` acts as the evaluator/stakeholder to judge whether the question directly elicits one remaining hidden requirement and to return the simulated user response.

The three methods are each run with `ds/deepseek-v4-flash` and `ds/deepseek-v4-pro`. The Evaluator / Stakeholder model is always `ds/deepseek-v4-pro`.

- **Direct**: a direct clarification baseline with no explicit aspect or hypothesis state.
- **BED**: a rolling-belief method that generates candidate questions and selects by local EIG.
- **Aspect-aware**: a method that explicitly asks the model to choose among Interaction, Content, and Style before asking a clarification question.

For each task, the maximum number of question turns equals the number of hidden requirements for that task. This budget is used only by the local runner and is not included in the LLM prompt.

## Overall Results

| Run | Elicited | Total Ratio | Avg Ratio | Avg TKQR | Avg ORA | Avg Rounds |
|---|---:|---:|---:|---:|---:|---:|
| Direct Flash | 4/65 | 6.15% | 8.76% | 0.2021 | 0.4488 | 2.40 |
| BED Flash | 11/65 | 16.92% | 18.53% | 0.1919 | 0.9412 | 5.80 |
| Aspect-aware Flash | 18/65 | 27.69% | 28.34% | 0.4266 | 0.7698 | 4.40 |
| Direct Pro | 6/65 | 9.23% | 12.76% | 0.2037 | 0.4683 | 2.40 |
| BED Pro | 7/65 | 10.77% | 9.86% | 0.1223 | 0.6375 | 3.50 |
| Aspect-aware Pro | 17/65 | 26.15% | 29.26% | 0.3949 | 0.7072 | 4.10 |

Aspect-aware is the strongest method under both Flash and Pro settings. Aspect-aware Flash elicits 18/65 requirements, giving the highest total ratio and TKQR among all six runs. Aspect-aware Pro elicits 17/65 requirements and reaches the highest average task-level ratio, 29.26%.

Pro does not yield a uniform improvement. Direct Pro improves slightly over Direct Flash: 6 hits instead of 4, with the same average rounds of 2.40. BED Pro drops substantially from BED Flash: 7 hits instead of 11, average rounds fall from 5.80 to 3.50, and ORA falls from 0.9412 to 0.6375. Aspect-aware Pro stays close to Flash but is slightly lower in total hits, with 17 vs 18.

## Flash vs Pro Comparison

| Method | Flash Elicited | Pro Elicited | Change | Flash Avg Rounds | Pro Avg Rounds | Main Observation |
|---|---:|---:|---:|---:|---:|---|
| Direct | 4/65 | 6/65 | +2 | 2.40 | 2.40 | Pro is slightly better, but still early-stops and never elicits Style |
| BED | 11/65 | 7/65 | -4 | 5.80 | 3.50 | Pro finishes earlier; EIG choices align less with benchmark hits |
| Aspect-aware | 18/65 | 17/65 | -1 | 4.40 | 4.10 | Both models remain strong; Style advantage is stable |

The model comparison shows that stronger base-model capability does not automatically improve hidden-requirement elicitation. This is especially clear for BED: the Pro planner often asks higher-level product-scoping questions and finishes earlier, reducing the chance of hitting the benchmark labels. Aspect-aware is the most stable method, suggesting that explicit aspect guidance matters more here than model scale alone.

## Results by Aspect

| Run | Interaction | Content | Style |
|---|---:|---:|---:|
| Direct Flash | 2/24 (8.33%) | 2/20 (10.00%) | 0/21 (0.00%) |
| BED Flash | 7/24 (29.17%) | 4/20 (20.00%) | 0/21 (0.00%) |
| Aspect-aware Flash | 9/24 (37.50%) | 5/20 (25.00%) | 4/21 (19.05%) |
| Direct Pro | 3/24 (12.50%) | 3/20 (15.00%) | 0/21 (0.00%) |
| BED Pro | 2/24 (8.33%) | 5/20 (25.00%) | 0/21 (0.00%) |
| Aspect-aware Pro | 9/24 (37.50%) | 4/20 (20.00%) | 4/21 (19.05%) |

Style is the clearest separator. Direct and BED elicit no Style requirements in either Flash or Pro. Aspect-aware elicits 4/21 Style requirements in both model settings. On Interaction, Aspect-aware Flash and Pro both reach 9/24. On Content, BED Pro and Aspect-aware Flash each reach 5/20, slightly above the other runs.

This pattern is tightly linked to the dataset annotations. In this subset, Style requirements are mostly color-like preferences: background colors, component colors, and interface element color schemes. Aspect-aware benefits from explicitly prompting the model to consider Style, but this should be read as a benchmark-facing gain rather than complete evidence of broad real-world visual requirements elicitation ability.

## Results by Task

| Task | Hidden Reqs | Direct Flash | BED Flash | Aspect Flash | Direct Pro | BED Pro | Aspect Pro |
|---|---:|---:|---:|---:|---:|---:|---:|
| Stock Report Generation System | 5 | 1 | 2 | 1 | 2 | 1 | 3 |
| Texas Hold'em Online Poker Platform | 5 | 0 | 0 | 0 | 0 | 0 | 2 |
| Credit Repair Lead Generation Website | 3 | 1 | 1 | 2 | 1 | 0 | 1 |
| customer service call logging system | 10 | 0 | 2 | 3 | 0 | 3 | 0 |
| Online Polling System | 5 | 0 | 0 | 0 | 1 | 1 | 2 |
| Real Estate Property Search and Listings System | 5 | 1 | 2 | 1 | 1 | 0 | 2 |
| Email Composition and Delivery Platform | 7 | 0 | 1 | 3 | 0 | 2 | 1 |
| Driver Recruitment and Job Posting System | 11 | 0 | 1 | 2 | 0 | 0 | 4 |
| Global Institute of Information Security Course Enrollment Portal | 7 | 0 | 1 | 3 | 0 | 0 | 1 |
| Medical Journal Publishing and Access System | 7 | 1 | 1 | 3 | 1 | 0 | 1 |

At the task level, Aspect-aware's advantage is distributed rather than caused by a single outlier. Aspect-aware Pro improves on several tasks that were difficult for Flash, including Poker, Online Polling, Real Estate, and Driver Recruitment. However, it is weaker than Aspect-aware Flash on customer service, Email, Course Enrollment, and Medical Journal. BED Pro has useful hits on customer service and Email but early-stops with zero hits on Real Estate, Driver Recruitment, Course Enrollment, and Medical Journal.

## Trace Analysis

### Direct

Direct Flash and Direct Pro behave similarly. Both ask 24 evaluated questions and voluntarily finish in 9 out of 10 tasks. Flash has 4 clarify turns and 20 probe turns; Pro has 6 clarify turns and 18 probe turns. Pro slightly improves Interaction and Content elicitation: Interaction moves from 2/24 to 3/24, and Content from 2/20 to 3/20. Style remains 0/21.

Direct's main failure modes remain early stopping and benchmark mismatch. It often asks reasonable product questions, such as real-money versus virtual chips, account management, user roles, implementation details, page sections, and email workflows. These questions can matter in real products, but they do not directly ask for ReqElicitGym's hidden requirements and are therefore judged as probes. Pro does not change this structural issue; it only occasionally asks closer to the hidden labels.

Direct's low average rounds should not be read as high efficiency. Several tasks finish with zero or very low elicitation, especially larger tasks such as customer service, Email, Driver Recruitment, and Course Enrollment. This explains why Direct's ORA remains low in both Flash and Pro.

### BED

BED Flash and BED Pro differ sharply. BED Flash asks 58 evaluated questions, with 11 clarify turns, 47 probe turns, and only 2 voluntary finishes. Its average rounds are 5.80 and ORA is 0.9412. BED Pro asks only 35 evaluated questions, with 7 clarify turns, 28 probe turns, and 8 voluntary finishes. Its average rounds fall to 3.50 and ORA to 0.6375.

The BED Pro drop first appears as early stopping in the trace. The Pro planner often decides after only a few turns that no more clarification is useful. Driver Recruitment, Course Enrollment, and Medical Journal each stop after 2 rounds with zero hits. BED Flash more often approaches the round budget, giving itself more chances to hit Interaction or Content labels even though many questions are probes.

The EIG trace makes the alignment issue clearer. In BED Flash, clarify questions have higher average selected EIG than probe questions, 0.5099 vs 0.4087, so EIG has some positive relation to benchmark hits. In BED Pro, clarify questions average 0.7369 while probes average 0.8018. Pro's high-EIG questions are more often high-level product hypothesis questions rather than direct hidden-label questions. It tends to ask about target users, account roles, platform boundaries, private rooms, integrations, and additional features.

Thus, BED Pro's low score should not be reduced to "EIG is useless." The trace suggests a mismatch between objectives: BED optimizes hypothesis discrimination under visible context, while ReqElicitGym rewards direct hits on hidden annotations. The Pro model may amplify that mismatch by constructing broader product hypotheses.

### Aspect-aware

Aspect-aware is the most stable method across model settings. Flash asks 44 evaluated questions, with 18 clarify turns, 26 probe turns, and 7 finishes. Pro asks 41 evaluated questions, with 17 clarify turns, 24 probe turns, and 6 finishes. The two runs are close in question count, hit count, and average rounds.

The selected-aspect trace distribution is:

| Run | Selected Content | Selected Interaction | Selected Style |
|---|---:|---:|---:|
| Aspect-aware Flash | 16 questions / 6 hits | 18 questions / 8 hits | 10 questions / 4 hits |
| Aspect-aware Pro | 17 questions / 5 hits | 17 questions / 7 hits | 7 questions / 5 hits |

These selected-aspect hit counts are grouped by the model's chosen aspect; they are not always identical to the true aspect of the hidden requirement. By true hidden aspect, Aspect-aware Flash and Pro both elicit 4 Style requirements. Both runs have a few cross-aspect hits: in Flash, 15 of 18 hits have matching selected and elicited aspects; in Pro, 15 of 17 match. For example, a Content question can elicit an Interaction requirement, and a Style question can also elicit an Interaction requirement. The aspect prompt is therefore a useful questioning scaffold, not a hard evaluator label.

Aspect-aware's advantage comes from explicit coverage of Interaction, Content, and Style. Style is the clearest case: Direct and BED almost never spend clarification budget on color preferences, while Aspect-aware asks about visual style, layout, color scheme, and overall look and feel. It can still fail when the question remains too generic, such as asking broadly about visual style or layout without directly touching background color or component color.

## Trace Integrity Check

I checked all evaluator turns across the six result files for structural consistency:

| Check | Count |
|---|---:|
| Evaluator returned multiple requirement ids | 0 |
| `probe` turn with nonempty ids | 0 |
| `is_relevant=true` with empty ids | 0 |
| `clarify` turn using the default no-preference response | 0 |
| Trace warnings | 0 |

Therefore, the current results do not show the previously suspected failure mode where a multi-hit question is incorrectly written as the default no-preference miss. The persisted hit/miss records are structurally consistent with the runner rules.

## Runtime And Resource Note

The BED Pro continuation exposed a resource-parameter plumbing issue: although the runner CLI accepted `--max-tokens` and `--timeout`, interviewer/evaluator calls still hardcoded `max_tokens=4096`, causing long Pro BED planner JSON outputs to be truncated or returned empty. After the fix, calls use `LLMClient.max_tokens`, so the larger resource limits passed on the command line actually take effect.

This is not an experiment-design change. Prompts, dataset, per-task budget, `num_hypotheses=4`, `num_candidates=4`, EIG computation, and evaluator/stakeholder rules were not changed. The final BED Pro results are completed valid results under the same structured-output constraints.

## Conclusion

The complete experiment supports a clear conclusion: **Aspect-aware is the most effective and stable method in this setup**. It achieves the best total ratio and TKQR in Flash, 27.69% and 0.4266, and the best average task-level ratio in Pro, 29.26%. Under both interviewer models, it clearly outperforms Direct and BED.

Stronger model capability does not automatically improve benchmark performance. Direct Pro only slightly improves over Flash, BED Pro performs substantially worse than BED Flash, and Aspect-aware Pro remains close to Aspect-aware Flash. ReqElicitGym rewards direct hits on hidden implicit requirements, not necessarily the questions that would be most generally valuable in real product discovery; this is especially unfavorable to BED.

Finally, Aspect-aware's Style advantage should be interpreted carefully. The benchmark's Style labels are highly color-like, so explicitly asking about Style or visual preferences produces real score gains here, but this is best understood as a benchmark-facing improvement rather than complete proof of general real-world requirements engineering ability.
