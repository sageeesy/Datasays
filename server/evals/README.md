# DataSays Evaluation / 评测说明

DataSays keeps two complementary 24-case suites over prepared 2017 tables from the [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce). The suites answer different questions and must not be merged into one headline score.

DataSays 基于 [Olist 巴西电商公开数据集](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)的 2017 年精简表保留两套互补的 24 题评测。两套题回答的问题不同，不应合并成一个笼统的总分。

| Suite / 题集 | Purpose / 目的 | Primary signal / 核心信号 | Runner |
|---|---|---|---|
| Olist Calculation Suite v1 | Closed-form calculation regression / 确定性计算回归 | Exact numeric accuracy / 精确数值正确率 | `evals/run_eval.py` |
| Olist Business Analysis Suite v2 | End-to-end Agent capability / 完整经营分析能力 | Facts, business reasoning, clarification, memory / 事实、业务要点、澄清与记忆 | `evals/run_business_eval.py` |

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

## v1: Calculation Suite / 计算回归题集

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

## v2: Business Analysis Suite / 经营分析能力题集

Current full baseline / 当前全量基线：[`baselines/qwen3.6-flash-v2.1.0-2026-08-21.md`](baselines/qwen3.6-flash-v2.1.0-2026-08-21.md). Qwen3.6 Flash passed 4/24 cases on fixture v2.1.0; the report includes category scores, all case outcomes, limitations, and failure analysis. / Qwen3.6 Flash 在 v2.1.0 数据上通过 4/24 题，报告包含分类分数、逐题结果、限制和失败归因。

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

- v2.1.0 has one complete Qwen3.6 Flash baseline; v1.1.0 still requires a new baseline. Earlier reports used the 45,101-order fixture and are not directly comparable.
- v2.1.0 contains one known authored-threshold issue: intended two-of-three term coverage was stored as `0.67`, which is stricter than exact `2/3`. The raw result is preserved and the issue is disclosed in the baseline report.
- A deterministic reference fact proves the expected calculation for the prepared fixtures, not universal business truth.
- Term coverage can detect missing required concepts, but cannot fully judge recommendation quality or causal reasoning.
- A passed structured contract does not independently prove every generated transformation is semantically correct.
- Full-suite model runs incur API cost and should record model ID, date, configuration, and raw result JSON.

- v2.1.0 已有一次完整 Qwen3.6 Flash 基线；v1.1.0 仍需重跑。早期报告使用 45,101 订单数据，不能直接比较。
- v2.1.0 已知一个阈值编写问题：预期的三组要点命中两组被写成 `0.67`，它比精确的 `2/3` 更严格。原始分数保持不变，并在基线报告中披露。
- 确定性标准答案只证明当前精简数据和既定口径下的计算，不代表普适业务真理。
- 词组覆盖可以发现遗漏要点，但不能完整评价建议质量或因果推理。
- 结构化协议通过不等于每一步数据变换都已被独立证明正确。
- 全量模型评测会产生 API 成本，应记录模型 ID、日期、配置和原始结果 JSON。

Detailed rationale / 详细设计：[`BENCHMARK_DESIGN.md`](BENCHMARK_DESIGN.md).
