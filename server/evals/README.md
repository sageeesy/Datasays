# DataSays Evaluation / 评测说明

DataSays currently uses two headline evaluation tracks: a 13-case cross-capability benchmark for analysis breadth and an Olist-24 stress test for business-analytics reliability. A legacy 24-case Olist calculation suite is retained as a supporting deterministic regression asset. These suites answer different questions and must not be merged into one headline score.

DataSays 当前使用两条主要评测轨道：13 题的跨能力 Benchmark 验证分析广度，Olist-24 压力测试验证经营分析可靠性。项目另保留一套 24 题的 Olist 确定性计算回归题作为辅助资产。这些题集回答的问题不同，不应合并成一个笼统总分。

| Suite / 题集 | Purpose / 目的 | Primary signal / 核心信号 | Runner |
|---|---|---|---|
| Analysis Capability Benchmark V1 | Breadth across heterogeneous analysis tasks / 异构分析任务的能力广度 | Planning, execution, audited references, Evidence, strict E2E / 计划、执行、独立参考值、Evidence 与严格端到端 | `evals/run_capability_probes.py` |
| Olist-24 Business Analytics Reliability Benchmark | Strict semantic reliability stress test / 严格业务语义可靠性压力测试 | Metric semantics, population, denominator, grain, joins, time, clarification / 指标口径、总体、分母、粒度、Join、时间与澄清 | `evals/run_business_eval.py` |
| Olist Calculation Suite v1 (retained) | Supporting closed-form regression / 辅助确定性计算回归 | Exact scalar accuracy / 精确标量数值 | `evals/run_eval.py` |

The cases are authored for DataSays. They are not official Olist, DataSciBench, DABench, DABstep, or DS-1000 benchmark releases. Olist fixture licensing and attribution are documented in [`data/olist/README.md`](data/olist/README.md).

这些题目由 DataSays 项目自行设计，不是 Olist、DataSciBench、DABench、DABstep 或 DS-1000 的官方题集。数据许可和署名见 [`data/olist/README.md`](data/olist/README.md)。

## Prepared Data / 精简数据

| Dataset | Grain / 粒度 | Rows / 行数 |
|---|---|---:|
| `olist_orders_2017.csv` | one order / 每行一个订单 | 15,000 |
| `olist_order_items_2017.csv` | one order item / 每行一个订单商品 | 16,956 |
| `olist_order_payments_2017.csv` | one payment sequence / 每行一条支付序列 | 15,796 |
| `olist_order_reviews_2017.csv` | one review record / 每行一条评价 | 14,988 |
| `olist_products_2017.csv` | one product / 每行一个商品 | 8,264 |

The fixtures are a deterministic customer-level sample targeting 15,000 orders. Customers are ranked by a stable SHA-256 hash of `customer_unique_id`; every order for a selected customer is retained, then child tables are filtered by `order_id` and `product_id`. This preserves repeat-order history and one-to-many relationships instead of sampling each CSV independently.

精简表是以 15,000 笔订单为目标的客户级确定性抽样：按 `customer_unique_id` 的 SHA-256 结果稳定排序，保留入选客户的所有订单，再用 `order_id` 和 `product_id` 筛选关联表。因此仍保留复购历史、一对多 Join、重复或缺失评价、多次支付、履约、品类和卖家等真实难点。经纬度表与当前题目无关，未纳入仓库。

Reducing CSV rows lowers upload, profiling, and sandbox runtime, but barely changes LLM tokens because the model receives bounded schema profiles rather than raw rows. Token cost is controlled mainly by the number of cases, model calls, retries, and repeated prompt context.

缩减 CSV 会降低上传、数据画像和沙箱执行成本，但对 Token 影响很小，因为模型收到的是有界字段画像，而不是原始数据行。Token 主要由题目数、模型调用数、修复次数和重复 Prompt 上下文决定。

## Analysis Capability Benchmark V1 / 分析能力评测 V1

[`capability_probe_cases.json`](capability_probe_cases.json) defines 13 cases across Core Data Analysis, Statistical Analysis, Predictive Analysis, and Behavioral Analysis. Independent deterministic references are stored in [`capability_probe_references.json`](capability_probe_references.json). The benchmark separates canonical planning, Gate readiness, execution, numerical reference matching, Evidence coverage, and strict Plan-to-Evidence-to-Reference completion.

