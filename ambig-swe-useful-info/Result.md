# Ambig-SWE Useful-Info Experiment Results and Analysis

> **Current status: all four Flash and Pro runs are complete.** This document is based on `direct_flash.jsonl`, `bed_flash.jsonl`, `direct_pro.jsonl`, `bed_pro.jsonl`, plus the corresponding `report_flash.txt`, `report_pro.txt`, `per_task_flash.jsonl`, and `per_task_pro.jsonl` files under `results/`. All metrics, per-task comparisons, and trace analysis below come from these completed result files.

## 1. Experiment Setup

This experiment compares two clarification strategies on the Ambig-SWE 10-task pilot:

- **Direct**: the evaluated model directly generates the next clarification question from the shortened issue and dialogue so far.
- **BED**: each turn, the evaluated model generates 4 hypotheses, disagreement axes, and 4 candidate questions; local EIG computation selects the highest-information-gain question.
- **Model tiers**: the Flash runs use `ds/deepseek-v4-flash` as the evaluated model; the Pro runs use `ds/deepseek-v4-pro` as the evaluated model.
- **Proxy selector**: all four runs use `ds/deepseek-v4-pro` to decide whether the question directly elicits one remaining useful-info item.
- **Turn budget**: each task has at most 5 clarification turns and stops early after full coverage.
- **BED configuration**: `num_hypotheses=4`, `num_candidates=4`.
- **Evaluation target**: 29 useful-info items across 10 tasks, all read from `ambig_swe_10_clean_with_useful_info.jsonl`.

The experiment evaluates only clarification behavior for recovering ordinary issue-reporter-answerable useful information. It does not run a downstream repair agent or evaluate whether patches pass tests. The proxy is a strict exact-slot mechanism: each turn can return at most one exact useful-info item; if the question does not directly map to a remaining item, the answer is fixed as `I don't have that information.`

## 2. Overall Results

The complete result is clear: **Direct substantially outperforms BED under both Flash and Pro evaluated models**. Pro does not make BED's EIG-based question selection translate into higher useful-info recovery. Instead, BED Pro ends at only `0.220` coverage, below BED Flash's `0.365`.

| Run | TTR mean | Recovery rate | Useful-info coverage | ATC mean | IDK/task |
|---|---:|---:|---:|---:|---:|
| BED Flash | 5.50 | 0.100 | 0.365 | 4.60 | 3.60 |
| Direct Flash | **4.60** | **0.500** | **0.753** | **4.10** | **1.90** |
| BED Pro | 6.00 | 0.000 | 0.220 | 5.00 | 4.30 |
| Direct Pro | **4.40** | **0.500** | **0.670** | **3.90** | **2.00** |

Direct's advantage appears not only in final coverage, but also in the earlier coverage curve. Pro Direct has the highest turn-1 coverage, while BED Pro completely stalls after turn 3.

| Run | Turn 1 | Turn 2 | Turn 3 | Turn 4 | Turn 5 |
|---|---:|---:|---:|---:|---:|
| BED Flash | 0.198 | 0.257 | 0.257 | 0.315 | 0.365 |
| Direct Flash | **0.228** | **0.443** | **0.555** | **0.720** | **0.753** |
| BED Pro | 0.058 | 0.175 | 0.220 | 0.220 | 0.220 |
| Direct Pro | **0.312** | **0.460** | **0.617** | **0.637** | **0.670** |

At the task level, Direct wins 8 and ties 2 in Flash, and wins 7 and ties 3 in Pro. BED never beats Direct on any task. Full recovery shows the same gap: Flash Direct `5/10`, Flash BED `1/10`, Pro Direct `5/10`, and Pro BED `0/10`. BED's lower coverage is not caused by early stopping: BED Pro runs all 5 turns on every task, yet never reaches full recovery.

## 3. Per-Task Results

