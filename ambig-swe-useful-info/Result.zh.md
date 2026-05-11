# Ambig-SWE Useful-Info 实验结果与分析

> **当前状态：Flash 与 Pro 四组实验均已完成。** 本文基于 `results/` 下的 `direct_flash.jsonl`、`bed_flash.jsonl`、`direct_pro.jsonl`、`bed_pro.jsonl`，以及对应的 `report_flash.txt`、`report_pro.txt`、`per_task_flash.jsonl`、`per_task_pro.jsonl`。后文所有指标、逐任务比较和 trace 分析均来自这些完整结果文件。

## 1. 实验设置概述

本实验在 Ambig-SWE 10-task pilot 上比较两种澄清策略：

- **Direct**：evaluated model 根据 shortened issue 和已有对话直接生成下一条澄清问题。
- **BED**：evaluated model 每轮生成 4 个假设、分歧轴和 4 个候选问题，再由本地 EIG 计算选择信息增益最高的问题。
- **模型档位**：Flash 组使用 `ds/deepseek-v4-flash` 作为 evaluated model；Pro 组使用 `ds/deepseek-v4-pro` 作为 evaluated model。
- **Proxy selector**：四组都使用 `ds/deepseek-v4-pro` 判断问题是否直接命中一条 remaining useful-info item。
- **轮次上限**：每个任务最多 5 轮澄清；若全部 useful-info item 已覆盖则提前停止。
- **BED 配置**：`num_hypotheses=4`，`num_candidates=4`。
- **评估目标**：10 个任务共 29 条 useful-info items，均来自 `ambig_swe_10_clean_with_useful_info.jsonl`。

该实验只评估澄清过程恢复 ordinary issue-reporter-answerable useful information 的效率，不运行 downstream repair agent，也不评估 patch 是否通过测试。Proxy 是严格的 exact-slot 机制：每轮最多返回一条 exact useful-info item；如果问题不能直接映射到某个 remaining item，则回答固定为 `I don't have that information.`。

## 2. 总体结果

完整结果很清楚：**Direct 在 Flash 和 Pro 两档 evaluated model 上都明显优于 BED**。Pro 并没有让 BED 的 EIG 问题选择转化为更高 useful-info recovery；相反，BED Pro 的最终 coverage 只有 `0.220`，低于 BED Flash 的 `0.365`。

| Run | TTR mean | Recovery rate | Useful-info coverage | ATC mean | IDK/task |
|---|---:|---:|---:|---:|---:|
| BED Flash | 5.50 | 0.100 | 0.365 | 4.60 | 3.60 |
| Direct Flash | **4.60** | **0.500** | **0.753** | **4.10** | **1.90** |
| BED Pro | 6.00 | 0.000 | 0.220 | 5.00 | 4.30 |
| Direct Pro | **4.40** | **0.500** | **0.670** | **3.90** | **2.00** |

Direct 的优势不仅体现在最终 coverage，也体现在更早的 coverage curve 上。Pro Direct 第一轮覆盖率最高，而 BED Pro 到第 3 轮后完全停滞。

| Run | Turn 1 | Turn 2 | Turn 3 | Turn 4 | Turn 5 |
|---|---:|---:|---:|---:|---:|
| BED Flash | 0.198 | 0.257 | 0.257 | 0.315 | 0.365 |
| Direct Flash | **0.228** | **0.443** | **0.555** | **0.720** | **0.753** |
| BED Pro | 0.058 | 0.175 | 0.220 | 0.220 | 0.220 |
| Direct Pro | **0.312** | **0.460** | **0.617** | **0.637** | **0.670** |

按任务看，Direct 在 Flash 中 8 胜 2 平，在 Pro 中 7 胜 3 平；BED 没有任何任务超过 Direct。完整恢复任务数同样显示出差距：Flash Direct `5/10`，Flash BED `1/10`，Pro Direct `5/10`，Pro BED `0/10`。BED 的问题不是过早停止：BED Pro 每个任务都跑满 5 轮，但仍然没有任何任务达到 full recovery。

## 3. 按任务结果