[`capability_probe_cases.json`](capability_probe_cases.json) 定义了 13 道覆盖基础数据分析、统计分析、预测分析和行为分析的题目，独立确定性参考值保存在 [`capability_probe_references.json`](capability_probe_references.json)。评测分开记录 canonical planning、Gate readiness、执行、数值参考匹配、Evidence coverage 与严格 Plan-to-Evidence-to-Reference 闭环。

Current frozen baseline / 当前冻结基线：

- 13 cases across 4 capability tracks / 13 题、4 个 capability tracks；
- 12/13 successful executions / 12/13 成功执行；
- all 12 executed cases matched their audited numerical references / 12 道已执行题均匹配独立审核数值参考；
- 7/13 strict Plan → Evidence → Reference E2E passes / 7/13 严格端到端通过。

The 12/12 figure is conditional numerical reference matching among executed cases, not overall benchmark accuracy. The full local run artifact is saved under `evals/results/` and excluded from Git.

12/12 表示“已执行题目中的数值参考匹配”，不是整体正确率。完整本地 artifact 保存在 `evals/results/` 且不进入 Git。

```bash
cd server
python evals/run_capability_probes.py \
  --output evals/results/analysis-capability-baseline.json
```

## Retained v1 Calculation Suite / 保留的 v1 计算回归题集

[`benchmark_cases.json`](benchmark_cases.json) contains 24 closed-form questions with deterministic scalar answers and tolerances. It tests aggregation, filtering, dates, multi-table joins, entity grain, reconciliation, and basic business metrics. Its main pass condition is numeric accuracy from `AnalysisResult.primary_value`; incidental numbers in prose cannot pass a case.

[`benchmark_cases.json`](benchmark_cases.json) 包含 24 道拥有确定性标量答案和容差的封闭题，覆盖聚合、筛选、日期、多表 Join、实体粒度、金额核对和基础业务指标。主通过条件是 `AnalysisResult.primary_value` 的数值准确性，正文里偶然出现正确数字不能得分。

Historical pre-sampling baseline / 15k 抽样前的历史基线：[`baselines/qwen3.6-flash-2026-08-20.md`](baselines/qwen3.6-flash-2026-08-20.md). Its scores are not comparable with fixture version 1.1.0 and must be rerun before publication. / 其分数不能与 1.1.0 数据版本直接比较，发布前必须重跑。

```bash
cd server
python evals/run_eval.py \
  --model qwen/qwen3.6-flash \
  --local-files \
  --in-process-api \
  --summary-only \
  --output evals/results/olist-v1-qwen3.6-flash.json
```

## Olist-24 Business Analytics Reliability Benchmark / Olist-24 业务分析可靠性评测

Current post-RMC diagnostic baseline / 当前 post-RMC 诊断基线：**3/24 strict case passes**. It used `qwen/qwen3.6-flash`, explicit `project_id=olist`, and the current RMC, Planner, Gate, Code, Evidence, and Validator path. The complete local artifact is `evals/results/post-rmc-diagnostic-baseline-20260826.json` and is intentionally excluded from Git; the committed facts and failure analysis are recorded in the [evaluation-driven reliability retrospective](../../docs/evaluation-driven-reliability-improvement.md). This is a reliability stress-test result, not DataSays' overall analysis accuracy.

当前 post-RMC 诊断基线为 **3/24 严格 case 通过**。该轮固定 `qwen/qwen3.6-flash`、显式传入 `project_id=olist`，并走当前 RMC、Planner、Gate、Code、Evidence 和 Validator 链路。完整本地 artifact 为 `evals/results/post-rmc-diagnostic-baseline-20260826.json`，按设计不进入 Git；可提交的事实与失败分析记录在[Evaluation-driven Reliability 技术复盘](../../docs/evaluation-driven-reliability-improvement.md)。这是可靠性压力测试结果，不是 DataSays 整体分析正确率。

Historical v2.1.0 baseline / 历史 v2.1.0 基线：[`baselines/qwen3.6-flash-v2.1.0-2026-08-21.md`](baselines/qwen3.6-flash-v2.1.0-2026-08-21.md). Qwen3.6 Flash passed 4/24 cases in that earlier frozen run. The 4/24 record remains historical evidence and has not been overwritten by the newer baseline.