| Task | Items | Flash BED | Flash Direct | Pro BED | Pro Direct | Short observation |
|---|---:|---:|---:|---:|---:|---|
| `django__django-13112` | 4 | 0.750 | **1.000** | 0.500 | 0.500 | Flash Direct fully recovers the task; both Pro runs only hit mixed-case AppConfig and the lowercased lazy reference, missing the version difference and intra-app FK condition. |
| `django__django-15375` | 2 | 0.000 | **1.000** | 0.500 | **1.000** | Both Direct runs recover the SQL/FROM syntax error; BED Pro only hits raw SQL, while Flash BED gets IDK in all turns. |
| `django__django-13297` | 2 | 0.500 | **1.000** | 0.000 | **1.000** | Direct Pro fully recovers the URL slug converter and sqlite traceback in 2 turns; BED Pro drifts to workaround location, third-party packages, and ideal Django behavior. |
| `matplotlib__matplotlib-26466` | 3 | 0.000 | **0.667** | 0.000 | 0.000 | Both BED runs get 0 coverage; Pro Direct also degrades to 0, showing Direct can also choose questions that miss the strict proxy slots. |
| `matplotlib__matplotlib-23314` | 3 | 0.333 | **0.667** | 0.333 | **1.000** | Pro Direct fully recovers version, 3D axes condition, and backend; BED mostly stays on visible-element descriptions. |
| `scikit-learn__scikit-learn-15100` | 5 | 0.200 | **0.800** | 0.000 | **0.800** | Direct is stable across tiers on NFKD/input/actual/expected output; Pro BED asks only about fix strategy or root cause and gets 0 coverage. |
| `sympy__sympy-20428` | 5 | 0.200 | **0.400** | 0.200 | **0.400** | Both tiers show the same pattern: Direct hits more concrete polynomial/rep information, while BED only recovers one state/trigger item. |
| `sympy__sympy-15345` | 3 | 0.667 | **1.000** | 0.667 | **1.000** | Both Direct runs fully recover input, actual output, and expected output in 3 turns; BED hits part of the output detail and then drifts. |
| `django__django-11239` | 1 | **1.000** | **1.000** | 0.000 | **1.000** | A simple config-slot case: both Flash runs and Pro Direct hit in one turn; Pro BED gets IDK in all 5 turns. |
| `django__django-13279` | 1 | 0.000 | 0.000 | 0.000 | 0.000 | None of the four runs asks for the single key item: `DEFAULT_HASHING_ALGORITHM='sha1'`. |

The per-task table shows two things. First, Direct's advantage is not driven by one outlier; it repeats across most tasks. Second, a Pro evaluated model does not automatically improve useful-info recovery. On `matplotlib__matplotlib-26466` and `django__django-13112`, Pro Direct is worse than Flash Direct, suggesting that alignment with the strict exact-slot proxy matters more than model tier alone.

## 4. Trace Analysis

### 4.1 BED asks more but hits less

| Run | Total questions | Useful-info hit turns | IDK | Hit rate |
|---|---:|---:|---:|---:|
| Direct Flash | 41 | 22 | 19 | **53.7%** |
| BED Flash | 46 | 10 | 36 | 21.7% |
| Direct Pro | 39 | 19 | 20 | **48.7%** |
| BED Pro | 50 | 7 | 43 | 14.0% |

BED is especially weak in later turns. Flash BED goes `0/9` on turn 3. Pro BED goes `0/10` on both turns 4 and 5. In other words, Pro BED's final 20 questions recover no new useful-info items.

| Run | Turn 1 | Turn 2 | Turn 3 | Turn 4 | Turn 5 |
|---|---:|---:|---:|---:|---:|
| Direct Flash hits/asked | 5/10 | 7/9 | 4/9 | 5/8 | 1/5 |
| BED Flash hits/asked | 5/10 | 2/9 | 0/9 | 2/9 | 1/9 |
| Direct Pro hits/asked | 7/10 | 5/9 | 5/8 | 1/6 | 1/6 |
| BED Pro hits/asked | 2/10 | 3/10 | 2/10 | 0/10 | 0/10 |

