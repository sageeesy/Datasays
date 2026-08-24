# Qwen3.6 Flash: Olist Business Analysis Suite v2.1.0

## Run Configuration / 运行配置

| Field / 字段 | Value / 值 |
|---|---|
| Date / 日期 | 2026-08-21 |
| Model / 模型 | `qwen/qwen3.6-flash` via OpenRouter |
| Benchmark | `datasays_olist_business_analysis_v2` v2.1.0 |
| Data / 数据 | Deterministic customer-level sample: 15,000 orders, five related Olist tables |
| Cases / Turns | 24 cases / 26 turns |
| Prompt style | `zero` |
| Repair budget | At most 2 validation-driven code repairs per turn |
| File transport | Local staged files |
| API transport | In-process ASGI through the real `/api/query` route |
| Raw local report | `server/evals/results/olist-business-v2.1.0-qwen3.6-flash.json` (git-ignored) |

This is one observed run on a local working-tree snapshot, not a universal model-accuracy claim. The earlier v1 and v2 smoke reports used the 45,101-order fixture and are not directly comparable.

这是当前本地工作区代码和 15k 抽样数据上的一次实测，不代表模型的普适准确率。早期 v1 和 v2 冒烟报告使用 45,101 订单数据，不能直接比较。

## Headline Results / 核心结果

| Metric / 指标 | Result / 结果 |
|---|---:|
| Case pass rate / 题目通过率 | **4 / 24 (16.67%)** |
| Fact recall / 事实召回率 | **46.15%** |
| Business-term coverage / 业务要点覆盖率 | **82.05%** |
| Execution success / 执行成功率 | **96.15% (25/26 turns)** |
| Structured-result rate / 结构化结果率 | **100% (24/24 non-clarification turns)** |
| Runtime validation pass / 运行时验证通过率 | **95.83% (23/24)** |
| Clarification accuracy / 澄清准确率 | **100% (2/2 expected stops)** |
| Memory signal accuracy / 记忆信号准确率 | **100% (2/2 expected follow-ups)** |
| Metric adoption / 指标定义采用率 | **60% (3/5 applicable turns)** |
| Visualization coverage / 图表覆盖率 | **100% (9/9 requested turns)** |
| Plan-intent accuracy / 计划意图准确率 | **23.53% (4/17 applicable turns)** |
| Average turn latency / 平均单轮延迟 | **54.642 s** |
| Summed turn latency / 单轮延迟合计 | **1,420.68 s (23.68 min)** |

The CLI returned exit code 1 because twenty cases failed benchmark hard gates; the evaluation process itself completed and wrote the full report.

CLI 退出码为 1 是因为 20 题未通过硬性条件，不是评测进程崩溃。完整报告已正常写入本地结果目录。

## Capability Breakdown / 能力分类

| Capability / 能力 | Passed / Total | Pass rate |
|---|---:|---:|
| Metric execution / 指标执行 | 2 / 6 | 33.33% |
| Data quality and grain / 数据质量与粒度 | 0 / 4 | 0% |
| Business diagnosis / 经营诊断 | 1 / 5 | 20% |
| Decision support / 决策支持 | 0 / 4 | 0% |
| Clarification and boundaries / 澄清与边界 | 1 / 3 | 33.33% |
| Multi-turn memory / 多轮记忆 | 0 / 2 | 0% |

## Case Outcomes / 逐题结果

