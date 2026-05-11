# ReqElicitGym 完整实验结果与 Trace 分析

> **完成状态说明：计划内 Flash 与 Pro 实验均已完成。** 当前完整结果文件包括 `direct_flash`、`bed_flash`、`aspect_aware_flash`、`direct_pro`、`bed_pro` 和 `aspect_aware_pro` 六组运行，每组均覆盖 `ReqElicitGym_10.jsonl` 的 10 个任务、65 条隐藏隐式需求。BED Pro 最终运行前修正了 runner 的资源参数接线，使 `--max-tokens` / `--timeout` 真正传入 interviewer 与 evaluator 调用；这只影响 Pro 运行的调用资源上限，不改变 prompt、数据集、任务预算、假设数、候选数、EIG 逻辑或 evaluator 判定规则。

## 实验设置概述

本实验使用 `ReqElicitGym_10.jsonl`，包含 10 个应用类别各 1 个任务，共 65 条隐藏隐式需求。其中 Interaction 24 条、Content 20 条、Style 21 条。三种方法共享同一套 LLM-backed episode loop：interviewer 每轮提出 1 个澄清问题，`ds/deepseek-v4-pro` 作为 evaluator/stakeholder 判断该问题是否直接命中一条尚未获得的隐藏需求，并返回模拟用户回答。

三种方法分别在 `ds/deepseek-v4-flash` 与 `ds/deepseek-v4-pro` 上运行。Evaluator / Stakeholder 始终使用 `ds/deepseek-v4-pro`。

- **Direct**：直接澄清提问 baseline，不显式维护方面或假设。
- **BED**：维护 rolling belief state，生成候选问题并用本地 EIG 选择问题。
- **Aspect-aware**：显式要求模型在 Interaction / Content / Style 三类需求方面之间选择并提问。

每个任务的最大提问轮数等于该任务隐藏需求数量。该预算只由本地 runner 使用，不进入 LLM prompt。

## 总体结果

| 运行 | 命中需求 | 总体命中率 | 任务平均命中率 | 平均 TKQR | 平均 ORA | 平均轮数 |
|---|---:|---:|---:|---:|---:|---:|
| Direct Flash | 4/65 | 6.15% | 8.76% | 0.2021 | 0.4488 | 2.40 |
| BED Flash | 11/65 | 16.92% | 18.53% | 0.1919 | 0.9412 | 5.80 |
| Aspect-aware Flash | 18/65 | 27.69% | 28.34% | 0.4266 | 0.7698 | 4.40 |
| Direct Pro | 6/65 | 9.23% | 12.76% | 0.2037 | 0.4683 | 2.40 |
| BED Pro | 7/65 | 10.77% | 9.86% | 0.1223 | 0.6375 | 3.50 |
| Aspect-aware Pro | 17/65 | 26.15% | 29.26% | 0.3949 | 0.7072 | 4.10 |

Aspect-aware 在 Flash 和 Pro 两个模型设置下都是最强方法。Flash 中 Aspect-aware 命中 18/65，是六组中最高总体命中率与最高 TKQR；Pro 中 Aspect-aware 命中 17/65，任务平均命中率 29.26%，是六组中最高的任务平均命中率。

Pro 并没有带来一致提升。Direct Pro 相比 Direct Flash 略有提升：命中从 4 条增至 6 条，平均轮数仍为 2.40。BED Pro 相比 BED Flash 明显下降：命中从 11 条降至 7 条，平均轮数从 5.80 降至 3.50，ORA 也从 0.9412 降至 0.6375。Aspect-aware Pro 与 Flash 接近但略低：总命中 17 vs 18，平均轮数 4.10 vs 4.40。

## Flash 与 Pro 对比

| 方法 | Flash 命中 | Pro 命中 | 变化 | Flash 平均轮数 | Pro 平均轮数 | 主要观察 |
|---|---:|---:|---:|---:|---:|---|
| Direct | 4/65 | 6/65 | +2 | 2.40 | 2.40 | Pro 稍好，但仍早停且不命中 Style |
| BED | 11/65 | 7/65 | -4 | 5.80 | 3.50 | Pro 更早 finish，EIG 选择与 benchmark 命中更不一致 |
| Aspect-aware | 18/65 | 17/65 | -1 | 4.40 | 4.10 | 两个模型都稳定领先，Style 优势保持 |

从模型差异看，Pro 并不自动转化为更好的需求获取表现。特别是 BED，Pro 的 planner 往往提出更高层的产品范围问题并更早结束，反而减少了命中隐藏需求的机会。Aspect-aware 的表现最稳，说明显式方面提示比单纯更强的模型能力更能影响该 benchmark 中的提问方向。