历史 v2.1.0 基线见 [`baselines/qwen3.6-flash-v2.1.0-2026-08-21.md`](baselines/qwen3.6-flash-v2.1.0-2026-08-21.md)，当时 Qwen3.6 Flash 在该冻结版本中通过 4/24 题。这一 4/24 仍作为历史证据保留，没有被新基线覆盖。

The lower post-RMC headline count is not, by itself, evidence that RMC reduced analysis capability. The frozen runs differ in planning and fail-closed contracts, and the post-RMC audit identified Planner readiness, result/evidence representation, scorer behavior, and benchmark assumptions as distinct failure layers. The repository does not support attributing the one-case decrease to a single cause.

post-RMC 的表面通过数更低，本身不能证明 RMC 降低了分析能力。两次冻结运行的 planning 与 fail-closed contract 不同，post-RMC 审计也将 Planner readiness、result/evidence representation、scorer behavior 和 benchmark assumptions 分成了不同失败层。现有证据不支持把一题的下降归因于某一个因素。

Historical pre-sampling integration smoke test / 15k 抽样前的历史冒烟测试：[`baselines/qwen3.6-flash-v2-smoke-2026-08-21.md`](baselines/qwen3.6-flash-v2-smoke-2026-08-21.md). It is not comparable with the current fixture. / 它不能与当前 fixture 直接比较。

[`business_benchmark_cases.json`](business_benchmark_cases.json) contains 24 Chinese business requests. The source columns remain English, so language understanding is still exercised without allocating half of the benchmark to translated duplicates.

[`business_benchmark_cases.json`](business_benchmark_cases.json) 包含 24 道中文经营需求。源数据字段仍为英文，因此仍会测试跨语言字段理解，但不再为了中英文配额重复相同题型。

| Capability / 能力 | Cases / 题数 | What is tested / 测试内容 |
|---|---:|---|
| Metric execution / 指标执行 | 6 | Multi-metric answers, trends, concentration, repeat customers, payment structure |
| Data quality and grain / 数据质量与粒度 | 4 | Join fanout, review grain, customer identity, missingness impact |
| Business diagnosis / 经营诊断 | 5 | Drivers, hotspots, prioritization, sample thresholds, association boundaries |
| Decision support / 决策支持 | 4 | Evidence-backed recommendations, risks, and next actions |
| Clarification and boundaries / 澄清与边界 | 3 | Missing fields, undefined metrics, and unsupported causal claims |
| Multi-turn memory / 多轮记忆 | 2 | Follow-up references and reuse of validated, dataset-scoped context |

### v2 Case-to-Data Map / v2 题目与数据表映射

Table aliases / 表简写：`O` = Orders，`I` = Order Items，`Pay` = Payments，`Rev` = Reviews，`Prod` = Products。每题只上传表中列出的数据表。

