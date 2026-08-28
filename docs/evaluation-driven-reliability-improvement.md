# DataSays: Evaluation-Driven Reliability Improvement

> 文档状态：持续维护中的技术复盘
> 覆盖范围：Olist Business Analysis Suite v2.1.0 基线、失败分析、AnalysisPlan V1.5 Planner 层改造
> 基线日期：2026-08-21
> 重要边界：本文区分实测结果、代码事实和设计推论；不会把后续计划描述为已完成能力。

## 目录

1. [Background](#1-background)
2. [Initial Benchmark](#2-initial-benchmark)
3. [Error Analysis](#3-error-analysis)
4. [Root Cause Investigation](#4-root-cause-investigation)
5. [Design Decision](#5-design-decision)
6. [Completeness Gate](#6-completeness-gate)
7. [Implementation](#7-implementation)
8. [Validation & Results](#8-validation--results)
9. [What We Learned](#9-what-we-learned)
10. [Next Steps](#10-next-steps)
11. [Interview / Project Story](#11-interview--project-story)

## 1. Background

DataSays 是一个以 CSV 为当前主要数据入口、通过 LLM 规划和生成 Pandas 代码、在 Python 沙箱中执行并返回结构化证据的数据分析 Agent 原型。它的目标不是让 LLM 仅凭上下文直接回答，而是让答案尽可能来自可执行、可检查的数据计算。

改造前的主要工作流是：

```text
User Question
    ↓
Profile / Skill / Metric / Memory
    ↓
AnalysisPlan
    ↓
LLM-to-Code
    ↓
Python Sandbox
    ↓
Validation
    ↓
Final Answer
```

各阶段分别负责：

- **Profile：**提取字段、类型、缺失率、候选主键、候选度量和日期范围等数据画像。
- **Skill：**根据问题选择 data quality、aggregation/ranking、time/cohort 或 metric diagnostics 分析 playbook。
- **Metric：**从本地指标定义中检索 GMV、AOV、订单量等业务口径，并把逻辑概念绑定到上传字段。
- **Memory：**在多轮对话中提供近期消息和已经验证的历史发现。
- **AnalysisPlan：**描述计划使用的指标、字段、维度、过滤、时间粒度和分析步骤。
- **LLM-to-Code：**结合原始问题、文件信息和 analysis context 生成 Pandas 代码。
- **Sandbox：**执行代码并提取 `AnalysisResult` 结构化结果。
- **Validation：**检查执行状态、字段存在性、结构化协议、metric ID grounding、结果字段和可视化协议。

### 为什么建立 Olist Business Analysis Benchmark

早期测试更接近“代码是否执行、是否返回结果”。这不足以判断一个数据 Agent 是否能够完成真实业务分析，因为一段代码可以无错误运行，却使用错误的人群范围、错误的分析粒度或错误的指标分母。

因此建立了 [Olist Business Analysis Suite v2.1.0](../server/evals/business_benchmark_cases.json)，使用 2017 年 15,000 笔订单的确定性客户级样本以及 orders、items、payments、reviews、products 五张关联表。24 个 case 不只测试数值计算，也测试：

- 业务指标口径和适用人群；
- order、item、payment、review、customer 等不同 entity grain；
- 多事实表 Join 与预聚合；
- 经营诊断、决策支持和因果边界；
- 缺字段时是否停止并澄清；
- 多轮分析是否正确使用记忆并重新计算。

它的核心问题不是“Python 能不能跑”，而是“Agent 是否算了用户真正要求的东西，并能提供可复核证据”。

## 2. Initial Benchmark

基线使用 `qwen/qwen3.6-flash`，通过 OpenRouter 运行；prompt style 为 `zero`，每轮最多允许两次 validation-driven code repair。原始配置和结果见 [基线报告](../server/evals/baselines/qwen3.6-flash-v2.1.0-2026-08-21.md)与[完整 JSON artifact](../server/evals/results/olist-business-v2.1.0-qwen3.6-flash.json)。这是一次本地工作区快照上的观测，不代表模型的普适准确率。

| 指标 | 改造前结果 |
|---|---:|
| Cases / Turns | 24 cases / 26 turns |
| Case pass rate | 4/24 = 16.67% |
| Fact recall | 46.15% |
| Business-term coverage | 82.05% |
| Execution success | 96.15%（25/26 turns） |
| Runtime validation pass | 95.83%（23/24 non-clarification turns） |
| Plan-intent accuracy | 23.53%（4/17 applicable turns） |

### 最重要的观察

**High execution success / validation pass did not imply business analysis correctness.**

系统几乎总能生成并执行代码，也几乎总能返回满足 `AnalysisResult` schema 的结果；但只有 4 个 case 通过，事实召回率只有 46.15%。这说明系统当时主要证明了：

1. 代码在运行时没有报错；
2. 输出满足结构化协议；
3. 输出中的字段和 metric ID 没有明显越界。

它没有证明：

1. GMV 是否使用了正确订单人群；
2. AOV 的 GMV 和订单数是否来自同一 scope；
3. rate/share 的分母是否符合业务定义；
4. payment 与 item 是否在安全粒度上 Join；
5. 结果中的数值是否对应 benchmark 要求的那个指标，而非另一张月度表中的相近数值。

这个 gap 很重要，因为用户看到的是一个“已验证、高置信度”的答案，而不是底层 execution pass。若语义错误仍能得到 high confidence，验证标签反而可能增加错误答案的说服力。

## 3. Error Analysis

### Scope / Population

多道题混用了不同分析人群。例如 `executive_business_snapshot` 要求已交付订单口径，但生成结果中的 GMV 使用全部 2017 订单支付，AOV 也使用更宽的人群，而已交付订单量使用 delivered scope。多个指标虽然分别能计算，却没有共享同一业务 scope。

这属于 **Agent/Product bug**：问题不是代码无法执行，而是用户问题中的人口范围没有成为下游必须遵守的合同。

### Grain

Olist 表具有不同事实粒度：

- orders：一行一笔订单；
- payments：一行一笔支付序列，一笔订单可能多行；
- items：一行一个订单商品项；
- reviews：一行一条评价记录，一笔订单可能多条；
- customers：当前样本通过 orders 中的 `customer_id` 与 `customer_unique_id` 表达不同身份含义。

失败 case 中，order、payment、item、review grain 经常没有在计划中显式表达。例如直接按 review 行计算均值，会让多评价订单拥有更高权重；直接连接 payment 和 item 两张事实表，则可能产生笛卡尔式金额放大。

这属于 **Agent/Product bug**。Data Profile 能提供行数、唯一值和候选键，但这些信号当时没有转化为 AnalysisPlan 中的强制粒度约束。

### Numerator / Denominator

`payment_structure_risk` 暴露了金额占比与订单占比混淆：

- 信用卡支付金额占比的分子和分母都应是 payment value；
- 多次支付订单占比的分子和分母都应是 distinct orders；
- 两者不能共享一个模糊的“占比”定义。

类似问题也存在于 delivery rate、repeat purchase rate 和其他 rate/share/ratio。旧 AnalysisPlan 只有自由文本 `aggregation` 和字符串 filters，不能明确表达 numerator、denominator 及其各自过滤条件。

这属于 **Agent/Product bug**。

### Join & Aggregation Order

`fact_table_join_audit` 要求审计 payment 与 item 两张事实表直接 Join 的膨胀风险。安全做法通常需要先分别聚合到 order grain，再连接 order-level 结果；若题目是审计直接 Join，则仍需要保存独立基准总额，明确“错误 Join”只用于测量膨胀。

旧计划没有 join relationship、左右粒度或 pre-join aggregation 字段。Code Generator 可以自行决定 Join 顺序，Validator 也不会检查聚合前后粒度是否改变。

这属于 **Agent/Product bug**。

### Benchmark / Scoring Issues

错误分析也发现了评测器本身的问题，不能把所有失败都归因于 Agent。

#### Delivery-rate 数值误匹配

v2.1.0 的 `executive_business_snapshot` reference delivery rate 是：

```text
14,429 delivered orders / 15,000 total orders = 0.961933...
```

生成答案的总体口径文字也是“已交付订单数 / 2017 年总下单订单数”，结果表中以百分数 `96.19` 保存。当前 scorer 会把整个 `AnalysisResult` 中的所有数字展平，再选择与 expected value 最接近的数字。由于 expected 使用 fraction，scorer 没有把 `96.19` 归一化成 `0.9619`，反而从月度趋势中选择了 `0.960558...` 作为 observed delivery rate，导致该 fact 失败。

因此，先前“这一题 delivery-rate denominator 与 reference 不一致”的概括并不被保存的 v2.1 artifact 支持。更准确的结论是：

- GMV/AOV 的 scope 错误是 **Agent/Product bug**；
- delivery-rate 失败主要是 **Benchmark/scorer bug**，具体是数值归属与 scale 未绑定；
- scorer 同样可能把月度 AOV 等相近数字误当作总体 AOV，尽管 Agent 的总体 AOV 本身也确实使用了错误 scope。

#### Term threshold 编写问题

`channel_quality_clarification` 预期覆盖三组术语中的两组，数学结果是 `0.666...`，但配置阈值写成 `0.67`，使正确的两组覆盖仍失败。这属于 **Benchmark authoring bug**，原始 v2.1.0 结果应保留，后续版本应单独修复和重评，不能回写历史结果。

## 4. Root Cause Investigation

### `executive_business_snapshot` 的真实链路

本次调查沿着以下路径追踪：

```text
User Question
  → Profile
  → Skill Retrieval
  → Metric Retrieval
  → AnalysisPlan
  → Code Generator
  → Sandbox
  → Validator
  → Final Answer
  → Benchmark Scorer
```

#### 1. Profile、Skill 和 Metric Retrieval 并没有完全失效

- 数据画像识别了 orders 中的 `order_id`、`order_status`、`order_purchase_timestamp`，以及 payments 中的 `order_id`、`payment_value`。
- Skill 选择链路在 Planner 之前执行；该问题能够触发时间趋势和指标诊断相关 playbook。
- Metric Retrieval 能检索到 `ecommerce.gmv` 和 `ecommerce.aov`，并把 amount/order 概念绑定到上传字段。
- `profiles`、`metric_matches` 和 compact skills 都会被序列化进入 Planner prompt。

需要说明的是：完整 benchmark JSON 主要保存最终 plan/result/validation，而不是每一步完整 retrieval payload；以上判断同时来自实际工作流代码、当时的逐链路调查和保存的计划/指标迹象，不应理解为 benchmark artifact 单独包含了全部中间状态。

#### 2. 信息进入 Planner，但没有形成计划约束

v2.1.0 artifact 中最终保存的计划是：

```json
{
  "intent": "other",
  "metric_ids": [],
  "required_columns": [],
  "dimensions": [],
  "filters": [],
  "aggregation": null,
  "time_grain": null,
  "steps": [],
  "assumptions": [],
  "needs_clarification": false,
  "clarification_question": null
}
```

旧 schema 中 `intent` 默认是 `other`，其余字段几乎都有空默认值，所以 `AnalysisPlan.model_validate({})` 可以通过。Pydantic 只确认“值的类型是否符合 schema”，不会自动判断“这个计划是否足以回答问题”。

#### 3. 空计划仍进入 Code Generator

旧工作流没有 `plan ready` gate。只要 Pydantic 成功生成 `AnalysisPlan`，LangGraph 就继续进入代码生成。

Code Generator 同时接收：

- 原始 User Question；
- 文件 headers/profile；
- analysis context 中的 plan、retrieved metrics、skills 和 memory。

因此当 plan 几乎为空时，Code Generator 仍能重新解释原始问题并自行决定过滤、Join 和指标口径。实际结果中：

- delivered order count 使用 delivered scope，得到正确的 14,429；
- GMV 使用所有 2017 订单支付，得到 2,439,323.73，而 reference delivered GMV 是 2,320,454.39；
- 总体 AOV 使用更宽 scope，结果表为 162.62，而 reference delivered AOV 是约 160.82；
- 月度趋势也使用 Code Generator 自己选择的计算口径。

这说明当时 Planner 没有真正决定 WHAT TO COMPUTE，只是 Code Generator 的可选上下文。

#### 4. Validator 为什么仍然 high confidence

Validator 的检查在其职责范围内大多确实通过了：

- 沙箱成功执行；
- 空的 `required_columns` 自然不存在 missing columns；
- 返回值满足 `AnalysisResult` schema；
- 空的 `metric_ids` 自然不存在 unretrieved metric ID；
- `columns_used` 都存在；
- 图表引用的数据集和字段有效。

这些属于 execution correctness 和 schema correctness，不是 semantic correctness。Validator 没有独立重算 delivered GMV、验证 AOV 分子分母 scope，或证明月度趋势与总体口径一致，因此返回了 `passed=true, confidence=high`。

### 根因总结

> **AnalysisPlan existed, but it was advisory rather than an enforceable analytical contract.**

Retrieval 成功不代表 Planner 一定采用；Planner 生成 schema-valid 对象不代表内容完整；Code Generator 看到 plan 不代表必须遵守；Validator 检查 artifact 合法不代表业务语义正确。

## 5. Design Decision

### 为什么没有直接调大模型

更强模型可能提高单次输出质量，但不能消除架构漏洞。只要空计划仍能进入代码生成，换模型只是降低失败概率，不是建立可靠边界；也无法解释错误发生在 retrieval、planning、execution 还是 validation。

### 为什么没有继续无限修改 prompt

Prompt 改进是必要工具，但纯 prompt 约束无法稳定代替程序化 gate。系统需要能明确回答：“这个 plan 是否具备进入代码生成的最低信息？”

### 为什么没有给 24 个 case 加特殊规则

按 case ID、Olist 字段或 expected value 编写规则会提高 benchmark 分数，却不能泛化到未知 CSV，还会污染产品逻辑与评测逻辑的边界。

### 为什么没有先构建复杂 Semantic Validator

如果 Planner 连 scope、grain、metric、denominator 和 Join 都没有显式表达，Validator 没有稳定的合同可验证。先写复杂 semantic checks 会迫使 Validator 再次猜测用户意图，重复 Planner 的工作。

### 为什么先强化 Planner

本阶段采用的职责划分是：

> **Planner decides WHAT to compute.**
> **Code Generator decides HOW to implement it.**

AnalysisPlan V1.5 增加了：

- `analysis_scope`：分析包含什么人群或记录；
- `entity_grain`：一个分析实体代表什么；
- `metrics`：本题需要输出哪些指标；
- `numerator / denominator`：rate/share/ratio 的语义组成；
- structured `filters`：数据表、字段、操作符和值；
- `time_field / time_grain`：时间字段和汇总粒度；
- minimal `joins`：左右数据表、键、粒度、关系和必要的预聚合说明；
- ordered `steps`：按顺序描述分析过程的自然语言步骤。

### 为什么 V1.5 不是完整 Analytics DSL

V1.5 的目标是形成“足够完整、可读、可检查”的分析合同，而不是构建新的查询语言：

- scope、grain、metric definition 和 calculation 仍是自然语言；
- numerator/denominator 是结构化语义描述，不是表达式树；
- steps 是有序自然语言，不是 operation DSL；
- JoinSpec 只保留识别 grain inflation 所需的最小字段；
- 没有修改 `AnalysisResult` 或要求前端理解新的执行协议。

这保留了对未知 CSV 的泛化能力，也避免第一阶段同时重构 Planner、Code Generator、Validator 和 UI。

## 6. Completeness Gate

核心原则是：

> **Schema Valid ≠ Plan Ready**

新的控制流是：

```text
Planner
  ↓
Schema Validation
  ↓
Completeness Gate
  ↓
Ready?
  ├─ Yes → Code Generation
  └─ No  → Replan once with structured missing items
              ↓
          Still incomplete?
              ├─ Genuine ambiguity / missing evidence → Clarification
              └─ Planner omission or conflict         → Stop safely
```

Gate 当前检查的重点包括：

- executable plan 是否具有 scope、grain、required columns 和 ordered steps；
- aggregation/ranking/trend/cohort/metric diagnostic 是否定义了 planned metrics；
- rate/share/ratio 是否包含 numerator 和 denominator；
- structured filters 引用的数据表、字段和值是否合法；
- trend/cohort 是否包含 time field 与 time grain；
- 多表计划是否包含连接这些数据表的 Join；
- many-to-many Join 是否说明 pre-join aggregation 或 audit-only 处理；
- 非空 metric ID 是否来自 retrieved metrics；
- `metric_ids` 是否与 `metrics[].metric_id` 保持一致；
- 直接匹配且字段完整的 retrieved metric 是否被 Planner 静默遗漏。

第一次 gate fail 时，系统把结构化 issue code、field 和 message 回传给 Planner，最多 replan 一次。Planner 漏填已有信息不应打扰用户；只有缺字段、缺业务定义、未知实体或会改变结论的歧义才进入 clarification。第二次仍不完整时，LangGraph 直接结束本轮，不调用 Code Generator。

这个设计首先解决的不是“让所有题都完成”，而是“不再让格式合法但内容空洞的计划继续生成看似可信的代码和答案”。

## 7. Implementation

本阶段改动被限制在 Planner 合同、Planner 服务、LangGraph 截止路由以及直接相关测试。

### `server/app/schemas/analysis.py`

- 新增 `PlanFilter`、`MetricOperand`、`PlannedMetric`、`JoinRequirement`。
- `intent` 改为必填，并移除默认 `other`。
- 在 `AnalysisPlan` 中加入 scope、grain、metrics、time field 和 joins。
- 保留旧 `aggregation` 字段，以减少对既有 metadata/readers 的破坏，但 V1.5 的指标语义以 `PlannedMetric` 为主。
- 新增 `PlanCompletenessIssue` 和 `PlanCompletenessReport`，将 schema validity 与 readiness 分离。

### `server/app/services/plan_service.py`

- 新增 `evaluate_plan_completeness()`。
- 扩展 Planner prompt，明确 V1.5 contract 和 clarification 边界。
- 对 schema-invalid 或 incomplete plan 最多进行一次 replan。
- 将 gate issues、attempts、usage、guard 和 completeness 写入 planner metadata。
- 若两次仍失败，返回明确的 incomplete 状态，不构造可继续执行的假计划。

### `server/app/services/agent_service.py`

- 保持现有 LangGraph 主节点结构，不新增 Agent。
- `plan_analysis` 后重新执行 completeness gate。
- incomplete plan 路由到 `finalize_response`，不进入 `generate_code`。
- legitimate clarification 继续进入既有 clarification 节点。

### Planner tests

直接相关测试覆盖：空 plan、aggregation 无 metric、ratio 无 denominator、trend 缺时间、多表无 Join、many-to-many 无预聚合、retrieved metric 被遗漏、合法 clarification、replan 后通过、replan 后仍失败，以及 Agent Graph 不调用 Code Generator 的截止行为。

### Planner-only evaluation runner

新增 [run_planner_eval.py](../server/evals/run_planner_eval.py)，只执行：

```text
Question → Profiles → Skill/Metric Retrieval → Planner → Completeness Gate
```

它不读取 expected facts，不调用 Code Generator、Sandbox 或完整 benchmark scorer，用于隔离观察 Planner 输出质量。

### 本阶段明确没有修改

- `code_service.py` / Code Generator；
- `validation_service.py` / semantic validation；
- `AnalysisResult`；
- Python Sandbox；
- Frontend；
- benchmark expected values；
- 完整 benchmark scoring。

这一边界很重要：Planner-only 结果不能被解释为端到端准确率变化，也不能声称 Code Generator 已经被强制逐字段执行 V1.5 plan。

## 8. Validation & Results

### 自动测试

本地验证结果：

- 63 backend tests passed；
- Python compile check passed；
- `git diff --check` passed。

这些测试证明 schema、gate、一次 replan 和 LangGraph 截止路由按当前测试合同工作；它们不证明 24 个业务题已经算对。

### Planner-only 8-case evaluation

改造后使用项目当时 `.env` 中的 `openrouter/free` 运行 8 个代表性 case。该路由可能在不同请求中选择不同免费模型，因此这不是 fixed-model accuracy claim。

| 结果 | 数量 |
|---|---:|
| Ready for Code Generation | 0 |
| Legitimate Clarifications | 2 |
| Blocked as Incomplete | 6 |
| Cases that Replanned | 7 |

逐题概况：

| Case | Planner-only 结果 |
|---|---|
| `executive_business_snapshot` | fallback plan 缺 scope、grain、metrics、time 和 Join，被拦截 |
| `monthly_peak_diagnosis` | trend plan 缺 metrics、time 和 Join，被拦截 |
| `payment_structure_risk` | 有 delivered scope 和 payment Join，但缺 required columns 与 planned metrics，被拦截 |
| `fact_table_join_audit` | 生成了审计步骤，但包含未检索 metric IDs、ratio 缺 operands、Join cardinality 可疑，被拦截 |
| `review_grain_audit` | 表达了 order-level review aggregation，但遗漏被 gate 视为适用的 retrieved metric，被拦截 |
| `customer_identity_audit` | 计算逻辑只写在 steps，缺 metrics 和 required columns，被拦截 |
| `channel_quality_clarification` | 缺 channel 字段，合法停止并请求补充 |
| `profit_metric_clarification` | 缺 cost evidence，合法停止并请求补充 |

### Iteration 2 — Planner Stability Diagnosis

为排除 `openrouter/free` 动态路由造成的模型不可比问题，Planner-only suite 随后固定使用 `qwen/qwen3.6-flash`，对同一组 8 cases 连续运行三次并分别保存 artifact。三轮结果完全一致：first-attempt schema valid `0/8`、any-attempt schema valid `0/8`、ready `0/8`、legitimate clarification `2/8`、replan `8/8`；所有最终 Plan 均来自 `deterministic_incomplete_fallback`。

**Updated interpretation：**三轮最终 Plan 的 100% consistency 是 deterministic fallback consistency，不是 LLM Planner consistency。因此目前不能再把 schema-valid 为零主要归因于 `openrouter/free` 的动态路由。Gate 中的 `missing_analysis_scope`、`missing_metrics` 等 issue 也是对 fallback Plan 的检查结果，不能据此证明 Qwen 的原始业务计划遗漏了这些语义。

对最近一轮 `executive_business_snapshot` 的 attempt metadata 检查显示：Attempt 1 在 JSON 解析阶段失败，错误为 `Expecting ',' delimiter: line 93 column 6 (char 3712)`；Attempt 2 未找到 JSON object。两次都没有进入 Pydantic field validation。当前 artifact 保存了 error 和 token usage，但没有保存 raw `message.content`、HTTP 400 后是否移除 `response_format`、provider/model response metadata 或 `finish_reason`。两次 completion 都接近当前 3,500-token 上限，但没有 `finish_reason` 和 raw response，暂时不能确认是否由截断、structured-output compatibility 或其他响应行为造成。

随后使用临时、环境变量门控的 instrumentation，仅重跑一次固定 `qwen/qwen3.6-flash × executive_business_snapshot`。两个 attempt 都由 Alibaba provider 返回 HTTP 200，初始请求均携带 `response_format=json_schema`，且没有触发 HTTP 400 后的 prompt-only fallback；但两次 `finish_reason` 和 `native_finish_reason` 都是 `length`，约 3,500 个 completion tokens 全部计入 reasoning，最终 `message.content` 均为空。由此确认本次失败是 **token truncation before final structured content**：structured-response 请求路径确实被接受，但模型在输出最终 JSON 前耗尽预算，因此不存在可以定位断点的 raw JSON，也没有进入 Pydantic。临时 instrumentation 在诊断后已移除，debug artifacts 保留在 git-ignored 的 `server/evals/results/` 中。

当前状态是 **diagnosis in progress**。真正待诊断的问题已从“Qwen 是否漏填业务语义”前移为“真实 LLM response 为什么无法通过 AnalysisPlan V1.5 的 JSON/schema 入口”。下一步仅对 `executive_business_snapshot` 做单 case debug，保留两个 raw attempts、实际请求分支、response metadata、finish reason、解析阶段和精确 Pydantic errors；在获得这些证据前不调整完整 benchmark，也不把问题写成已解决。

**Updated after the single-case debug：**上述 raw-attempt 采集已完成；当前这次失败的直接原因已经确认，但修复尚未验证。下一步最小实验应保持模型、case、schema、prompt 和 gate 不变，只降低/关闭 Planner reasoning effort，为最终 JSON 保留 completion budget；若 provider 不支持该控制，再单独提高 completion token limit。每次只改变一个变量并继续记录 `finish_reason`、reasoning tokens 和 raw content。

**Single-variable reasoning-off experiment：**Planner request 随后只增加了 `reasoning={"effort":"none","exclude":true}`；模型仍为 `qwen/qwen3.6-flash`，`max_tokens=3500`，prompt、AnalysisPlan V1.5 schema、Metric Retrieval 和 Completeness Gate 均未改变。只运行一次 `executive_business_snapshot`，保留最多两个 attempts。两次均由 Alibaba provider 正常返回非空内容，`finish_reason=stop`、reasoning tokens 为 `0`；Attempt 1 使用 1,964 completion tokens，Attempt 2 使用 1,010 completion tokens。两份内容都成功提取并解析为 JSON，也都进入了 Pydantic，因此此前由 reasoning 耗尽预算造成的空响应和 JSON 入口失败已经消失。

这次实验仍未产生 schema-valid Plan。Attempt 1 有 27 个 validation errors，主要是自定义 `intent`、把字符串 `analysis_scope` 写成对象、指标字段命名/枚举不匹配，以及 Join 字段结构不匹配。收到结构化 retry feedback 后，Attempt 2 收敛到 7 个 errors：`analysis_scope` 仍为对象；`metrics[0..3].calculation` 缺失；`metrics[2].metric_type=count_distinct` 不在允许枚举中；`joins[0].relationship` 缺失。因为两次 LLM 输出都在 Pydantic 层失败，真实 LLM Plan 没有进入 Completeness Gate；最终返回的仍是 `deterministic_incomplete_fallback`，其 `missing_analysis_scope`、`missing_metrics` 等 Gate issues 不能解释为本轮 Qwen 输出的 completeness 结果。

**Updated interpretation：**关闭 reasoning 解决了 token/response 层的首要阻塞，使诊断首次到达 Pydantic，但没有直接把该 case 变成 schema-valid。当前失败层已经从“没有 final content”后移为“模型生成的 JSON 结构与 AnalysisPlan V1.5 contract 不一致”。本轮只证明单变量作用，不证明 Planner 业务语义正确，也没有运行 8-case suite 或完整 benchmark。原始响应与结果保存在 git-ignored artifact `server/evals/results/planner-v15-qwen-executive-reasoning-off-20260824.json`；当前状态仍为 **diagnosis in progress**。

**Strict V1.5 skeleton experiment：**在继续固定 `qwen/qwen3.6-flash`、reasoning disabled、`max_tokens=3500`、AnalysisPlan V1.5 schema、Metric Retrieval、Completeness Gate 和 `executive_business_snapshot` 的前提下，Planner prompt 只增加了一个不含 Olist expected values 的通用 JSON field-shape skeleton，并明确列出 intent、metric type、value scale、`count_distinct` 和 Join 字段约束。单次运行仍使用原有最多两个 attempts。Attempt 1/2 均正常结束，reasoning tokens 为 `0`，分别使用 1,867/1,815 completion tokens；两次 JSON 都成功解析并进入 Pydantic。

Skeleton 将 schema mapping errors 从上一实验的 27/7 个收敛为两次各 1 个：`aggregation` 被模型写成包含 `group_by` 和 `metrics` 的对象，而当前 V1.5 schema 要求 `string | null`。因此本轮仍是 schema-invalid，真实 LLM Plan 仍未进入 Completeness Gate，最终返回 deterministic fallback。该实验说明严格 skeleton 显著改善了字段映射，但尚未把故障层完全推进到 completeness/semantic validation；也不能据此判断生成计划中的 scope、metric denominator 或 Join 语义正确。完整 raw responses 保存在 git-ignored artifact `server/evals/results/planner-v15-qwen-executive-strict-skeleton-20260824.json`，当前状态继续标记为 **diagnosis in progress**。

**Legacy aggregation rule experiment：**下一轮继续保持模型、reasoning、token limit、schema、retrieval、gate、case 和 skeleton 不变，只在 Planner prompt 明确规定顶层 `aggregation` 是 V1.5 legacy compatibility field，必须为 `null`，grouping 应进入 `dimensions/time_field/time_grain`，指标计算应进入 `metrics`。单次评测的 Attempt 1 首次生成 schema-valid Plan，并进入 Completeness Gate；Gate 仅报告 `dimensions` 中的 `month_of_year` 不是 profile 内真实列。现有一次自动 replan 随后生成的 Attempt 2 同样 schema-valid，也得到相同 Gate issue。因此最终结果为 `llm_structured_output_incomplete`，而不是 deterministic fallback。

这证明此前的 token truncation 和 schema mapping 两层阻塞均已在该单 case 中消除，诊断已经推进到 completeness layer；但 Plan 仍未 ready。最终 LLM Plan 已完整填写 scope、order grain、四个 metrics、结构化 filters、月度 time spec，以及 orders-to-payments Join 和 payment pre-aggregation；`dimensions=["month_of_year"]` 是唯一 completeness failure。该结果只说明字段存在且通过类型检查，不证明 delivered population、GMV/AOV scope、delivery-rate denominator 等业务语义正确。本轮在首次得到 schema-valid Plan 后停止继续优化，也没有运行 8-case suite 或完整 benchmark。Artifact 保存在 `server/evals/results/planner-v15-qwen-executive-legacy-aggregation-rule-20260824.json`。

**Time-dimension mapping experiment：**下一轮只增加一条通用 Planner rule：`dimensions` 只能包含 profile 中真实存在的非时间业务列，时间分组仅由 `time_field + time_grain` 表达；即使是 state × month，`dimensions` 也只保存真实 state 列。其余模型、reasoning、token limit、schema、strict skeleton、legacy aggregation rule、retrieval 和 gate 均不变。`executive_business_snapshot` 在 Attempt 1 即生成 schema-valid Plan，并首次得到 `ready_for_code_generation=true`、Gate `issues=[]`；Planner 因此直接返回，没有 Attempt 2，也没有运行 Code Generator。

该 Plan 使用空 `dimensions` 和 `order_purchase_timestamp/month` 表达月度趋势，并填写了 scope、order grain、四个 metrics、2017 filters、orders-to-payments Join、payment pre-aggregation 和有序 steps。这说明该单 case 已依次越过 token、schema mapping 与 completeness 三层阻塞。不过 `ready` 仍只代表当前 Gate 检查通过：scope 文本对 delivered 与 all-orders population 的描述仍可能不一致，GMV/AOV scope 和 delivery-rate denominator 也尚未经过 semantic validation。本轮没有继续优化或运行完整 benchmark。Artifact 保存在 `server/evals/results/planner-v15-qwen-executive-time-dimension-rule-20260824.json`。

**Universal Planning Semantics experiment：**在不改 schema、gate、Skills、Metric Retrieval、Code Generator、Validator 或 benchmark 的前提下，Planner prompt 增加了七条通用语义规则，覆盖 broadest base population、filter locality、metric-specific populations、denominator preservation、population-safe joins、business-event time 和 overall/trend consistency。固定 `qwen/qwen3.6-flash`，只对 `executive_business_snapshot`、`monthly_peak_diagnosis` 和 `payment_structure_risk` 各独立运行三次 Planner-only；没有运行 Code Generator 或完整 benchmark。三轮 artifact 分别保存在 git-ignored 的 `server/evals/results/planner-v15-universal-semantics-run-{1,2,3}-20260824.json`。

九个最终 Plan 均 schema-valid、`ready_for_code_generation=true`、Gate `issues=[]`，其中 `payment_structure_risk` 第 1 轮和 `monthly_peak_diagnosis` 第 3 轮经过一次 replan；没有 clarification 或 blocked case。该结果说明新增规则没有破坏结构化输出和 completeness，但**不能解释为 semantic accuracy 已提升**：

- `executive_business_snapshot` 三轮都选择 purchase time，但只有前两轮以全部 2017 orders 为 base population 并使用 left join；第 3 轮缩窄为有 payment 的订单并使用 inner join。前两轮 GMV/AOV 又没有稳定限定 delivered population，因此 benchmark reference 所需的 delivered GMV/AOV 仍未被一致表达。
- `monthly_peak_diagnosis` 三轮都使用 delivered-order population，但也都选择 `order_delivered_customer_date`；当前 benchmark reference 按 `order_purchase_timestamp` 归月。Join 也在一轮 inner、两轮 left 之间变化，所以结果是“稳定生成计划”，不是“稳定遵循 reference 时间口径”。
- `payment_structure_risk` 三轮都区分了 payment-amount share 与 order-level multi-payment ratio，并写出分子分母；但顶层 entity grain 在 order、声称 join 后一单一行、payment transaction 三种表述之间变化，Join 也在 left/inner 间变化。第 1 轮还把 `payment_sequential >= 2` 放在 metric-level filter，和 steps 中“先按订单计数再筛多次支付”的表述冲突。

**Updated interpretation：**Planner 的主要诊断层已从 token/schema/completeness 推进到 business semantics。U1-U7 对显式 operands、purchase-time selection（executive）和 Join 风险描述有帮助，但自然语言规则仍不能保证不同运行中的 population、metric scope、event time 和 baseline preservation 一致；当前 Gate 也不检查这些语义。下一步应先做最小的 Planner semantic disambiguation，而不是把 `9/9 ready` 当成端到端改进。`candidate metrics → selected metrics` 仍作为独立后续项保留，本轮没有设计或修改。

**Metric Knowledge Layer phase 1：**为减少 Planner 临场猜测业务口径，本轮没有继续修改 Planner prompt、Gate、Skills、Code Generator 或 Validator，而是打通 Metric Definition → Retrieval → Planner context：现有 `time_concept` 现在会产生带 resolved/unresolved 状态的 profile field candidates；`MetricDefinition` 仅新增可选的 `default_population` 与 `denominator_policy`；显式 `project_id=olist` 会加载 Olist project override，并记录 domain defaults、effective defaults、project policies 和 binding provenance。Olist override 只定义 completed order、默认 purchase/order event、`paid_amount → payment_value` 和 order-level payment pre-aggregation；未传 project ID 时不会应用。

第一批只补强或新增 `ecommerce.payment_gmv`、`ecommerce.aov`、`ecommerce.delivery_rate`、`ecommerce.payment_method_amount_share` 和 `ecommerce.multi_payment_order_rate`。42 个相关后端测试通过，JSON/compile/diff checks 通过。随后固定 `qwen/qwen3.6-flash`，对 Executive、Monthly Peak 和 Payment Structure 各运行三次 Planner-only；三个 artifact 独立保存在 git-ignored 的 `server/evals/results/planner-v15-metric-knowledge-run-{1,2,3}-20260824.json`，没有运行 Code Generator 或完整 benchmark。

九次结果中，8 次至少生成过 schema-valid LLM Plan，5 次最终 ready。`monthly_peak_diagnosis` 三轮均首次 schema-valid/ready，稳定采用 delivered population、`order_purchase_timestamp/month`、left join 和 payment pre-aggregation；这修正了上一轮三次都选择 delivery time 的现象。`executive_business_snapshot` 三轮均生成 schema-valid Plan并稳定采用 purchase time、all-orders delivery denominator、left join 和预聚合，但三轮都被 `omitted_retrieved_metric=ecommerce.gmv` 拦截：问题同时检索到了更具体的 `payment_gmv` 与通用 `gmv`，Planner选择前者，既有 Gate 又要求所有直接命中的 fully-bound metric 不得遗漏。这是 candidate retrieval 与 selected metric coupling，不是时间绑定失败。Executive 的 delivered GMV/AOV population 仍只有两轮一致，另一轮仍采用 all-orders scope。

`payment_structure_risk` 前两轮首次 schema-valid/ready，稳定检索 amount-share 与 order-rate 两个不同 grain 的指标，并使用 delivered-payment population；第 3 轮两次都因模型输出未支持的 `operator="gt"` 而 schema-invalid，最终 fallback 被 Gate 拦截。前两轮虽然区分了金额分母与订单分母，但一个结构化 metric 仍可能把 credit card 与 boleto 合在同一 numerator，或只在 steps 而非 operand 中表达“payment rows > 1”。因此本阶段说明 Metric Knowledge 能改善部分 time/population consistency，但没有解决 metric instantiation、candidate selection、schema enum stability 或 semantic enforcement。

**Updated interpretation：**`time_concept` 已真实到达 Planner，Olist 下有效绑定为 `order_purchase_timestamp`；AOV 的 effective time/population/denominator 也能覆盖 domain default。原始用户问题仍与 precedence metadata 一起进入 Planner，设计上保持 user explicit > project override，但本组三题没有显式指定另一时间事件，因此尚未实证用户覆盖行为。Project override 只能通过显式 ID 启用，直接测试确认 domain-only retrieval 不会误用 Olist。当前不继续自动修复 Executive 的 duplicate metric retrieval 或 Payment 的 schema/instantiation 问题。

**Candidate Metric Decision experiment：**为解除 Retrieval 与 Completeness Gate 的强耦合，本轮将 retrieved metrics 明确定义为 candidates，并增加最小 selected/rejected decision contract。Runtime match metadata 现在区分 `exact` 与 `token_overlap`，标记 `decision_required`，并只对明显的 nested alias 做保守 shadow；retrieval score 继续用于排序，不再代表业务适用度。Gate 只要求 decision-required candidates 被 selected、rejected 或 clarification 闭环，同时检查 selected/rejected 来源、冲突和 supersession 引用；原先“所有直接命中且 fully bound 的指标都必须 selected”的规则已删除。没有修改 Metric Knowledge、project overrides、Skills、Code Generator、Validator 或 benchmark。

固定 `qwen/qwen3.6-flash` 后，对 `executive_business_snapshot`、`review_grain_audit`、`monthly_peak_diagnosis` 各独立运行三次 Planner-only。每轮结果均为 2 ready、0 clarification、1 blocked、1 replan；72 个后端测试通过。三个独立 artifact 保存在 git-ignored 的 `server/evals/results/planner-candidate-decision-run-{1,2,3}-20260824.json`。

- Executive 中 `payment_gmv` 三轮均为 decision-required exact candidate；通用 `gmv` 因其 `GMV` alias 被更具体的“支付GMV”短语遮蔽，三轮均为 non-mandatory candidate。Planner稳定选择 `payment_gmv + aov + delivery_rate`，不再因遗漏 generic GMV 被 Gate 拦截，且三轮均首次 attempt ready。
- Monthly Peak 中 `gmv` 与 `aov` 三轮均被稳定选择；`payment_gmv` 仅为 token-overlap、`decision_required=false`，可以无解释省略，三轮均首次 attempt ready。
- Review Grain 中 `order_count` 三轮均为 decision-required exact candidate。Planner 的第一次 attempt 都是 schema-valid，但既未选择也未写入 `rejected_metrics`；replan 又发生 schema failure，最终均以 `unresolved_metric_candidate` 安全停止。因此 rejection contract 和 Gate 行为已验证，但尚不能声称 Planner 会稳定采用 rejection contract。

**Updated interpretation：**candidate retrieval 不再等同于 mandatory selection，Executive 的 duplicate-candidate coupling 已解除；同时，Review Grain 表明“提供 rejection 字段”不等于模型会使用它。当前剩余问题位于 Planner candidate-decision adoption / structured replan stability，而不是继续放宽 Gate。此次实验没有运行 Code Generator 或完整 benchmark，也没有证明端到端准确率提高。

**Metric instantiation 单案例实验：**只在 Planner prompt 中增加一条通用规则：当 planned metric 与 retrieved candidate 的公式、实体和粒度相同，仅增加查询特定过滤、子群或更窄 population 时，应视为该 candidate 的实例并填写对应 `metric_id`；只有业务含义或公式、实体、粒度实质不同时才 reject。随后固定 `qwen/qwen3.6-flash`、`project_id=olist`，仅运行一次 `review_grain_audit` Planner-only，保留既有最多两次 attempts，artifact 位于 git-ignored 的 `server/evals/results/planner-metric-instantiation-review-grain-20260825.json`。

本次 A1、A2 都未通过 schema validation，且错误相同：`metrics.2.numerator.filters.0.operator` 输出了 schema 不支持的 `gt`；`metrics.2.denominator.aggregation` 输出了 `null`，但 schema 要求 string。因此实验在 schema mapping 层停止，没有得到可供 Gate 检查的真实 LLM Plan；最终 deterministic fallback 仍被 `missing_analysis_scope`、`missing_entity_grain`、`unresolved_metric_candidate` 和 `missing_join_requirement` 拦截。现阶段不能根据 fallback 判断 metric-instantiation 规则有效或无效，也不能声称 `order_count` 已被正确选择。下一步应继续保持单案例与其他变量不变，先做一个最小的 operand/filter schema-mapping 实验，使严格大于整数阈值映射为等价的受支持表达（例如 `> 1` 表达为 `gte 2`），并确保每个 operand 的 `aggregation` 为 string；在获得 schema-valid Plan 后再评估 metric instantiation。

**Schema-mapping guidance follow-up：**下一次单变量实验只强化 Planner 的字段格式说明：列出受支持的 filter operators，将整数条件 `> 1` 明确映射为 `gte 2`，并要求每个 `MetricOperand.aggregation` 都是非空 string、禁止 `null`。固定模型、项目和 case 不变后，A1 首次成为 schema-valid LLM Plan 并真实进入 Gate；其唯一 issue 是 `unresolved_metric_candidate=ecommerce.order_count`，因此既有机制执行了一次 replan。A2 也 schema-valid，按 `order_id` 统计 review rows、筛选 review count > 1 的 ordered steps 表达正确，但它没有将 `orders_with_multiple_reviews` 绑定到 `ecommerce.order_count`，而是显式 reject 该 candidate，理由是 retrieved definition 指向 valid/completed orders，而用户问题关注 review-grain audit。该 rejection 满足当前 decision contract，所以 A2 通过 Gate并得到 `ready_for_code_generation=true`。

这说明 schema-mapping 阻塞已在本次运行中消失，但预设的 metric-instantiation 成功标准没有达到：最终 `metric_ids=[]`、目标 metric 的 `metric_id=null`、`rejected_metrics` 包含 `ecommerce.order_count`。当前失败层已经从 schema mapping 推进到 Planner 对“通用订单计数定义”与“查询特定重复评价订单计数”之间继承关系的业务语义判断；Gate 本身按现有 contract 正常接受了合法 rejection。本次没有继续修改 prompt、Gate 或 retrieval，也没有运行 Code Generator 或完整 benchmark。Artifact 位于 git-ignored 的 `server/evals/results/planner-metric-instantiation-schema-guidance-review-grain-20260825.json`。

**Current 8-case Planner-only checkpoint：**在接受 Review Grain 的 strict metric identity/rejection 作为合法策略后，使用当前实现、固定 `qwen/qwen3.6-flash` 和 `project_id=olist` 将既有 8-case suite 重跑一次。结果为 5 ready、2 legitimate clarifications、1 blocked、2 replans；所有 case 最终都有 schema-valid LLM Plan，没有 deterministic fallback。Executive、Monthly Peak、Payment Structure 和 Customer Identity 正确完成 mandatory candidate selection，Profit 对缺少成本字段的 gross-profit candidate 做了显式 rejection；Review Grain 本轮 replan 后既未 select 也未 reject `order_count`，仍因 `unresolved_metric_candidate` 被阻止，说明 candidate decision adoption 尚不稳定。

Metric Knowledge 与 Olist override 在本轮继续把 Executive/Monthly 的时间绑定到 `order_purchase_timestamp`，并在 Executive 中形成 delivered GMV/AOV、all-orders delivery denominator、payment pre-aggregation 与 left join 的自洽计划。不过 ready 不等于 semantic correctness：Monthly 使用 inner join，可能在计算订单量/AOV denominator 前删除没有 payment match 的 delivered orders；Payment 的 structured operand 用 `payment_sequential >= 2`，而 steps 使用“按 order_id 统计 payment rows > 1”，两种定义依赖额外等价假设；Fact Join Audit 的 JoinSpec 描述 safe pre-aggregated joins，但同时要求计算 naive direct-join inflation，且用 string `"null"` 填充不适用的 operand aggregation；Customer Identity 的 `>1 order` 条件主要留在 calculation/steps，没有完整进入 operands。两个 clarification 也存在停止前的替代口径草案：Channel 把地域当作渠道 proxy，Profit 把 freight 当作成本 proxy；deterministic guard 最终阻止了这些草案进入执行。本轮 artifact 位于 git-ignored 的 `server/evals/results/planner-current-8case-suite-20260825.json`，没有运行 Code Generator 或完整 benchmark。

**Website Project Context experiment：**真实网站此前没有在 QueryRequest 中传递 `project_id`，所以即使 Olist override 已存在，Metric Retrieval 仍以 `project_id=null` 运行。本轮只补齐可选的 website URL context → frontend request → FastAPI QueryRequest → query route → Agent state → Metric Retrieval 链路；测试页面通过显式 `?project_id=olist` 启用项目上下文，不根据文件名推断，未提供参数的普通分析仍保持 domain-only 行为。最终 workflow metadata 记录实际 `project_id`，每个 retrieved metric 的既有 `knowledge_context` 继续记录 effective values、project policies 和 applied override provenance。没有修改 Planner prompt/schema、Gate、Metric Knowledge、Project Override、Skills、Code Generator 或 Validator。

真实网站重新上传两份 Olist 2017 CSV 并只运行一次 `executive_business_snapshot`，run ID 为 `44cbc1d6-9721-47e8-8ac8-12d2afd8523e`。Artifact 与 Trace 均确认 `project_id=olist`；AOV、Payment GMV 和 Delivery Rate 的 effective context 已分别加载 completed-order population、completed-order denominator policy、all-orders delivery denominator，以及 purchase/order time 和 payment pre-aggregation policy。因此 Project Context 链路和 override provenance 已打通。

但 Planner 虽然 schema-valid、Gate ready，仍把 Payment GMV 写成所有 scope orders 的 `sum(payment_value)`，把 AOV 写成所有 scope orders 的支付额除以 distinct orders，没有采用 retrieved override 中的 delivered/completed population。Code Generator随后按这个错误 Plan 汇总全部订单支付，并额外把 Plan 的年末边界 `2017-12-31T23:59:59` 实现成 `<= '2017-12-31'`，漏掉 12 月 31 日午夜后的订单。网站结果表聚合后为 14,411 delivered orders、2,436,736.45 Payment GMV、162.67 AOV、96.20% Delivery Rate，未达到 benchmark reference。Updated interpretation：本轮证明了 project context transport 已解决，但没有证明 override adoption 或端到端准确率提升；第一处业务语义错误仍在 Planner，另有独立的 Plan-to-Code 时间边界偏差。按单变量约束，本轮没有继续修改 Code Generator、Validator 或前端已知展示问题。

**Selected-metric grounding contract experiment：**下一轮只在 Planner prompt 增加通用 grounding contract：一旦 candidate 被选为 `metrics[].metric_id`，其 effective population、denominator 和 resolved time semantics 就是默认业务合同；Planner 必须按 user explicit > effective project semantics > domain default > clarification 的优先级，将它们落实到 metric/operand filters、calculation、steps、time field 和 denominator-preserving join order。没有修改 AnalysisPlan schema、Gate、Retrieval、Metric Knowledge、Olist override、candidate decision、Skills、Code Generator、Validator 或 benchmark。

固定 `qwen/qwen3.6-flash`、`project_id=olist` 后，仅运行一次 `executive_business_snapshot` Planner-only，artifact 位于 git-ignored 的 `server/evals/results/planner-selected-metric-grounding-executive-20260825.json`。Attempt 1 因 `metrics.1.denominator.aggregation=null` schema-invalid；既有 replan 后 Attempt 2 schema-valid、Gate ready。最终 Plan 正确采用了 `order_purchase_timestamp/month`、payment pre-aggregation、left join、AOV delivered numerator/denominator，以及 Delivery Rate 的 all-orders denominator；但 selected `ecommerce.payment_gmv` 仍写成所有 eligible scope orders 的 `sum(payment_value)`，没有 materialize completed-order filter。因此九项预设成功标准只满足八项，不能声称 selected-metric grounding 已解决。

Updated interpretation：继续增加 prompt 规则已出现边际不足。当前第一处失败仍是 Planner grounding/adoption：effective Payment GMV population 已到达 prompt，但分散在 `default_population`、project policy 和 field bindings 中，模型没有稳定编译为结构化 PlanFilter。下一步应优先验证将 effective population、denominator、time binding 和 provenance 预先整理为更直接的 Planner grounding context，而不是继续扩充自然语言规则；本轮按约束停止，没有运行 Code Generator 或完整 benchmark。

### 正面结果

- 空计划和不完整计划不再进入 Code Generation。
- 两个真正缺少业务证据的 case 正确进入 clarification。
- Gate 将原本会被 Code Generator 隐式补全的问题显式暴露出来。
- Planner failure 可以按 schema、scope、metric、time、join 等 issue 分类，不再只有最终答案“对/错”。

### 不能声称的结果

- **不能声称 Planner 准确率提升。**本次 8 题没有任何计划达到 ready。
- **不能声称端到端 benchmark 提升。**本阶段没有重跑完整 24 题，也没有改 Code Generator。
- **不能声称 semantic correctness 已解决。**Completeness 只证明关键字段存在，不证明内容正确。

### Remaining problems

- `openrouter/free` 下 structured planning 不稳定，部分 case 两次都无法得到可用的 schema-valid plan。
- Planner 有时把重要计算写进 `steps`，却没有形成 `metrics` 合同。
- Join cardinality 仍可能判断错误，例如把一对多误写为一对一。
- Metric Retrieval 与 gate coupling 偏强；误召回 metric 可能导致本来合理的 plan 被判定为遗漏指标。
- 自然语言 scope、grain 和 calculation 仍不能被完整机器验证。
- Completeness 不等于 semantic correctness，后续仍需要让 Code Generator 遵守 plan，并逐步增加 semantic checks。

### Compatibility boundary

旧 checkpoint 或 fixture 中的 `intent="other"`、字符串 filters 或近乎空白的 plan 不再满足 V1.5 readiness。当前实现选择明确失败或停止，而不是静默把旧内容转换成可能错误的新语义。历史 metadata 仍可作为记录读取，但不应假定能够重新进入新执行链路。

### Iteration 3 — Single Resolved Metric Contract

Architecture redundancy audit 发现，Planner 同时收到 domain defaults、project override、effective values、field-binding candidates 和完整 `knowledge_context`，因此同一 population、denominator 或 time semantics 仍有多个可重新解释的入口。本轮在现有 Metric Service 内增加 `ResolvedMetricContract` / `ResolvedMetricCandidate` 投影，将 MetricDefinition、显式 Project Override、concept binding 和 effective semantics 解析成单一 Planner-facing contract。原有 compact MetricMatch 与完整 `knowledge_context` 仍保留在 Agent metadata 和 planner-eval artifact 中用于 Trace；Code Generator、Validator、AnalysisPlan、Completeness Gate、Skills 和 U1–U7 未修改。

Olist override 增加了最小结构化 policy contract/reference，使 resolver 可以确定性产出 `order_status == delivered` 和支付表按 `order_id` 预聚合，而不是从自然语言中猜测。三个 unit-level contract 检查确认：Payment GMV 带 delivered population、purchase-time binding 和 payment pre-aggregation；AOV numerator/denominator 共用 completed-order population；Delivery Rate 仅对 numerator 应用 delivered filter，denominator 保留 analysis period 内全部 distinct orders。

固定 `qwen/qwen3.6-flash`、`project_id=olist` 只运行一次 `executive_business_snapshot` Planner-only。Attempt 1 即 schema-valid、Gate ready，未 replan；Planner 选择 Payment GMV、AOV 和 Delivery Rate，正确使用 `order_purchase_timestamp/month`、delivered GMV/AOV population、all-orders delivery denominator、payment-by-order pre-aggregation 和 denominator-preserving left join。Planner metric context 的 JSON 字符数从 raw compact context 的 10,940 减少到 resolved candidate context 的 8,845（约 19%）。Artifact 位于 git-ignored 的 `server/evals/results/planner-rmc-executive-20260826.json`。这是一次单例 Planner 结果，只证明 single resolved contract 在该次运行中被采用，不代表 24-case 准确率提升或 Code Generator/Validator 已遵守新合同。

**RMC Planner stability check：**随后在同一固定模型和 `project_id=olist` 下，对 Executive、Monthly Peak 和 Payment Structure 各独立运行三次 Planner-only，共 9 次。全部 first attempt 均 schema-valid，没有 deterministic fallback；7/9 Gate ready，3/9 发生 replan（全部为 Monthly Peak）。Executive 3/3 使用 delivered Payment GMV、同一 completed-order AOV numerator/denominator、all-orders Delivery Rate denominator、`order_purchase_timestamp/month`、payment-by-order pre-aggregation 和 left join，说明 RMC 对这三个 resolved metric contracts 形成了明显的跨轮稳定性。但是请求中的 standalone delivered-order count 只在 1/3 plan 中单独列出，表明非 Metric Knowledge 覆盖的 ad hoc output 仍有遗漏风险。

Monthly Peak 3/3 使用 purchase time、delivered population 与 payment pre-aggregation，但只有 1/3 ready；其余两轮在两次 schema-valid planning 后仍未对 decision-required `ecommerce.gmv` 做 selected/rejected/clarification 决策，因 `unresolved_metric_candidate` 被 Gate 拦截。唯一 ready 轮使用 inner join，可能在 order-count/AOV denominator 计算前删除无 payment match 的 delivered orders；另两轮使用 left join。因此 time/population 稳定，但 candidate decision 和 baseline-preserving join 仍不稳定。

Payment Structure 3/3 schema-valid 且 ready，也都将 payment-method amount share 表达为 payment-value grain、将 multi-payment rate 表达为先按 `order_id` 统计 payment rows 的 order grain。但三轮都将用户问题中的 delivered-order population 放宽为 orders with payment records。其中一轮在 structured numerator 中使用 `payment_sequential >= 2`，其余两轮只在 calculation/steps 中表达 payment-row count > 1，显示结构化 multi-payment predicate 仍有漂移。根因是这两个 project metric override 当前仍只提供自然语言 population description，没有关联可解析的 population policy filter；RMC 没有编造不存在的结构化语义，Planner 因而稳定地采用了错误的更宽总体。

Updated interpretation：RMC 确实减少了已完整 resolve 指标的 semantic drift，但不会自动修复缺失的 knowledge contract、candidate decision 或 ad hoc requested-output coverage。因此当前已适合开始一个窄范围的 Code Generator adherence 实验，但还不适合宣称 Planner 全面稳定，也不应立即运行完整 24-case benchmark。三轮 artifact 分别位于 git-ignored 的 `server/evals/results/planner-rmc-stability-run{1,2,3}-20260826.json`。

**Executive Code Generator adherence 与 executable-contract 修复：**固定使用已经 schema-valid、Gate Ready 且核心业务语义正确的 Executive AnalysisPlan，第一次只运行 Code Generator + Sandbox 时，生成代码在 population、denominator、purchase-time 边界、payment pre-aggregation、left join、order grain 和 overall/monthly consistency 上均遵守 Plan；但 result dictionary 写成了 `"primary_value": null`。Python 将 `null` 解析为普通变量名，因此既有 `ast.parse()` 语法检查没有拦截，Sandbox 最终以 `NameError` 失败，Validator 正确将 execution 与 structured result 标为 fail。

根因是 Code Generator 和 repair prompt 用 JSON 的 `null` 描述 Python result dictionary，而提取链只有 Python syntax validation，没有 executable literal contract。本轮最小修复将 prompt 改为明确使用 Python `None/True/False`，并在所有 generation/repair 共用的代码提取出口增加 token-level normalization：只转换裸 NAME token `null/true/false`，不修改字符串或注释，随后再次执行 AST parse。直接相关的 30 个 `unittest` 全部通过。

修复后只重跑同一 Executive Code Generator + Sandbox 实验一次，没有调用 Planner、repair 或完整 benchmark。生成代码不再包含裸 JSON literal，Sandbox 成功返回结构化结果和 12 个月趋势数据；全年结果为 14,429 个 delivered orders、2,320,454.39 BRL Payment GMV、160.82 BRL AOV、96.19% Delivery Rate，现有 Validator 8/8 pass。Artifact 位于 git-ignored 的 `server/evals/results/code-adherence-executive-literal-fix-20260826.json`。这证明该单例的 executable-contract 问题已修复，不代表 Code Generator 在其他任务上全面遵循 Plan，也不代表 Validator 已具备通用 semantic validation。非阻塞缺口：月度 dataset 已包含 AOV，但 visualization specs 尚未为 AOV 单独生成图表；本轮没有修改 visualization policy。

**Three-case end-to-end expansion：**Executive 现作为 golden regression case 使用。四个 expected facts 已记录在 `business_benchmark_cases.json`，十项 Plan-to-Code 合同与成功 artifact 已记录在本文和 git-ignored eval artifact；但目前还没有一条自动化测试同时断言 purchase time、完整年度边界、payment pre-aggregation、left join、四个 population/denominator 合同和最终四个 reference 数值。因此当前 golden protection 是 benchmark + artifact + review checklist，而不是完整的 deterministic regression test。本轮没有修改或重跑 Executive。

固定 `qwen/qwen3.6-flash`、`project_id=olist` 后，Monthly Peak、Payment Structure 和 Review Grain 各通过真实 in-process `/api/query` 完整运行一次。没有运行完整 24-case benchmark，也没有修改 Planner、RMC、Gate、Code Generator、Validator、Skills 或 expected values。

| Case | RMC | Plan / Gate | Code / Sandbox / Validator | Final | First failure |
|---|---|---|---|---|---|
| `monthly_peak_diagnosis` | Partial：AOV 与 Payment GMV 带 delivered/purchase-time contract；generic GMV 仍是 exact mandatory candidate，且自身缺少 completed population 与 payment pre-aggregation | 两次 plan 均 schema-valid；核心计划采用 delivered、purchase month、payment-by-order pre-aggregation 和 left join，但没有 select/reject/clarify `ecommerce.gmv`；Gate 在一次 replan 后安全停止 | 未生成代码、未运行 Sandbox/Validator；0 repair | 无结果 | Planner candidate-decision instability；generic GMV 与 Payment GMV 的 RMC/retrieval ambiguity 是 contributing factor |
| `payment_structure_risk` | Incomplete：两个 RMC 都在 description 中提到 Olist valid completed orders，但 `resolved_population.filters=[]`，没有结构化 delivered filter | 用户问题显式要求 delivered，Planner 将该条件写入顶层 filters；amount share 使用 payment amount grain，multi-payment rate 使用先按 `order_id` 统计 payment rows 的 order grain；Gate ready，无 replan | Code 忠实执行 delivered inner join、金额分子/总金额分母和 payment-row-count > 1。初次结果把多个 metric IDs 写成 list，AnalysisResult schema 拒绝；一次 repair 后 Sandbox success、Validator 8/8 pass | 77.92% credit-card amount share、19.21% boleto share、3.45% multi-payment order rate；3/3 facts pass | RMC structured-population coverage gap；最终结果被 user-explicit filter 正确补救。独立工程问题是 multi-metric result 的单值 `metric_id` contract |
| `review_grain_audit` | Generic `ecommerce.order_count` exact candidate 与本题 ad hoc review metrics 不同；A1 未处置，A2 合法 reject。当前没有 authoritative review-grain metric contract | A2 schema-valid、Gate ready；Plan 以全部 review rows 为 population，明确 row grain 与 order grain 两级计算；1 replan | Code 直接按 reviews 计算 row mean，并按 `order_id` 聚合 review count/order mean；grain transformation 与 weighting-bias explanation 正确。Sandbox success、Validator 8/8 pass、0 repair | 122 duplicate-review orders、4.0689 row mean、4.0696 order mean、-0.0006 delta；benchmark 0/4 facts | Benchmark/task population ambiguity：问题文本没有要求 delivered，但 expected values 使用 delivered-order reviews。若 delivered 是真实合同，当前 Planner/RMC 没有获得该 authority；不能只把差异归因于 Code |

Artifacts 分别位于：`server/evals/results/e2e-expansion-monthly_peak_diagnosis-20260826.json`、`e2e-expansion-payment_structure_risk-20260826.json` 和 `e2e-expansion-review_grain_audit-20260826.json`，均被 Git ignore。

Updated interpretation：项目已经能够在 Payment Structure 中稳定区分 amount grain 与 order grain，Code Generator 也能忠实执行正确 Plan；Review Grain 证明 ad hoc 两级 grain transformation 和 candidate rejection 可以完成，但也证明 Validator 的 high confidence 仍只覆盖 execution/schema/grounding，而不会发现未写进 Plan 的 delivered population reference。Monthly Peak 则表明 candidate decision 仍可能在 Code Generation 前阻断任务。当前不适合用完整 24-case benchmark 作为“已稳定版本”的准确率评估：最小阻塞是 generic/specific metric candidate 的稳定决策、RMC structured population coverage，以及先澄清 Review case 的 delivered population 是否应成为用户可见合同。完整 benchmark 仍可用于诊断，但不应把这些未收敛问题混成一个总分后宣称能力提升或下降。

**Canonical GMV identity and structured payment population follow-up：**本轮只在 Olist Project Override 与 Metric Resolver 层收敛两个产品问题，没有修改 Planner prompt、Gate、Code Generator、Validator 或 benchmark reference。Olist 现在显式将 project-scoped canonical `ecommerce.gmv` 映射到 `ecommerce.payment_gmv`；domain 层两个 metric 仍保持独立。当用户直接询问 generic GMV 时，generic candidate 保留在 trace 中但被 canonical target shadow，Payment GMV 成为 `decision_required` candidate，provenance 明确记录 `project_override`，不依赖 retrieval score 或题目特判。

Payment Structure 的两个 Olist overrides 新增 `population_policies=["valid_completed_order"]`。Resolver 通过既有 policy contract 绑定到 `olist_orders_2017.csv.order_status == delivered`，并在 `resolved_population`、`resolved_numerator` 与 `resolved_denominator` 中均生成同一结构化 filter。这一结果来自 deterministic project policy resolution，不再依赖 Planner 从 natural-language `default_population` 中猜测。

固定 `qwen/qwen3.6-flash` 与 `project_id=olist` 后，Monthly Peak 和 Payment Structure 各独立运行 3 次 Planner-only。6/6 均 schema-valid、Gate Ready、0 replan、0 fallback。Monthly 3/3 均选择 `ecommerce.payment_gmv` + `ecommerce.aov`，generic GMV 3/3 为 non-mandatory shadowed candidate；3/3 使用 `order_purchase_timestamp`、delivered Payment GMV/AOV、payment-by-order pre-aggregation 和 left join。但第 2 轮将 monthly order count 定义为全部 2017 orders，而 GMV/AOV 仍是 delivered population，所以 candidate conflict 已解决，但多指标 population consistency 仍存在 Planner semantic drift。Payment Structure 3/3 均选择 amount-share 与 multi-payment-rate，使用 delivered population，并保持 payment-amount grain 与 order-rate grain 的区分。Artifacts 位于 git-ignored 的 `server/evals/results/canonical-population-planner-run-{1,2,3}-20260826.json`。

Review Grain 本轮保持不变：用户问题与当前产品 knowledge 没有提供 delivered-only authority，而 reference 采用 delivered-order reviews，因此继续标记为 benchmark/spec hidden assumption，不通过修改产品逻辑迎合。根目录 `/data/agent-checkpoints.db*` 也已加入 Git ignore，覆盖 SQLite 主库、`-wal` 和 `-shm`。

**Post-RMC diagnostic baseline（24-case E2E）：**在冻结当前 Planner、RMC、Project Override、Gate、Code Generator、Validator、Skills 与 benchmark scoring 的前提下，固定 `qwen/qwen3.6-flash`，并为全部 Olist 请求显式传入 `project_id=olist`，运行完整 24 cases / 26 turns。首次长任务中断且未形成可复用结果后，使用不修改源码的逐 case wrapper 调用原有 `run_business_eval`，每题独立保存中间结果并汇总为 git-ignored artifact：`server/evals/results/post-rmc-diagnostic-baseline-20260826.json`。本轮是 diagnostic baseline，不是最终准确率验收。

| Metric | Pre-RMC baseline | Post-RMC diagnostic |
|---|---:|---:|
| Case pass rate | 4/24 = 16.67% | 3/24 = 12.50% |
| Fact recall | 46.15% | 31.73% |
| Business-term coverage | 82.05% | 58.97% |
| Execution success | 96.15% | 15/26 = 57.69% |
| Structured-result success | 100% | 13/24 analysis turns = 54.17% |
| Runtime validation pass | 95.83% | 13/13 executed analyses = 100% |
| Plan-intent accuracy | 23.53% | 58.82% |

本轮通过的 case 是 `monthly_peak_diagnosis`、`payment_structure_risk` 和 `profit_metric_clarification`。Planner first-attempt schema-valid 为 18/26（69.23%），any-attempt schema-valid 为 20/26（76.92%）；14/26 turns replan（53.85%），1/26 turns repair（3.85%）。11/26 turns 在 Plan Readiness Gate 停止，涉及 9 个 case；这说明安全边界确实阻止了 incomplete plan 继续执行，但 Planner schema/completeness 仍显著降低任务完成率。两个预期 clarification 均正确触发。

四个重点 case 的 updated interpretation：

- `executive_business_snapshot` 的 Plan、生成代码和最终答案均使用 delivered Payment GMV/AOV、all-orders Delivery Rate denominator、purchase time、payment-by-order pre-aggregation 与 left join；最终答案精确包含 14,429、2,320,454.39、160.82 和 96.19%。但 `AnalysisResult.rows` 只包含 12 个按月记录，全年值仅存在于 summary/insights 字符串中。scorer 只能从结构化数值字段取值，误将 11 月数值当作全年结果，造成 0/4 fact recall。这是 requested-output/structured-result contract 与 scorer interface 问题，不是 Executive 计算回归；expected metric IDs 仍要求 generic `ecommerce.gmv`，也与新的 Olist canonical Payment GMV identity 不一致。
- `monthly_peak_diagnosis` 继续通过，3/3 facts 正确；真实 E2E 使用 purchase month、delivered population、payment pre-aggregation 和 denominator-preserving left join，本轮未观察到此前的 population drift。
- `payment_structure_risk` 首次完整 baseline 中通过，3/3 facts 正确；resolved delivered population 在 E2E 中生效，代码正确区分 payment-amount grain 与先按 `order_id` 统计 payment rows 的 order grain。
- `review_grain_audit` 在 A1 因 unresolved `ecommerce.order_count` candidate 被 Gate 拦截，A2 又因两个 operand 的 `aggregation=null` schema-invalid 而停止，未进入 Code Generator。即使执行，reference 的 delivered-only review population 仍未出现在用户问题或 authoritative knowledge 中，因此该 population mismatch 继续标记为 benchmark/spec hidden assumption；当前产品侧首个失败仍是 Planner candidate decision/schema mapping。

失败 case 的第一处 failure layer：

- **Planner / Gate（产品缺陷）：**`fact_table_join_audit`、`review_grain_audit`、`late_delivery_experience_gap`、`category_experience_problem`、`seller_risk_diagnosis`、`fulfillment_action_plan`、`category_portfolio_strategy`、`state_category_followup`、`experience_executive_followup`。Gate 本身不是根因；它暴露了 missing join、unresolved/unretrieved metric、schema failure 或 fallback plan。
- **Planner semantic correctness（产品缺陷）：**`category_revenue_concentration` 的 category field/denominator，`state_delivery_hotspot` 的 review one-to-many inflation，`seller_governance_strategy` 的 metric/population/grain，以及 `causal_claim_boundary` 的 causal boundary 与 late definition。
- **Structured output / final protocol（产品或协议缺口）：**`executive_business_snapshot`、`state_revenue_concentration`、`repeat_customer_health` 和 `monthly_decline_decomposition`。这些 case 分别存在全年 aggregate 未作为结构化数值输出、Top-3 aggregate 未输出、repeat numerator 只写进 insight、percent 与 fraction scale 未统一的问题；不能简单归为分析计算错误。
- **Benchmark/spec ambiguity：**`customer_identity_audit`、`missingness_business_impact` 与 Review 的 delivered-only population 没有充分用户/knowledge authority；`channel_quality_clarification` 正确澄清，但 `2/3=0.666...` 被 `0.67` threshold 判失败。`category_revenue_concentration` 还需要明确 category naming 与 denominator policy。
- **Final Answer coverage：**`regional_growth_priority` 的数值事实全部通过，但业务术语覆盖只有 2/3，因此 case 未通过。

Updated interpretation：Post-RMC 总通过率低于旧基线，不能直接解释为 RMC 造成能力退化。新 Gate 把原来会继续执行的空洞计划安全停止，同时 Planner schema 稳定性、structured-result coverage 和 scorer/spec 问题共同压低了总分。另一方面，Plan-intent accuracy 从 23.53% 提升至 58.82%，Executive 的四个核心口径已在真实 E2E 中正确闭环，Payment Structure 也从旧基线失败变为通过。这些是局部、可定位的进展，不构成总体准确率提升声明。

当前 top failure layers 是：（1）Planner schema/completeness 与多表 Join 计划；（2）ad hoc 业务问题中的 population、grain、metric 和 causal semantics；（3）Plan/requested outputs 到 `AnalysisResult` 及 scorer 的结构化数值合同。Validator 在 13 个实际执行 case 中 13/13 通过，但其中多数仍未通过 benchmark，证明其覆盖 execution/schema/grounding，而不覆盖 Plan compliance 或业务语义。下一阶段值得开始设计窄范围 Plan Compliance Validator，优先检查 planned metric/output 是否都有具名结构化数值证据、population/filter preservation、Join/pre-aggregation/grain 和 value scale；但 Planner schema/completeness 稳定仍应先于大范围 semantic validator 实现。

在下一次把总分用于版本验收前，应先清理或明确以下 benchmark contract：Review、Customer Identity、Missingness 的 population authority；Channel clarification threshold；Executive 的 canonical metric IDs 与全年 scalar output；Monthly Decline 的 percent/fraction scale；Category Revenue 的 category naming 和 denominator。上述清理应修正 spec/scoring，而不是让产品逻辑迎合隐藏 reference。

## 9. What We Learned

### 1. Execution correctness ≠ analytical correctness

96.15% execution success 与 16.67% case pass rate 同时出现，说明“代码跑通”只覆盖最底层可靠性。数据 Agent 还必须在 scope、grain、metric 和 aggregation order 上正确。

### 2. Schema validation ≠ semantic completeness

旧 `AnalysisPlan` 的空对象可以通过 Pydantic，因为所有字段都有默认值。类型正确只是必要条件；系统需要额外定义“什么信息齐全后才允许执行”。

### 3. Retrieval does not guarantee downstream adoption

Skill 和 Metric Retrieval 可以找到正确资料，但 Planner 可能漏掉，Code Generator 也可能自行改写。检索命中率不能直接当作最终业务口径遵循率。

### 4. Planning must be an enforceable contract, not optional context

只把 plan 放进 prompt，无法保证 Code Generator 遵守。第一步是阻止空 plan；下一步才是限制 Code Generator 不得覆盖 Planner 已决定的业务语义。

### 5. Evaluation should separate failure layers

一次最终失败可能来自：

- Planner 没有表达正确 scope；
- Code Generator 没有实现 plan；
- Sandbox 执行错误；
- Validator 没有发现语义偏差；
- Scorer 把正确数值匹配到错误指标；
- benchmark threshold 本身编写错误。

只有分层评测，才能避免为 scorer bug 修改产品代码，或为 Planner bug不断修复 Sandbox。

### 6. Safety gates can initially reduce completion while improving reliability

Planner-only 结果从“可以继续跑”变成 6 个 incomplete stop，看上去降低了任务完成率，但减少了系统输出未经约束答案的机会。这个变化是 reliability boundary 的建立，不是准确率提升；只有后续 Planner 稳定后，安全性和完成率才可能同时改善。

## 10. Next Steps

以下内容是已确定的下一阶段方向，**尚未实现**：

1. **Planner failure taxonomy：**把 schema invalid、missing semantics、retrieval mismatch、invalid clarification 和 model/provider failure 分开统计。
2. **Candidate metrics vs selected metrics（第一阶段已完成）：**已区分 candidate、selected 与 rejected，并移除“全部召回均 mandatory”的 Gate 规则；后续仍需提高 Planner 对 rejection contract 的稳定采用率。
3. **Fixed-model planner evaluation：**固定模型、版本和参数，避免 `openrouter/free` 动态路由造成不可比较结果。
4. **Planner prompt/schema stability：**检查 provider 对 strict JSON schema 的兼容性，降低字段漏填和结构化失败。
5. **Repeated planner evaluation：**同一组 case 多次运行，记录 ready rate、clarification accuracy、issue 分布和输出一致性。
6. **Only after Planner stabilizes, make Code Generator obey Plan：**让 Code Generator 只决定 Pandas 实现方式，不得覆盖 scope、grain、metrics、filters、denominator 和 Join 语义。
7. **Semantic validation later：**在稳定 plan contract 基础上增加最小 compliance checks，再逐步验证 scope consistency、ratio operands 和 join-grain invariants。

完整 24-case benchmark 应在 Planner 与 Code Generator 合同接通后重新运行，并保留新旧版本为独立实验，不能覆盖 v2.1.0 历史结果。

## 11. Interview / Project Story

### 30 秒版本

我给 DataSays 建了一套 24 题的 Olist 经营分析 benchmark。结果发现代码执行成功率达到 96.15%，但题目通过率只有 16.67%，说明 Agent 会运行不等于会算对。追踪后发现 Skill 和 Metric 已检索成功，但 AnalysisPlan 可以为空并继续生成代码，Validator 又主要检查执行和结构。于是我先把 Planner 改成包含 scope、grain、指标分子分母和 Join 要求的分析合同，并增加 completeness gate 和一次 replan。改造后 8 题中 6 题被安全拦截、2 题正确澄清、0 题 ready，证明风险边界建立了，但也诚实暴露了 Planner 稳定性还没解决。

### 1 分钟版本

DataSays 是一个把自然语言问题转成 Pandas 代码、在沙箱运行并返回结构化证据的数据分析 Agent。我没有只用“代码能否执行”评估它，而是基于 Olist 五张关联表设计了 24 个真实经营分析 case，覆盖指标口径、事实表粒度、Join、诊断、澄清和记忆。基线中 execution success 是 96.15%，runtime validation pass 是 95.83%，但 case pass rate 只有 16.67%。我追踪 `executive_business_snapshot` 后发现，GMV/AOV 使用了错误 scope；更根本的是旧 AnalysisPlan 几乎为空也能通过 Pydantic，Code Generator 会重新解释问题，Validator 又无法检查业务语义。我的设计决策不是给 24 题写规则，而是先让 Planner 决定 WHAT、Code Generator 只负责 HOW。我实现了 AnalysisPlan V1.5、结构化 filters、metric operands、最小 JoinSpec、completeness gate 和一次 replan。63 个后端测试通过；8 题 Planner-only 评测中 6 题被拦截、2 题正确澄清，但没有 ready plan，所以目前成果是阻止不可靠执行，而不是宣称准确率提升。下一步是固定模型稳定 Planner，再约束 Code Generator。

### STAR 结构版本

**Situation：**DataSays 已具备 Profile、Skill/Metric Retrieval、LLM-to-Code、Python Sandbox 和 Validator，但缺少能证明业务计算正确的系统评测。

**Task：**判断 Agent 是否能完成真实经营分析，并定位为什么“已验证”的结果仍可能使用错误口径。

**Action：**我建立了 24 cases / 26 turns 的 Olist benchmark，分层统计事实、业务术语、执行、验证、澄清、记忆和计划意图；随后追踪 `executive_business_snapshot`，将 Agent bug 与 scorer bug 分开。根因是 AnalysisPlan 只是可选上下文。为隔离变量，我只改 Planner 层：增加 V1.5 schema、completeness gate、一次 replan 和 LangGraph 安全截止，并新增直接测试和 planner-only runner，没有修改 Code Generator、Validator 或 expected values。

**Result：**基线 case pass rate 为 16.67%，与 96.15% execution success 形成明显反差。改造后 63 个后端测试通过；8 个 planner-only case 中 6 个 incomplete plan 被阻止进入代码生成，2 个缺少渠道/成本证据的 case 正确澄清，0 个 plan ready。已实现的是分析合同和风险 gate；尚未实现的是稳定 Planner、Code Generator 强制遵循和 semantic validation。评测还发现 delivery-rate 数值归属及 `0.67` threshold 两个 benchmark/scorer 问题，因此没有把所有失败都归因于产品。

---

## 事实来源与解释边界

### 直接来自真实 benchmark / artifact 的数据

- 24 cases / 26 turns；
- 4/24 case pass rate；
- 46.15% fact recall；
- 82.05% business-term coverage；
- 96.15% execution success；
- 95.83% runtime validation pass；
- 23.53% plan-intent accuracy；
- `executive_business_snapshot` 的 expected/observed facts、最终空 plan 和 high-confidence validation；
- `channel_quality_clarification` 的 `2/3` 与 `0.67` threshold 问题。

### 直接来自本次实现和测试的事实

- AnalysisPlan V1.5 字段与 gate 规则；
- 最多一次 replan；
- incomplete plan 不进入 Code Generation；
- 63 backend tests、compile check 和 diff check 通过；
- planner-only 8-case 运行的 `0 ready / 2 clarification / 6 blocked / 7 replans`。

### 设计解释或工程推论

- “Planner decides WHAT / Code Generator decides HOW”是本次职责划分原则，不是完整落地状态；
- safety gate 预计降低未经约束答案风险，但当前没有用户风险率或端到端准确率提升数据；
- 先稳定 Planner、再约束 Code Generator、最后增加 semantic validation 是后续实施顺序，不是已完成功能；
- 自然语言 scope 和 grain 具有泛化优势，但是否足够支持未来 semantic validation 仍需实验。
