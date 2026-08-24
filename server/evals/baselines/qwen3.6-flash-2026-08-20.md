# Qwen3.6 Flash Olist v1 Baseline / Qwen3.6 Flash Olist v1 基线

## 中文说明

### 运行信息

| 项目 | 值 |
|---|---|
| 日期 | 2026-08-20 |
| Benchmark | `datasays_olist_business_analytics_v1` |
| 模型 | `qwen/qwen3.6-flash` via OpenRouter |
| 题目 | 24 题：中文 12、英文 12 |
| 文件传输 | `local_store` |
| API 调用 | `in_process_asgi`，真实调用 `/api/query` 路由 |
| Python 执行 | `USE_DOCKER=false`，使用后端 Conda Python |
| 原始结果 | 本机 `evals/results/olist-v1-qwen3.6-flash.json`，默认不提交 Git |

该基线覆盖真实 LangGraph、OpenRouter、代码生成、Python 执行、结构化结果、Validator 和修复循环，但不覆盖 multipart 上传传输、Docker 隔离或远程部署网络。

### 汇总结果

| 指标 | 结果 |
|---|---:|
| 数值答案通过率 | **23/24，95.83%** |
| 执行成功率 | 24/24，100% |
| 结构化结果覆盖率 | 24/24，100% |
| Validator 通过率 | 24/24，100% |
| 触发修复后的成功率 | 2/2，100% |
| 指标期望命中率 | 2/6，33.33% |
| 指定图表生成率 | 4/4，100% |
| 平均端到端延迟 | 36.47 秒/题 |
| Structured LLM Planner | 11/24 |
| Deterministic Fallback Planner | 13/24 |

### 分类别结果

| 类别 | 通过 |
|---|---:|
| 订单生命周期与时间 | 5/5 |
| 支付指标 | 5/5 |
| 商品经营 | 6/6 |
| 客户与体验 | 4/5 |
| 数据粒度与核对 | 3/3 |

中文题通过 11/12，英文题通过 12/12；Easy 2/2、Medium 11/11、Hard 10/11。

### 唯一数值失败

失败题：`on_time_minus_late_review_gap`

- 标准答案：`1.7382424719`
- 模型结果：`1.7369662616`
- 绝对误差：`0.0012762103`
- 容差：`0.001`

题目要求先按 `order_id` 汇总同订单多条评价，再比较准时和延迟订单平均分。修复后的代码成功执行且满足结果协议，但计算值显示它没有完全遵循订单级去重/平均规则。该案例证明：当前 Validator 能验证执行、字段和结果契约，但不会独立复算业务粒度，因此 `validation_passed=true` 不能解释为业务答案必然正确。

### 修复与 Planner 观察

- `multi_item_order_rate` 初次结果未满足结果协议，修复一次后通过；
- `on_time_minus_late_review_gap` 初次代码写错文件 ID，修复一次后成功执行，但最终数值仍超出容差；
- 24 题中 13 题回退到 deterministic fallback plan，说明该模型在严格 `AnalysisPlan` Schema 下的输出稳定性仍需提高；
- 6 道声明预期业务指标的题只有 2 道在最终 Plan 保留了正确指标 ID。数值准确率较高，但 metric grounding 不能据此声称稳定。

### 下一轮优先级

1. 在 Planner 与 Code Prompt 中增加通用的多表粒度检查：明确每张表 Grain、Join Cardinality，以及 Join 前是否需要先聚合；
2. 将“指标已检索”和“Planner 实际采用指标”分开计分，定位 Retriever 与 Planner 的责任；
3. 对 review、payment、item 等一对多表增加可确定执行的 Grain Validation，而不只依赖 Prompt；
4. Runner 增加逐题落盘和断点续跑，避免长评测中断后丢失已完成结果；
5. Docker 可用后重新运行同一模型，记录正式沙箱基线；再评估是否值得比较 Kimi K2.5 和可访问的 GPT 模型。

### 可安全使用的表述

可以写：

> 在本机非 Docker 执行环境中，Qwen3.6 Flash 在 24 题 Olist 经营分析 Benchmark 上取得 23/24 数值通过；全部任务完成结构化执行与验证，2 个触发修复的案例均恢复执行。

不能写：

- 已达到生产准确率；
- Validator 保证所有答案正确；
- 已完成 Docker 或公开部署基线；
- 指标语义遵循率稳定；
- 95.83% 可以代表未见真实企业数据上的泛化能力。

## English

### Run Configuration

| Item | Value |
|---|---|
| Date | 2026-08-20 |
| Benchmark | `datasays_olist_business_analytics_v1` |
| Model | `qwen/qwen3.6-flash` via OpenRouter |
| Cases | 24: 12 Chinese and 12 English |
| File transport | `local_store` |
| API transport | `in_process_asgi`, calling the real `/api/query` route |
| Python execution | `USE_DOCKER=false` with the backend Conda interpreter |
| Raw report | Local `evals/results/olist-v1-qwen3.6-flash.json`, ignored by Git by default |

This run covers the real LangGraph workflow, OpenRouter calls, code generation, Python execution, structured result contract, deterministic Validator, and repair loop. It does not cover multipart upload transport, Docker isolation, or remote-deployment networking.

### Headline Results

| Metric | Result |
|---|---:|
| Numeric answer pass rate | **23/24, 95.83%** |
| Execution success | 24/24, 100% |
| Structured result coverage | 24/24, 100% |
| Validator pass rate | 24/24, 100% |
| Success after repair was triggered | 2/2, 100% |
| Expected metric-ID adherence | 2/6, 33.33% |
| Requested visualization coverage | 4/4, 100% |
| Average end-to-end latency | 36.47 seconds per case |
| Structured LLM Planner | 11/24 |
| Deterministic Fallback Planner | 13/24 |

Category results were 5/5 for order lifecycle, 5/5 for payments, 6/6 for merchandising, 4/5 for customer experience, and 3/3 for grain/reconciliation. Chinese cases passed 11/12 and English cases passed 12/12.

### Numeric Failure

`on_time_minus_late_review_gap` expected `1.7382424719` but returned `1.7369662616`, an absolute error of `0.0012762103` against a `0.001` tolerance. The task explicitly required duplicate reviews to be aggregated at order grain before comparing on-time and late deliveries. The repaired code executed and passed the artifact contract, but the numeric difference indicates that the intended grain rule was not fully followed.

This is evidence that the current Validator checks execution and artifact consistency, not independent semantic correctness.

### Next Priorities

1. Add generic dataset-grain and join-cardinality checks to planning and code-generation context;
2. Score metric retrieval separately from planner metric adoption;
3. Add deterministic grain checks for one-to-many review, payment, and item tables;
4. Persist results after each case and support resume;
5. Re-run under Docker before comparing additional models.

### Resume-Safe Claim

> In a local non-Docker execution baseline, Qwen3.6 Flash passed 23 of 24 numeric Olist business-analytics cases; all cases produced structured executed artifacts, and both cases that triggered repair recovered successfully.

Do not describe this run as production accuracy, Docker isolation, guaranteed correctness, stable metric adherence, or generalization to unseen enterprise data.