| # | Case / 问题 | Capability / 类别 | Tables / 数据表 | Why these tables / 主要证据 |
|---:|---|---|---|---|
| 1 | `executive_business_snapshot` / 经营概览 | 指标执行 | O + Pay | 订单状态与时间 + 支付 GMV |
| 2 | `monthly_peak_diagnosis` / 月度峰值驱动 | 指标执行 | O + Pay | 月度订单量、GMV 与 AOV |
| 3 | `state_revenue_concentration` / 州收入集中度 | 指标执行 | O + Pay | 客户州 + 订单支付金额 |
| 4 | `category_revenue_concentration` / 品类收入集中度 | 指标执行 | O + I + Prod | 已交付订单 + 商品 `price` + 品类 |
| 5 | `repeat_customer_health` / 复购健康度 | 指标执行 | O | `customer_unique_id` 与已交付订单次数 |
| 6 | `payment_structure_risk` / 支付结构 | 指标执行 | O + Pay | 支付类型、金额与多次支付 |
| 7 | `fact_table_join_audit` / 事实表 Join 审计 | 数据质量 | O + I + Pay | 商品与支付两张事实表的粒度膨胀 |
| 8 | `review_grain_audit` / 评价粒度审计 | 数据质量 | O + Rev | 订单与多条评价记录 |
| 9 | `customer_identity_audit` / 客户标识审计 | 数据质量 | O | `customer_id` 与 `customer_unique_id` 对比 |
| 10 | `missingness_business_impact` / 缺失影响 | 数据质量 | O + Rev | 送达时间、评价覆盖与评论缺失 |
| 11 | `late_delivery_experience_gap` / 延迟与评分 | 经营诊断 | O + Rev | 预计/实际送达时间 + 订单级评分 |
| 12 | `state_delivery_hotspot` / 州履约热点 | 经营诊断 | O + Rev | 州级订单量、延迟率与评分 |
| 13 | `category_experience_problem` / 品类体验问题 | 经营诊断 | O + I + Prod + Rev | 品类收入、订单量、延迟率与评分 |
| 14 | `seller_risk_diagnosis` / 卖家风险 | 经营诊断 | O + I + Rev | 卖家收入、订单量、延迟率与评分 |
| 15 | `monthly_decline_decomposition` / 环比下降拆解 | 经营诊断 | O + Pay | 月度 GMV、订单量与 AOV 环比 |
| 16 | `regional_growth_priority` / 区域增长优先级 | 决策支持 | O + Pay | 非 SP 州的 GMV、规模与 AOV |
| 17 | `fulfillment_action_plan` / 履约改善计划 | 决策支持 | O + Rev | 延迟规模、评分损失与州级热点 |
| 18 | `category_portfolio_strategy` / 品类组合策略 | 决策支持 | O + I + Prod + Rev | 核心品类收入 + 问题品类体验 |
| 19 | `seller_governance_strategy` / 卖家治理 | 决策支持 | O + I + Rev | 卖家规模、履约与评价证据 |
| 20 | `channel_quality_clarification` / 渠道质量澄清 | 澄清边界 | O + Pay | 验证现有表缺少渠道和完整新客定义 |
| 21 | `profit_metric_clarification` / 利润口径澄清 | 澄清边界 | O + I + Prod | 验证有收入但缺少成本字段 |
| 22 | `causal_claim_boundary` / 因果边界 | 澄清边界 | O + Rev | 只能观察延迟与评分关联，不能证明因果 |
| 23 | `state_category_followup` / 州到品类追问 | 多轮记忆 | O + I + Pay + Prod | 第一轮找州 GMV，第二轮在该州重算品类收入 |
| 24 | `experience_executive_followup` / 体验管理层追问 | 多轮记忆 | O + Rev | 第一轮计算体验差距，第二轮基于已验证上下文组织摘要 |

