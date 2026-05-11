# ClarEval 完整实验结果与 Trace 分析

> **当前状态：四组实验均已完成。** `direct_flash`、`bed_flash`、`direct_pro`、`bed_pro` 均为 **30/30** 条唯一任务记录；未发现重复或缺失任务。本文所有结论均基于完整 Flash + Pro 实验结果。

## 1. 实验设置

本实验在 `clareval_multi_turn_30_clean.jsonl` 的 30 题 ClarEval 子集上比较两种澄清策略：

- **Direct**：被评估模型直接决定继续提问，或停止并生成最终 Python 代码。
- **BED**：被评估模型生成 4 个需求假设和 4 个候选澄清问题，本地 runner 根据期望信息增益选择问题。

共同设置如下：

| 项目 | 设置 |
|---|---|
| 数据集 | `clareval_multi_turn_30_clean.jsonl` |
| 任务数 | 30 |
| 最大 agent 行动轮次 | `max-turns = 6` |
| 用户模拟器 | `ds/deepseek-v4-flash` |
| 最终评估器 | `ds/deepseek-v4-pro` |
| Flash 被评估模型 | `ds/deepseek-v4-flash` |
| Pro 被评估模型 | `ds/deepseek-v4-pro` |
| BED 假设数 | `num-hypotheses = 4` |
| BED 候选问题数 | `num-candidates = 4` |

主要结果来源：

- `results/direct_flash_report.txt`
- `results/bed_flash_report.txt`
- `results/direct_pro_report.txt`
- `results/bed_pro_report.txt`
- `results/direct_flash_results.jsonl`
- `results/bed_flash_results.jsonl`
- `results/direct_pro_results.jsonl`
- `results/bed_pro_results.jsonl`

## 2. 主要结果

### 2.1 总体结果

| 方法 | n | Completion | Efficiency | ATC | Sim Answer Rate | Unresolved |
|---|---:|---:|---:|---:|---:|---:|
| Direct Flash | 30 | **0.644** | **1.582** | **2.600** | **0.906** | **0.133** |
| BED Flash | 30 | 0.494 | 1.003 | 3.600 | 0.697 | 0.300 |
| Direct Pro | 30 | **0.705** | **1.772** | **2.067** | **0.883** | **0.067** |
| BED Pro | 30 | 0.662 | 1.255 | 2.967 | 0.735 | 0.133 |

完整结果显示，Direct 在 Flash 和 Pro 两个模型强度下都保持总体领先。Direct Pro 是四组中 completion 和 efficiency 最高、unresolved 最低的设置；BED Pro 相比 BED Flash 有明显改善，但仍未超过 Direct Pro。

模型能力提升主要缩小了 BED 与 Direct 的差距，而不是改变排序。Flash 下 BED 相对 Direct 的平均 completion 差值为 **-0.150**；Pro 下收窄为 **-0.043**。这说明 Pro 的更强推理能力能够缓解 BED 的过度追问和未解决问题，但没有消除 BED 在当前候选问题生成方式下的信息效率损失。

### 2.2 按任务组统计

| 任务组 | 方法 | n | Completion | Efficiency | ATC | Sim Answer Rate | Unresolved |
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

最主要的 BED 弱点仍然来自 **Ambiguous Terms / easy**。Flash 下，BED completion 只有 **0.285**，远低于 Direct 的 **0.652**，且 unresolved 达到 **0.600**。Pro 下 BED 在该组提升到 **0.572**，但 Direct Pro 也提升到 **0.735**，差距仍然明显。

BED 唯一稳定占优的任务组是 **Missing Premises / hard**。Flash 下 BED completion 为 **0.772**，略高于 Direct 的 **0.747**；Pro 下 BED 为 **0.755**，也略高于 Direct 的 **0.722**。不过在两种模型强度下，Direct 的 efficiency 都更高，说明 BED 的收益来自更多追问和更高交互成本，而不是更高的信息利用效率。

### 2.3 逐任务配对结果

以每个任务的 completion 差值 `BED - Direct` 计算：

| 模型强度 | BED 优于 Direct | 持平 | BED 落后 Direct | 平均差值 |
|---|---:|---:|---:|---:|
| Flash | 5 | 15 | 10 | -0.150 |
| Pro | 8 | 14 | 8 | -0.043 |

Flash 结果显示 BED 输多赢少，且平均差值较大。Pro 结果更接近：BED 胜负各 8 题，平均差距缩小到 **-0.043**。这说明 BED 并非完全无效；当模型足够强时，它有更多机会把结构化假设空间转化为可执行代码。但 Direct 仍然是更稳定的基线，因为它用更少轮次取得了更高总体完成率和效率。

## 3. Trace 深入分析

### 3.1 BED 问得更多，但有效信息率更低