| Task | Items | Flash BED | Flash Direct | Pro BED | Pro Direct | 简短观察 |
|---|---:|---:|---:|---:|---:|---|
| `django__django-13112` | 4 | 0.750 | **1.000** | 0.500 | 0.500 | Flash Direct 完整恢复；Pro 两者都只命中 mixed-case AppConfig 和 lowercased lazy reference，未恢复版本差异与 intra-app FK 条件。 |
| `django__django-15375` | 2 | 0.000 | **1.000** | 0.500 | **1.000** | Direct 两档都能恢复 SQL/FROM syntax error；BED Pro 只命中 raw SQL，Flash BED 全 IDK。 |
| `django__django-13297` | 2 | 0.500 | **1.000** | 0.000 | **1.000** | Direct Pro 2 轮完整恢复 URL slug converter 和 sqlite traceback；BED Pro 转向 workaround、第三方包和理想 Django 行为。 |
| `matplotlib__matplotlib-26466` | 3 | 0.000 | **0.667** | 0.000 | 0.000 | 两个 BED 都 0；Pro Direct 也退化为 0，说明 Direct 也可能选错 strict proxy 可计分槽位。 |
| `matplotlib__matplotlib-23314` | 3 | 0.333 | **0.667** | 0.333 | **1.000** | Pro Direct 完整恢复版本、3D axes 条件和 backend；BED 主要停在可见元素描述上。 |
| `scikit-learn__scikit-learn-15100` | 5 | 0.200 | **0.800** | 0.000 | **0.800** | Direct 两档都稳定恢复 NFKD/input/actual/expected；Pro BED 全部问修复策略或底层原因，0 覆盖。 |
| `sympy__sympy-20428` | 5 | 0.200 | **0.400** | 0.200 | **0.400** | 两档结果一致：Direct 命中更多 concrete polynomial/rep 信息，BED 只命中一条状态/触发条件。 |
| `sympy__sympy-15345` | 3 | 0.667 | **1.000** | 0.667 | **1.000** | Direct 两档 3 轮完整恢复 input、actual output、expected output；BED 命中部分输出细节后转向无关问题。 |
| `django__django-11239` | 1 | **1.000** | **1.000** | 0.000 | **1.000** | 简单 config-slot：Flash 两者和 Pro Direct 一轮命中；Pro BED 5 轮全 IDK。 |
| `django__django-13279` | 1 | 0.000 | 0.000 | 0.000 | 0.000 | 四组都没有问到唯一关键 item：`DEFAULT_HASHING_ALGORITHM='sha1'`。 |

逐任务表说明两个现象。第一，Direct 的优势不是单个异常任务造成的，而是在大多数任务上重复出现。第二，Pro evaluated model 并不会自动带来更高 useful-info recovery；在 `matplotlib__matplotlib-26466` 和 `django__django-13112` 上，Pro Direct 反而低于 Flash Direct，说明问题表述与 strict exact-slot proxy 的对齐比模型档位本身更关键。

## 4. Trace 深入分析

### 4.1 BED 问得更多，但命中更少

| Run | Total questions | Useful-info hit turns | IDK | Hit rate |
|---|---:|---:|---:|---:|
| Direct Flash | 41 | 22 | 19 | **53.7%** |
| BED Flash | 46 | 10 | 36 | 21.7% |
| Direct Pro | 39 | 19 | 20 | **48.7%** |
| BED Pro | 50 | 7 | 43 | 14.0% |

BED 尤其在后期失效。Flash BED 第 3 轮为 `0/9`；Pro BED 第 4、5 轮为 `0/10` 和 `0/10`。也就是说，Pro BED 最后 20 个问题没有恢复任何新 useful-info item。

| Run | Turn 1 | Turn 2 | Turn 3 | Turn 4 | Turn 5 |
|---|---:|---:|---:|---:|---:|
| Direct Flash hits/asked | 5/10 | 7/9 | 4/9 | 5/8 | 1/5 |
| BED Flash hits/asked | 5/10 | 2/9 | 0/9 | 2/9 | 1/9 |
| Direct Pro hits/asked | 7/10 | 5/9 | 5/8 | 1/6 | 1/6 |
| BED Pro hits/asked | 2/10 | 3/10 | 2/10 | 0/10 | 0/10 |

