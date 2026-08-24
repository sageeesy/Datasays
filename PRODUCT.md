# DataSays Product Context

DataSays is an evidence-first data analysis Agent for operations and business users who need reproducible answers from exported CSV data without writing Python. The near-term product direction is a verifiable business analysis Agent; ecommerce operations is the first proposed vertical, not yet a validated market claim.

## Core Surfaces

- **Verified Analysis:** the primary workflow. Upload CSV data, ask a question, and receive one sandbox-backed answer with expandable evidence and execution trace.
- **Comparison Lab:** an evaluation workspace for comparing three models across three prompt strategies. It is secondary to the trusted-answer workflow.
- **Data Dashboard:** an interactive visualization opened from a verified result when that result contains structured rows suitable for charting.

## Product Commitments

- Keep model and prompt controls visible for now.
- Support Simplified Chinese and English UI, with Chinese as the default.
- Prefer a single trustworthy answer over duplicated answer cards on the primary surface.
- Keep metric definitions, code, assumptions, validation checks, and trace inspectable.
- Use only bounded, dataset-scoped, validation-passing history as Agent context.
- Show only backend-emitted LangGraph node progress; never simulate workflow advancement with a timer.
- Do not expose a dashboard link when the result has no chartable structured data.

## Deferred Scope

Ecommerce metric research, multimodal inputs, vector RAG, checkpoint resume/approval controls, conversation report generation, external benchmark compatibility, MCP, and production sandbox hardening are separate later phases. The current Olist v1/v2 suites are local product evaluations, not proof of external benchmark performance.
