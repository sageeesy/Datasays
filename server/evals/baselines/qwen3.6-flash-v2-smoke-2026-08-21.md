# Qwen3.6 Flash v2 Smoke Test - 2026-08-21

This is a one-case integration smoke test, not a complete Olist Business Analysis Suite v2 baseline.

这是单题端到端冒烟测试，不是 Olist Business Analysis Suite v2 的完整基线。

## Configuration / 配置

| Field | Value |
|---|---|
| Model | `qwen/qwen3.6-flash` through OpenRouter |
| Case | `profit_metric_clarification` |
| Transport | Local file store + in-process FastAPI ASGI |
| Full workflow | FastAPI -> LangGraph -> Planner -> code execution/repair -> Validator |
| Date | 2026-08-21 |

## Initial Result / 初始结果

| Metric | Value |
|---|---:|
| Case pass | 0 / 1 |
| Business-term coverage | 100% |
| Workflow status success | 100% |
| Clarification accuracy | 0% |
| End-to-end latency | 73.204 seconds |

The answer recognized that cost data was missing and mentioned that profit could not be calculated. However, the typed plan set `needs_clarification = false`, continued into code generation, produced a structured artifact and chart, and used one repair attempt. The benchmark therefore correctly failed the case: recognizing a limitation in prose is not equivalent to taking the required clarification branch before calculation.

回答正文识别了成本字段缺失，也说明无法计算利润；但结构化计划仍设置 `needs_clarification = false`，继续生成和执行代码，返回结构化结果与图表，并发生一次修复。因此该题判失败是合理的：在正文承认限制，不等于在计算前进入正确的澄清分支。

## Product Finding And Fix / 产品发现与修复

The smoke test identified a concrete Planner gap. DataSays added a gross-profit metric definition with required revenue and cost concepts, plus a deterministic planning guard that checks matched metrics and explicitly requested dimensions against the uploaded schema before code generation.

该测试暴露了明确的 Planner 缺口。修复包括：新增拥有收入与成本必需概念的毛利润指标定义，并增加确定性规划门禁，在代码生成前检查命中的指标和明确请求的分析维度是否存在于上传数据中。

## Post-fix Result / 修复后结果

| Metric | Value |
|---|---:|
| Case pass | 1 / 1 |
| Business-term coverage | 100% |
| Clarification accuracy | 100% |
| Structured result emitted | No, as required |
| Repair attempts | 0 |
| End-to-end latency | 21.540 seconds |

The rerun set `needs_clarification = true`, returned a Chinese explanation naming the missing cost and revenue concepts, and stopped before code generation. This validates the one-case feedback loop only; the complete 24-case v2 baseline remains pending.

复测中 `needs_clarification = true`，系统用中文说明缺失的成本与收入概念，并在代码生成前停止。该结果只验证了单题反馈闭环，完整 24 题 v2 基线仍待运行。