这说明 BED 的失败不是 “没有足够轮次”。相反，BED 经常消耗完整 5 轮，但无法把后续问题转化为 proxy 可计分的信息恢复。Pro BED 更极端：每个任务都问满 5 轮，ATC 为 `5.00`，但 full recovery 为 `0/10`。

### 4.2 Direct 更贴近 strict proxy 的可回答槽位

Direct 更常问用户可观察且能直接映射到 useful-info item 的槽位：

- **traceback/error**：完整错误文本、异常类型、异常位置、SQL syntax error。
- **version/config**：Django/Matplotlib/scikit-learn 版本、database `OPTIONS`、AppConfig 或 setting。
- **generated artifact**：generated SQL、URL pattern、wrong internal representation。
- **repro trigger**：slug path converter、3D axes、`ax.annotate` mutable `xy`、NFKD 输入。
- **actual/expected behavior**：实际输出、期望输出、错误 SQL、错误 Mathematica code。

这些问题与 useful-info item 的粒度更一致，因此即使问题本身有时包含多个子槽位，proxy 仍较容易选择其中一条 most directly asked item。例如 Direct Pro 在 `django__django-13297` 中第 1 轮问 URL pattern，第 2 轮问 traceback，正好对应两个 scored items，所以两轮完成。

### 4.3 BED 的 EIG 目标与 exact-slot scoring 错配

BED 的 selected questions 往往围绕 “哪个根因更可能”“修复范围在哪里”“理想修复策略是什么”“是否尝试 workaround”“哪个组件应该修改”“部署拓扑如何” 来区分假设。这些问题在真实 triage 中可能有价值，但在本 benchmark 中不一定对应 ordinary reporter 可以直接提供、且被 useful-info audit 计为 scored item 的具体信息槽位。

典型模式包括：

- **root cause / component ownership**：Pro BED 在 `django__django-13297` 连续询问 Django 哪个部分应修改、理想行为是什么；这些无法映射到 URL slug converter 或 sqlite traceback。
- **fix strategy / desired behavior**：Pro BED 在 `matplotlib__matplotlib-26466` 问是否希望库自动 copy、理想 resolution、修改数组后期望发生什么；scored items 实际是 Matplotlib 版本、Qt5Agg backend、`ax.annotate` mutable `xy` with arrow 的复现条件。
- **workaround / alternative scope**：BED 在多个任务中问 workaround 是否有效、是否换 aggregate function、是否只在某类 polynomial 上发生；这些通常不是 exact useful-info item。
- **deployment topology**：四组在 `django__django-13279` 都被 session backend、rolling upgrade、多实例部署吸走，但唯一 item 是 `DEFAULT_HASHING_ALGORITHM='sha1'`。

因此，本实验中的 BED 失败不应简单归因于 EIG 数值计算错误。更准确的解释是：**当前 BED prompt 生成的假设分歧轴，与 strict proxy 下的 exact-slot useful-info recovery 目标不够一致**。EIG 在优化假设区分度，但评分函数奖励的是直接命中预先审计出的用户可回答信息槽位。

### 4.4 Pro 没有自动修复这种错配

Pro Direct 有一些优势：它在第一轮命中 7 个任务，高于 Flash Direct 的 5 个；在 `django__django-15375` 和 `django__django-13297` 中也更快完整恢复。但 Pro 并不是单调更强：

- `django__django-13112`：Flash Direct 4 轮覆盖 4/4；Pro Direct 只覆盖 2/4，后续追问 AppConfig label、INSTALLED_APPS dotted path、shell inspection，未命中版本差异和 intra-app FK。
- `matplotlib__matplotlib-26466`：Flash Direct 覆盖 2/3；Pro Direct 5 轮全 IDK，问题停在 plotting library、array mutation intent 和 desired behavior。
- `matplotlib__matplotlib-23314`：Pro Direct 明显优于 Flash Direct，完整恢复 3/3，说明 Pro 能在某些任务上更好地定位版本、backend 和复现条件。

这组差异提示：更强模型可能让问题更具体，也可能让问题更像 maintainer diagnosis。对于本实验，关键不是“问题是否聪明”，而是“问题是否直接落在 strict proxy 能返回的 useful-info item 上”。

## 5. 代表性案例