| 方法 | 总提问数 | 有效模拟器回答 | `irrelevant or unknown` | Unknown Rate |
|---|---:|---:|---:|---:|
| Direct Flash | 78 | 66 | 12 | 0.154 |
| BED Flash | 108 | 65 | 43 | 0.398 |
| Direct Pro | 62 | 49 | 13 | 0.210 |
| BED Pro | 89 | 55 | 34 | 0.382 |

Flash 下，BED 比 Direct 多问 **30** 次，却少得到 **1** 条有效回答。Pro 下，BED 比 Direct 多问 **27** 次，多得到 **6** 条有效回答，但 unknown 也多 **21** 次。也就是说，Pro 让 BED 的额外提问更有机会转化为信息，但大量额外交互仍然落在模拟器无法用 gold premise 回答的问题上。

这解释了主结果表中的核心现象：BED 的 ATC 更高，但 completion 和 efficiency 未能相应提高。当前 BED 的瓶颈不是本地 EIG 数值计算本身，而是候选问题生成分布经常偏向“内部看似能区分假设、但不容易命中 gold premise”的问题。

### 3.2 问题形态：BED 更偏封闭式与边界情况

| 方法或候选池 | Open WH Questions | Yes/No or Closed Questions | Other |
|---|---:|---:|---:|
| Direct Flash 实际提问 | **62.8%** | 26.9% | 10.3% |
| BED Flash 实际提问 | 38.0% | **57.4%** | 4.6% |
| BED Flash 全部候选问题 | 36.1% | **60.0%** | 3.9% |
| Direct Pro 实际提问 | **58.1%** | 37.1% | 4.8% |
| BED Pro 实际提问 | 41.6% | **51.7%** | 6.7% |
| BED Pro 全部候选问题 | 34.8% | **55.3%** | 9.8% |

Direct 更常问开放式问题，例如输入类型、输出形式、整体转换逻辑和约束。这类问题与用户模拟器的机制更匹配，因为模拟器只能复制一条最接近的 `ground_truth_missing_premises` 或回答 `irrelevant or unknown`。

BED 的候选池和最终选择都更偏封闭式、是非式或边界情况问题，例如是否需要处理某类异常输入、某个符号如何解释、是否存在阈值或特殊 case。这些问题在真实需求访谈中可能有价值，但在本实验的模拟器约束下，只有当问题刚好映射到某条 gold premise 时才会得到有效回答。

### 3.3 后期追问仍然危险

| BED 提问位置 | Flash Unknown / Total | Flash Unknown Rate | Pro Unknown / Total | Pro Unknown Rate |
|---:|---:|---:|---:|---:|
| 1 | 6 / 30 | 0.200 | 11 / 30 | 0.367 |
| 2 | 5 / 25 | 0.200 | 7 / 26 | 0.269 |
| 3 | 11 / 21 | 0.524 | 6 / 13 | 0.462 |
| 4 | 6 / 14 | 0.429 | 5 / 9 | 0.556 |
| 5 | 8 / 9 | **0.889** | 3 / 7 | **0.429** |
| 6 | 7 / 9 | **0.778** | 2 / 4 | **0.500** |

BED Flash 在第 5、6 次提问时几乎已经进入“反复追问不可回答细节”的状态，unknown rate 分别达到 **0.889** 和 **0.778**。在 `max-turns = 6` 下，这非常致命：如果第六轮仍是提问，就会被记为 unresolved，生成代码为空，completion 为 0。

BED Pro 的后期样本明显更少，说明 Pro 更常能提前停止并生成代码；但一旦进入第 4 到第 6 问，unknown rate 仍然偏高。这表明模型能力提升缓解了过度追问，却没有根除 BED 候选问题偏边界、偏封闭式的问题。

### 3.4 代表案例

#### `task4_ambiguous_terms`

Flash 中，Direct 通过三次开放式问题恢复了核心信息：返回条件、初始余额、整数列表表示存取款操作，最终 completion 为 **1.0**。BED Flash 前两问也得到关键语义，但随后转向追问整数符号、正负数如何解释等细节；模拟器只能重复已给出的输入 premise 或返回 unknown，第六轮仍在提问，最终 unresolved，completion 为 **0.0**。

Pro 中，这一失败模式被明显缓解。Direct Pro 两问后生成代码，BED Pro 也在两问后停止并生成代码，二者 completion 均为 **1.0**。这说明 Pro 能更好地从不完整但足够的回答中形成实现，而不是继续把轮次花在符号边界上。

#### `task5_ambiguous_terms`

BED Flash 在拿到“输入为 float 列表”和 “Mean Absolute Deviation 公式”后，继续追问阈值、是否基于 MAD 做条件判断、阈值是否作为参数传入。这些都不是 gold premise，导致连续 unknown，并在第六轮仍未生成代码，completion 为 **0.0**。

BED Pro 仍然出现了类似的前期漂移：它先问空字符串、分支判断、固定阈值、返回值是否为布尔值等不相关问题。但 Pro 最终在第 4、5 问得到返回类型和输入类型后生成代码，completion 达到 **1.0**。这展示了 Pro 对 BED 的容错能力：即使候选问题质量不稳定，模型仍可能在有限信息下收束到正确实现。