This shows that BED's failure is not a lack of turns. BED often spends the full 5-turn budget but fails to convert later questions into proxy-scored information. Pro BED is the clearest case: every task runs all 5 turns, ATC is `5.00`, but full recovery is `0/10`.

### 4.2 Direct better matches the strict proxy slots

Direct more often asks about user-observable slots that map directly to useful-info items:

- **traceback/error**: full error text, exception type, exception location, SQL syntax error.
- **version/config**: Django/Matplotlib/scikit-learn versions, database `OPTIONS`, AppConfig, or settings.
- **generated artifact**: generated SQL, URL pattern, wrong internal representation.
- **repro trigger**: slug path converter, 3D axes, mutable `xy` in `ax.annotate`, NFKD input.
- **actual/expected behavior**: actual output, expected output, wrong SQL, wrong Mathematica code.

These questions match the useful-info item granularity better. Even when a Direct question contains multiple sub-slots, the proxy can often select the most directly asked item. For example, in `django__django-13297`, Direct Pro asks about the URL pattern on turn 1 and the traceback on turn 2, exactly matching the two scored items, so it finishes in two turns.

### 4.3 BED's EIG objective mismatches exact-slot scoring

BED's selected questions often distinguish hypotheses by asking about root cause, repair scope, ideal fix strategy, workaround behavior, component ownership, or deployment topology. These questions may be useful in real triage, but in this benchmark they do not necessarily correspond to concrete ordinary-reporter-answerable slots audited as useful-info items.

Typical patterns include:

- **root cause / component ownership**: in `django__django-13297`, Pro BED repeatedly asks which part of Django should change and what the ideal behavior should be; these do not map to the URL slug converter or sqlite traceback.
- **fix strategy / desired behavior**: in `matplotlib__matplotlib-26466`, Pro BED asks whether the library should automatically copy, what the ideal resolution is, and what should happen after mutating the array; the scored items are Matplotlib version, Qt5Agg backend, and the reproduction condition involving mutable `xy` with `ax.annotate` and an arrow.
- **workaround / alternative scope**: across tasks, BED asks whether a workaround works, whether another aggregate function fails, or whether only certain polynomials are affected; these are usually not exact useful-info items.
- **deployment topology**: on `django__django-13279`, all runs are pulled toward session backend, rolling upgrade, multi-instance deployment, or errors, while the only item is `DEFAULT_HASHING_ALGORITHM='sha1'`.

Therefore, BED's failure in this experiment should not be reduced to an EIG arithmetic problem. The more precise explanation is: **the current BED prompt generates disagreement axes that are poorly aligned with strict-proxy exact-slot useful-info recovery**. EIG optimizes hypothesis discrimination, but the scoring function rewards directly eliciting pre-audited user-answerable information slots.

### 4.4 Pro does not automatically fix the mismatch

Pro Direct has some advantages: it hits 7 tasks on turn 1, compared with Flash Direct's 5, and it fully recovers `django__django-15375` and `django__django-13297` more quickly. But Pro is not monotonically better:

- `django__django-13112`: Flash Direct covers 4/4 in 4 turns; Pro Direct covers only 2/4, then asks about AppConfig label, INSTALLED_APPS dotted path, and shell inspection, missing the version difference and intra-app FK.
- `matplotlib__matplotlib-26466`: Flash Direct covers 2/3; Pro Direct gets IDK in all 5 turns, staying on plotting library, array mutation intent, and desired behavior.
- `matplotlib__matplotlib-23314`: Pro Direct is clearly better than Flash Direct, recovering all 3 items: version, backend, and reproduction condition.

These differences suggest that a stronger model can make questions more specific, but it can also make them more like maintainer diagnosis. In this experiment, the key is not whether the question is intelligent in the abstract; it is whether the question lands directly on a useful-info item the strict proxy can return.

## 5. Representative Cases