## 按方面结果

| 运行 | Interaction | Content | Style |
|---|---:|---:|---:|
| Direct Flash | 2/24 (8.33%) | 2/20 (10.00%) | 0/21 (0.00%) |
| BED Flash | 7/24 (29.17%) | 4/20 (20.00%) | 0/21 (0.00%) |
| Aspect-aware Flash | 9/24 (37.50%) | 5/20 (25.00%) | 4/21 (19.05%) |
| Direct Pro | 3/24 (12.50%) | 3/20 (15.00%) | 0/21 (0.00%) |
| BED Pro | 2/24 (8.33%) | 5/20 (25.00%) | 0/21 (0.00%) |
| Aspect-aware Pro | 9/24 (37.50%) | 4/20 (20.00%) | 4/21 (19.05%) |

Style 是最能区分方法的方面。Direct 与 BED 在 Flash 和 Pro 中都没有命中任何 Style 需求；Aspect-aware 在两个模型设置下都命中 4/21 条 Style 需求。Interaction 上，Aspect-aware Flash 与 Pro 都达到 9/24；Content 上，BED Pro 与 Aspect-aware Flash 分别有 5/20，略高于其他运行。

这一结果与数据集标注模式强相关。本子集的 Style 需求主要是背景色、组件色、界面元素颜色等 color-like 偏好。Aspect-aware 通过显式提醒模型考虑 Style，更容易把问题问到颜色/视觉偏好上；这是明确的 benchmark 收益，但不应被过度解释为真实项目中全面的视觉需求澄清能力。

## 按任务结果

| 任务 | 隐式需求数 | Direct Flash | BED Flash | Aspect Flash | Direct Pro | BED Pro | Aspect Pro |
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

任务级结果显示，Aspect-aware 的优势不是来自单个任务的异常值，而是跨任务较稳定的覆盖。Aspect-aware Pro 在 Poker、Online Polling、Real Estate、Driver Recruitment 等 Flash 中较难的任务上有提升；但在 customer service、Email、Course Enrollment、Medical Journal 上不如 Aspect-aware Flash。BED Pro 在 customer service 和 Email 上有一定收益，但在 Real Estate、Driver Recruitment、Course Enrollment、Medical Journal 上早停并 0 命中。

## Trace 深入分析

### Direct

Direct Flash 与 Direct Pro 的行为形态很接近：两者都提出 24 个实际问题，并在 9/10 个任务中主动 finish。Flash 为 4 个 clarify、20 个 probe；Pro 为 6 个 clarify、18 个 probe。Pro 稍微提高了 Interaction 与 Content 命中：Interaction 从 2/24 到 3/24，Content 从 2/20 到 3/20，但 Style 仍为 0/21。

Direct 的主要失败模式仍是早停和 benchmark mismatch。它经常问出真实产品中合理的问题，例如真钱/虚拟币、账户管理、用户角色、技术实现、页面栏目、邮件工作流等，但这些问题没有直接询问 ReqElicitGym 的隐藏需求，因此被 evaluator 判为 probe。Pro 并没有改变这种结构性问题；它只是偶尔把问题问得更接近隐藏标签。

Direct 的低平均轮数不是高效率，而是过早结束。多个任务在 0 命中或低命中后 finish，尤其是 customer service、Email、Driver Recruitment、Course Enrollment 等需求数较多的任务。这解释了为什么 Direct 的 ORA 在 Flash 和 Pro 中都偏低。

### BED

BED Flash 与 BED Pro 的差异很明显。BED Flash 提出 58 个实际问题，11 个 clarify、47 个 probe，只主动 finish 2 次，平均轮数 5.80，ORA 0.9412。BED Pro 只提出 35 个实际问题，7 个 clarify、28 个 probe，主动 finish 8 次，平均轮数 3.50，ORA 0.6375。

BED Pro 的下降首先来自 trace 层面的早停。Pro planner 常在少数几轮后判断可见对话已经足够，例如 Driver Recruitment、Course Enrollment、Medical Journal 都只问 2 轮并 0 命中后 finish。相比之下，BED Flash 更常接近用满预算，因此虽然 probe 多，但仍有更多机会碰到 Interaction / Content 隐藏需求。

EIG trace 进一步说明 Pro BED 的问题。BED Flash 中 clarify 问题的平均 selected EIG 为 0.5099，高于 probe 的 0.4087，说明 EIG 与 benchmark 命中有一定正相关。但 BED Pro 中 clarify 的平均 selected EIG 为 0.7369，低于 probe 的 0.8018；Pro 生成的高 EIG 问题更常是“区分完整产品假设”的高层问题，而不是直接询问隐藏需求。例如它偏向询问目标用户、账户角色、平台边界、是否支持私有房间、集成工具、额外功能等。