`django__django-11239` 是最清晰的 config-slot 对照。Flash Direct 和 Flash BED 都一轮问到 PostgreSQL dbshell 的 client certificate/key 指定方式，命中 `OPTIONS` 中的 `sslcert` 和 `sslkey`。Pro Direct 也一轮命中。Pro BED 却 5 轮全 IDK，因为问题变成了 dbshell 应使用哪些 SSL 参数、是否应处理 `sslmode`、ORM SSL 配置匹配有多重要，而不是直接问 certificate/key 对应的 database setting keys。

`django__django-15375` 展示 Direct 如何命中 generated SQL/error slot。Direct Pro 第 1 轮恢复 `SELECT FROM (SELECT ...) subquery`，第 3 轮恢复 `OperationalError near FROM`，3 轮完成。BED Pro 只在第 2 轮命中 raw SQL，其余反复询问 `default` 参数应如何解释。Flash BED 则 5 轮全 IDK，集中在 aggregate function 种类、Django 4.0.1 是否新问题、是否尝试其他 aggregate、minimal reproducer。

`django__django-13297` 中，Direct Pro 两轮完整恢复：第 1 轮问 URL pattern 和 keyword argument type，命中 slug path converter；第 2 轮问 view code 与 traceback，命中 sqlite binding error。BED Pro 0 覆盖，问题转向 workaround 放在哪里、是否有第三方包、Django 哪个组件应改变、理想行为是什么。

`matplotlib__matplotlib-26466` 是 BED 与 Direct 都可能失败的例子。两个 BED 都 0 覆盖，Pro BED 更明显地问自动 copy、是否意外 side effect、ideal resolution、修改数组后的期望结果。Flash Direct 至少命中 annotate 复现条件和版本；Pro Direct 也退化为 0，说明 Direct 的优势是经验事实而不是保证。

`scikit-learn__scikit-learn-15100` 是 Direct 稳定成功、BED Pro 明显错配的例子。Direct Flash 和 Direct Pro 都恢复 `0.800` coverage，围绕 Unicode normalization、NFKD input、actual output 和 expected output 连续追问。Pro BED 5 轮全 IDK，主要问修复应在 `strip_accents_unicode` 还是 `CountVectorizer`、应采用什么 Unicode 策略、底层原因是什么、是否只影响某些 combining marks。

`django__django-13279` 是四组共同失败案例。唯一 useful-info item 是 `DEFAULT_HASHING_ALGORITHM` 被设置为 `'sha1'`。四组都没有直接问 hashing algorithm setting，而是转向 session backend、serializer、decode error、deployment、rolling upgrade 或 user impact。这说明 useful-info target 本身有时非常窄，若初始问题 framing 没有把模型引到该 setting，5 轮内很难恢复。

## 6. 结论与有效性威胁

在当前 10-task Ambig-SWE useful-info recovery benchmark 中，**Direct 是更稳健的 baseline**。它在 Flash 和 Pro 两档都以更低 ATC、更低 IDK、更高 hit rate 和更高 useful-info coverage 超过 BED。BED 的 structured hypotheses 和 EIG ranking 没有带来净收益，反而经常把问题预算消耗在 strict proxy 不计分的根因、范围、workaround 和修复策略问题上。

这个结论需要限定在当前设置内。它不证明 BED 思路在所有澄清任务中无效，也不证明 Direct 在真实软件修复中一定更好。更保守的表述是：在这组 10-task pilot、29 useful-info items、当前 BED prompt、Pro strict proxy、`max_turns=5` 和 exact-slot coverage 规则下，BED 与评估目标存在明显错配。

主要限制如下：

- 数据集只有 10 个任务，仍是 pilot 规模。
- useful-info items 由 LLM 生成并人工修订，可能仍有抽取偏差。
- proxy selector 是 LLM 模拟用户，不是真实 issue reporter。
- coverage 判断很严格：只有 proxy 选中 remaining item，且系统返回 exact item text，才计入覆盖。
- 每轮最多恢复一条 item，因此 broad question 不会因一次性覆盖多个信息点而获益。
- 实验不运行 downstream coding agent，因此不能直接推断 patch success 或测试通过率。
- Pro 与 Flash 的差异还受具体问题表述和 proxy 对齐影响，不能简单解读为模型能力排序。