| Case | Result | Primary finding / 主要原因 |
|---|---|---|
| `executive_business_snapshot` | Fail | GMV/AOV used a broader order scope than the delivered-order reference; delivery-rate denominator also differed. |
| `monthly_peak_diagnosis` | **Pass** | Peak month, supporting facts, trend output, and business explanation passed. |
| `state_revenue_concentration` | Fail | Top-three state concentration was calculated incorrectly. |
| `category_revenue_concentration` | Fail | Shares were rounded inside structured evidence and exceeded strict numeric tolerance. |
| `repeat_customer_health` | **Pass** | Correct stable customer identifier, repeat count/rate, and observation-window caveat. |
| `payment_structure_risk` | Fail | Payment-value shares and multi-payment order share were mixed or reported with the wrong denominator. |
| `fact_table_join_audit` | Fail | Join inflation and reconciliation facts were wrong after one repair; grain explanation was incomplete. |
| `review_grain_audit` | Fail | Used the wrong review population/grain and missed part of the weighting explanation. |
| `customer_identity_audit` | Fail | Repeat-rate precision missed tolerance and one required identity/grain concept was absent. |
| `missingness_business_impact` | Fail | Review coverage and comment-missingness populations differed from the delivered-order contract. |
| `late_delivery_experience_gap` | Fail | Late rate and score-gap facts were confused after one repair; causal-boundary language was incomplete. |
| `state_delivery_hotspot` | **Pass** | Correct sample threshold, state, order count, late rate, review score, and ranking artifact. |
| `category_experience_problem` | Fail | Correct problem category but rounded review score missed tolerance. |
| `seller_risk_diagnosis` | Fail | Revenue-percentile/order-count filters selected the wrong seller. |
| `monthly_decline_decomposition` | Fail | MoM direction and decomposition values were wrong after two repairs. |
| `regional_growth_priority` | Fail | Calculation ran, but validation rejected derived names in `columns_used` after two repairs. |
| `fulfillment_action_plan` | Fail | Late-order scale and score loss were wrong; action/causal wording coverage was incomplete. |
| `category_portfolio_strategy` | Fail | Core-category revenue and problem-category review evidence did not match the reference. |
| `seller_governance_strategy` | Fail | Wrong seller evidence and confusion between late rate and review score. |
| `channel_quality_clarification` | Fail* | Correctly stopped for missing channel/new-customer evidence, but `2/3` term coverage was compared with the authored `0.67` threshold. |
| `profit_metric_clarification` | **Pass** | Correctly stopped before calculation because cost evidence was unavailable. |
| `causal_claim_boundary` | Fail | Association values were wrong and the causal caveat was incomplete. |
| `state_category_followup` | Fail | First turn passed and memory loaded; second-turn category revenue used the wrong scope. |
| `experience_executive_followup` | Fail | Memory loaded, but both turns carried incorrect experience facts and incomplete boundary language. |

`channel_quality_clarification` exposes an evaluation-authoring issue: the intended two-of-three coverage is mathematically `0.666...`, which is less than the stored `0.67`. The raw v2.1.0 result is preserved unchanged. A future v2.1.1 should replace approximate fractional thresholds with exact fractions and report the rescored result separately.

`channel_quality_clarification` 暴露了一个评测编写问题：预期的“三组要点覆盖两组”实际为 `0.666...`，小于配置中的 `0.67`。v2.1.0 原始分数保持不变；后续 v2.1.1 应改用精确分数并单独报告重评结果。

## Failure Analysis / 失败分析

- 19 of 26 turns did not recall every required fact; numeric and entity correctness is the dominant bottleneck.
- 9 of 26 turns omitted at least one requested business concept or boundary.
- 6 turns used repair, totaling 8 repair attempts; two turns exhausted the two-repair budget.
- Only one turn failed runtime validation. High execution/validation rates therefore do not imply semantic correctness.
- Both expected clarification branches and both memory-use signals passed, but the memory cases still failed their recomputed facts.
- The current Validator checks execution, schema, structured output, metric grounding, and visualization contracts. It does not independently prove that generated filters, denominators, joins, or aggregations implement the requested business semantics.

- 26 轮中有 19 轮未完整命中必要事实，数值和实体准确性是当前主要瓶颈。
- 26 轮中有 9 轮遗漏了至少一项业务要点或边界说明。
- 6 轮触发修复，共 8 次修复；其中 2 轮用尽两次修复额度。
- 只有 1 轮未通过运行时 Validator，因此“能执行、有结构化结果”不等于业务语义正确。
- 两个澄清分支和两个记忆使用信号都正确，但两道多轮题仍因重算事实错误而失败。
- 当前 Validator 主要检查执行、字段、结构化协议、指标绑定和可视化协议，还不能独立证明过滤、分母、Join 和聚合语义正确。

## Recommended Next Actions / 建议下一步

1. Make delivery scope, entity grain, denominator, and aggregation order explicit typed fields in `AnalysisPlan`, then require generated code to consume them.
2. Separate exact machine evidence from two-decimal UI formatting; never round values inside `AnalysisResult` before scoring or validation.
3. Add deterministic semantic checks for common metrics and join-grain invariants instead of treating a valid structured artifact as sufficient evidence.
4. Improve repair feedback for wrong filters/denominators and for derived labels incorrectly reported in `columns_used`.
5. Fix exact fractional term thresholds in a new benchmark version rather than changing this recorded v2.1.0 result.
6. Add full token/cost accounting and per-case checkpointed result persistence; this run records latency but not complete token usage.