因此，BED Pro 的低分不应被简单解释为 EIG 思路无效，而更像是两个目标之间的错位：BED 优化的是可见语境下的假设区分度，ReqElicitGym 奖励的是直接命中隐藏标注。Pro 模型更会构造宏观产品假设，反而可能放大这种错位。

### Aspect-aware

Aspect-aware 是两种模型中最稳定的方法。Flash 提出 44 个实际问题，18 个 clarify、26 个 probe，7 次 finish；Pro 提出 41 个实际问题，17 个 clarify、24 个 probe，6 次 finish。两者问题数、命中数和平均轮数都很接近。

选中方面的 trace 分布如下：

| 运行 | 选中 Content | 选中 Interaction | 选中 Style |
|---|---:|---:|---:|
| Aspect-aware Flash | 16 问 / 6 命中 | 18 问 / 8 命中 | 10 问 / 4 命中 |
| Aspect-aware Pro | 17 问 / 5 命中 | 17 问 / 7 命中 | 7 问 / 5 命中 |

注意这里的“选中方面命中数”按模型选择的 aspect 统计；它不一定等同于被命中的隐藏需求真实方面。按真实隐藏需求方面统计，Aspect-aware Flash 与 Pro 都命中 4 条 Style 需求。两组运行都存在少量跨方面命中：Flash 18 个命中中 15 个 selected aspect 与真实需求方面一致，Pro 17 个命中中 15 个一致。例如 Content 问题可能命中 Interaction 需求，Style 问题也可能命中 Interaction 需求。这说明 aspect 是有效的提问脚手架，而不是 evaluator 的硬标签。

Aspect-aware 的优势来自显式覆盖 Interaction / Content / Style。尤其是 Style，Direct 和 BED 几乎不会主动把澄清预算花在颜色偏好上，而 Aspect-aware 会问到视觉风格、布局、颜色方案、整体 look and feel 等问题。它仍会失败：当问题只是泛泛询问“visual style or layout preferences”，而没有直接触及背景色或组件色时，evaluator 可能仍判为 miss。

## Trace 完整性检查

我对六组结果的所有 evaluator turn 做了结构一致性检查：

| 检查项 | 结果 |
|---|---:|
| evaluator 返回多个 requirement ids | 0 |
| `probe` turn 但 ids 非空 | 0 |
| `is_relevant=true` 但 ids 为空 | 0 |
| `clarify` turn 使用默认 no-preference 回复 | 0 |
| trace warning | 0 |

因此，当前结果中没有发现“多条命中被错误写成默认未命中回复”的落盘异常。所有命中/未命中记录在结构上与 runner 规则一致。

## 运行与资源限制说明

BED Pro 初次续跑时暴露出一个资源参数接线问题：runner CLI 虽然增加了 `--max-tokens` 和 `--timeout`，但 interviewer/evaluator 内部调用仍硬编码 `max_tokens=4096`，导致 Pro BED planner 的长 JSON 输出被截断或空返回。修正后，调用使用 `LLMClient.max_tokens`，使命令行传入的较大资源上限真正生效。

这个修正不改变实验设计：没有改 prompt，没有改数据集，没有改每题预算，没有改 `num_hypotheses=4`、`num_candidates=4`，没有改 EIG 计算，也没有改 evaluator/stakeholder 判定规则。最终 BED Pro 结果是在完整结构化输出约束下跑完的有效结果。

## 结论

完整实验支持一个清晰结论：**Aspect-aware 是本实验中最有效、最稳定的方法**。它在 Flash 中取得最高总体命中率 27.69% 和最高 TKQR 0.4266，在 Pro 中取得最高任务平均命中率 29.26%，并且在两个模型设置下都显著领先 Direct 和 BED。

模型能力提升并不自动提高 benchmark 表现。Direct Pro 相比 Flash 只小幅提升，BED Pro 反而明显下降，Aspect-aware Pro 与 Flash 接近。ReqElicitGym 奖励的是直接命中隐藏隐式需求，而不是提出真实项目中泛化价值最高的问题；这对 BED 尤其不利。

最后，Aspect-aware 的 Style 优势需要谨慎解释。本 benchmark 的 Style 标注高度 color-like，因此显式询问 Style 或视觉偏好能带来真实分数提升，但这更应被视为 benchmark-facing improvement，而不是对真实世界需求工程能力的完整证明。