`django__django-11239` is the cleanest config-slot contrast. Flash Direct and Flash BED both ask in turn 1 how the PostgreSQL dbshell client certificate/key should be specified, hitting the `sslcert` and `sslkey` `OPTIONS` keys. Pro Direct also hits in one turn. Pro BED gets IDK in all 5 turns because its questions become about which SSL parameters dbshell should use, whether it should handle `sslmode`, and how important exact ORM SSL matching is, rather than directly asking for the database setting keys for the certificate and key.

`django__django-15375` shows how Direct hits generated-SQL/error slots. Direct Pro recovers `SELECT FROM (SELECT ...) subquery` on turn 1 and `OperationalError near FROM` on turn 3, completing the task in 3 turns. BED Pro only hits raw SQL on turn 2; the other turns repeatedly ask about the intended semantics of the `default` argument. Flash BED gets IDK in all 5 turns, focusing on aggregate function type, whether the issue is new to Django 4.0.1, whether other aggregates fail, and minimal reproducer availability.

In `django__django-13297`, Direct Pro fully recovers the task in two turns: turn 1 asks about the URL pattern and keyword argument type, hitting the slug path converter; turn 2 asks about view code and traceback, hitting the sqlite binding error. BED Pro gets 0 coverage, asking where the workaround is applied, whether third-party packages are involved, which Django component should change, and what the ideal behavior is.

`matplotlib__matplotlib-26466` is a case where both BED and Direct can fail. Both BED runs get 0 coverage. Pro BED is especially clear: it asks about automatic copying, accidental side effects, ideal resolution, and expected behavior after array mutation. Flash Direct at least hits the annotation reproduction condition and version; Pro Direct degrades to 0 coverage, showing Direct's advantage is empirical rather than guaranteed.

`scikit-learn__scikit-learn-15100` is a stable Direct success and clear BED Pro mismatch. Direct Flash and Direct Pro both reach `0.800` coverage by asking about Unicode normalization, NFKD input, actual output, and expected output. Pro BED gets IDK in all 5 turns, asking whether the fix belongs in `strip_accents_unicode` or `CountVectorizer`, what Unicode strategy should be used, what the root cause is, and whether only some combining marks are affected.

`django__django-13279` is the shared failure case. The only useful-info item is that `DEFAULT_HASHING_ALGORITHM` is configured as `'sha1'`. None of the four runs directly asks about the hashing algorithm setting. Instead, they move toward session backend, serializer, decode error, deployment, rolling upgrade, or user impact. This shows that some useful-info targets are very narrow; if the initial framing does not guide the model to that setting, 5 turns may not be enough.

## 6. Conclusion and Threats to Validity

In the current 10-task Ambig-SWE useful-info recovery benchmark, **Direct is the stronger and more robust baseline**. Under both Flash and Pro evaluated models, it beats BED with lower ATC, lower IDK, higher hit rate, and higher useful-info coverage. BED's structured hypotheses and EIG ranking do not produce a net benefit; they often spend the question budget on root-cause, scope, workaround, and fix-strategy questions that the strict proxy cannot score.

This conclusion should remain scoped to the current setup. It does not show that BED-style clarification is ineffective in general, nor that Direct is always better for real software repair. The safer claim is: under this 10-task pilot, 29 useful-info items, current BED prompt, Pro strict proxy, `max_turns=5`, and exact-slot coverage rule, BED is visibly misaligned with the evaluation target.

Main limitations:

- The dataset has only 10 tasks, so this is pilot-scale evidence.
- Useful-info items were LLM-generated and manually revised, so extraction bias may remain.
- The proxy selector is an LLM-simulated user, not a real issue reporter.
- Coverage is strict: an item counts only when the proxy selects a remaining item and the system returns the exact item text.
- Each turn can recover at most one item, so broad questions are not rewarded for covering multiple information points at once.
- The experiment does not run a downstream coding agent, so it cannot directly infer patch success or test pass rates.
- Pro-vs-Flash differences are also affected by question wording and proxy alignment, so they should not be read as a simple model capability ranking.