The v2 scorer follows a lightweight test-first concept inspired by [DataSciBench](https://github.com/THUDM/DataSciBench): each task declares testable facts and behavioral requirements instead of relying only on an LLM judge. It does not copy DataSciBench tasks or claim compatibility with its official score.

v2 评分器借鉴 [DataSciBench](https://github.com/THUDM/DataSciBench) 的测试驱动思想：每道题声明可检验事实和行为要求，而不是只依赖 LLM Judge。当前没有复制其题目，也不宣称与其官方分数可比。

### v2 Metrics / v2 指标

- **Case pass rate / 题目通过率:** every hard requirement in every turn passes.
- **Fact recall / 事实召回率:** expected values appear in structured sandbox evidence within tolerance.
- **Business-term coverage / 业务要点覆盖率:** required concepts or accepted synonyms appear in the answer.
- **Clarification accuracy / 澄清准确率:** the plan stops before execution when essential fields or definitions are absent.
- **Memory accuracy / 记忆准确率:** a follow-up turn reports use of bounded conversation context.
- **Execution and structured-result rates / 执行与结构化结果率:** the workflow executes and returns the typed artifact.
- **Metric, plan, and visualization coverage / 指标、计划与图表覆盖:** supporting diagnostics; they do not currently hard-fail a case.
- **Latency / 延迟:** end-to-end time for each turn.

Numeric facts are scored only from the structured `AnalysisResult`, never from polished prose. Business recommendations and statistical boundaries use explicit term groups. This keeps scoring deterministic, but it is not a complete semantic-quality judge.

数值事实只从结构化 `AnalysisResult` 得分，不从润色正文提取。经营建议和统计边界按预设语义词组评分。这种方法可重复，但不能完全替代人工判断或高质量语义评审。

```bash
cd server
python evals/run_business_eval.py \
  --model qwen/qwen3.6-flash \
  --local-files \
  --in-process-api \
  --summary-only \
  --output evals/results/olist-business-v2-qwen3.6-flash.json
```

Smoke test / 少量冒烟测试：

```bash
python evals/run_business_eval.py \
  --model qwen/qwen3.6-flash \
  --local-files \
  --in-process-api \
  --case-id fact_table_join_audit \
  --case-id profit_metric_clarification
```

逐题人工检查 24 题时，可以直接打开 [`olist_business_v2_baseline.ipynb`](olist_business_v2_baseline.ipynb)。选择项目的 `datasays` Python 环境后，反复运行 `await run_next_case()`；Notebook 每次只调用一道题，并将单题报告保存到 `evals/results/`。它使用原生异步的 in-process FastAPI，因此不需要另外启动后端。

For manual case-by-case review, open [`olist_business_v2_baseline.ipynb`](olist_business_v2_baseline.ipynb), select the project `datasays` Python environment, and repeatedly run `await run_next_case()`. Each call runs one case through the native async in-process FastAPI path and saves its report under `evals/results/`; no separate backend process is required.

## Rebuild And Verify / 重新生成与校验

Rebuild the prepared Olist fixtures and v1 answers from the original archive:

```bash
python evals/prepare_olist_benchmark.py \
  --source-dir /path/to/olist/archive \
  --target-orders 15000
```

Regenerate v2 questions and deterministic facts from the committed fixtures:

```bash
python -m evals.prepare_olist_business_benchmark
```

Run deterministic tests without calling an LLM:

```bash
python -m unittest tests.test_olist_benchmark tests.test_olist_business_benchmark tests.test_business_eval_runner -v
```

`--local-files` skips multipart transfer only; the query still runs through the real FastAPI route, LangGraph, model, Python executor, Validator, and persistence services. `--in-process-api` uses ASGI transport and is intended for local baselines or CI. Omit both flags when evaluating a remote deployment and its upload path.

## Truthfulness Boundaries / 真实性边界

- The current headline baselines are the 13-case Analysis Capability Benchmark V1 run and the post-RMC Olist-24 diagnostic run. They measure breadth and strict business reliability respectively and are never combined.
- The 4/24 v2.1.0 report is a historical frozen baseline; the current post-RMC Olist-24 diagnostic baseline is 3/24. The lower count has multiple documented failure layers and no single proven cause.
- The retained Olist Calculation Suite v1.1.0 still requires a new publishable baseline. Earlier reports used the 45,101-order fixture and are not directly comparable.
- v2.1.0 contains one known authored-threshold issue: intended two-of-three term coverage was stored as `0.67`, which is stricter than exact `2/3`. The raw result is preserved and the issue is disclosed in the baseline report.
- A deterministic reference fact proves the expected calculation for the prepared fixtures, not universal business truth.
- Term coverage can detect missing required concepts, but cannot fully judge recommendation quality or causal reasoning.
- A passed structured contract does not independently prove every generated transformation is semantically correct.
- Full-suite model runs incur API cost and should record model ID, date, configuration, and raw result JSON.

- 当前首要基线是 13 题 Analysis Capability Benchmark V1 与 post-RMC Olist-24 诊断运行；两者分别测试能力广度与严格业务可靠性，不合并计分。
- 4/24 是历史 v2.1.0 冻结基线，当前 post-RMC Olist-24 诊断基线为 3/24。已记录的失败涉及多个层次，不存在已证明的单一下降原因。
- 保留的 Olist Calculation Suite v1.1.0 仍需新的可发布基线。早期报告使用 45,101 订单数据，不能直接比较。
- v2.1.0 已知一个阈值编写问题：预期的三组要点命中两组被写成 `0.67`，它比精确的 `2/3` 更严格。原始分数保持不变，并在基线报告中披露。
- 确定性标准答案只证明当前精简数据和既定口径下的计算，不代表普适业务真理。
- 词组覆盖可以发现遗漏要点，但不能完整评价建议质量或因果推理。
- 结构化协议通过不等于每一步数据变换都已被独立证明正确。
- 全量模型评测会产生 API 成本，应记录模型 ID、日期、配置和原始结果 JSON。

Detailed rationale / 详细设计：[`BENCHMARK_DESIGN.md`](BENCHMARK_DESIGN.md).