#### `task9_ambiguous_terms`

Direct Flash 和 Direct Pro 都在第一问得到“返回整数列表的 sum 和 product 组成的 tuple”后生成代码，completion 均为 **1.0**。BED Flash 第一问得到输出 tuple，第二问得到空列表 sum 为 0，随后追问非整数元素、字符串输入、是否保证全为整数等非 gold edge cases，最终 unresolved，completion 为 **0.0**。

BED Pro 仍然追问了非整数、字符串和布尔值等边界问题，但第 5 问得到空列表 product 为 1 后及时生成代码，completion 为 **1.0**。这再次说明 Pro 能减少“追问到死”的失败，但 BED 的问题选择仍然比 Direct 更绕、更耗轮次。

#### `task7_ambiguous_terms`

这是 BED Pro 仍然失败的代表。Direct Pro 通过四次开放式问题依次恢复任务目的、输出含义、输入格式和示例，最终 completion 为 **0.8**。BED Pro 则先问是否修改输入，随后得到输出类型和输入格式，但又转向未平衡括号如何处理等非 gold 问题，最终第六轮仍未生成代码，unresolved，completion 为 **0.0**。

这个案例说明，即便使用 Pro，BED 一旦把后期问题预算投入到 evaluator 不奖励、simulator 也无法回答的边界条件上，仍会重现 Flash 中的核心失败机制。

#### `task10_missing_premises`

BED Flash 在该任务中明显优于 Direct Flash。Direct Flash 反复追问 rolling maximum 的窗口大小和边界行为，第六轮仍未生成代码，completion 为 **0.0**。BED Flash 两问得到输入为整数列表、输出为 rolling maximum 列表后及时生成代码，completion 为 **0.75**。

但在 Pro 下，Direct Pro 也能两问后解决该任务，completion 为 **1.0**，BED Pro 同样为 **1.0**。这说明 BED 的优势主要出现在弱模型或“从零重建需求”的场景；当 Direct 模型足够强时，它也能从开放式澄清中快速形成实现。

### 3.5 常见失败前提

| 失败前提类型 | Direct Flash | BED Flash | Direct Pro | BED Pro |
|---|---:|---:|---:|---:|
| 函数命名 | 15 | 15 | 11 | 13 |
| 输入 / 参数 | 20 | 33 | 19 | 20 |
| 返回值 / 输出 | 1 | 2 | 1 | 2 |
| docstring / examples | 4 | 4 | 3 | 4 |
| 其他行为 / 约束 | 0 | 1 | 0 | 1 |

函数命名和 docstring/examples 是两种方法共同的稳定盲区。模型通常优先澄清行为、输入和输出，而很少主动询问函数应该叫什么、是否需要示例文档；即使生成了可运行代码，也常因这些接口外观要求不匹配而失分。

BED 相比 Direct 更容易漏掉输入/参数类前提，尤其在 Flash 下最明显。这与 Trace 中的高 unknown rate 一致：BED 把更多轮次花在阈值、异常类型、非整数元素、未平衡括号等边界问题上，反而没有稳定补齐基础接口信息。

## 4. 结论

在当前 ClarEval 30 题、当前 prompt、Flash simulator、Pro evaluator、`max-turns = 6` 设置下，**Direct 是更强、更稳定、更高效的基线**。它在 Flash 和 Pro 两个模型强度下都取得更高 overall completion、更高 efficiency、更低 ATC 和更低 unresolved。

BED 的结构化假设与 EIG 选择并非没有价值。它在 Missing Premises / hard 中稳定取得略高 completion，并且 Pro 模型显著缩小了 BED 与 Direct 的总体差距。然而，BED 的候选问题分布仍偏封闭式和边界情况，导致它经常问到模拟器无法用 gold premise 回答的问题，进而降低效率并增加 unresolved 风险。

因此，本文结论应限定为：**在这组 ClarEval 30 题和当前 BED prompt/候选生成机制下，BED 没有超过 Direct；这不能泛化为 BED 式澄清在所有任务上无效。** 更合理的后续方向是改进 BED 候选问题生成，使候选问题优先覆盖基础接口和核心语义，再追问边界条件。

## 5. 有效性威胁

- 数据集只有 30 题，且三类任务各 10 题；结果适合解释当前实验，不应过度外推。
- 用户模拟器只能复制一条 gold premise 或返回 `irrelevant or unknown`，这提高了可控性，但会惩罚真实对话中可能有价值的边界问题。
- 最终评估由 `ds/deepseek-v4-pro` 单次判断代码是否覆盖 premise，仍可能受 LLM judge 偏差影响。
- BED 的表现与当前 prompt 中“生成 4 个候选问题并估计 answer ID 分布”的格式强相关；改进候选问题生成策略后，结论可能变化。
