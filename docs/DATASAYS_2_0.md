# DataSays 2.0

## Product Positioning

DataSays is a metric-aware, evidence-first data analysis agent. Its purpose is not to support every possible data source or tool. It focuses on whether an answer follows an explicit business definition, can be reproduced from an execution artifact, and can be inspected when it fails.

## Current P0/P1 Workflow

1. Profile each uploaded CSV: types, semantic roles, missingness, cardinality, samples, ranges, and duplicate rate.
2. Load bounded recent dialogue and validated findings scoped to the current datasets.
3. Select a small analysis playbook from local versioned knowledge.
4. Retrieve matching ecommerce or SaaS metric definitions and bind logical concepts to actual columns.
5. Generate a typed `AnalysisPlan`.
6. Generate Python that emits a typed `AnalysisResult` marker.
7. Execute in the existing sandbox.
8. Validate execution, required columns, metric grounding, result structure, and final-answer numeric faithfulness.
9. Retry code generation with validation feedback within a bounded repair loop.
10. Show the plan, memory use, definitions, artifact, checks, assumptions, and workflow trace in the UI.

## Scope Boundary

| Area | Current P0 | Later P1/P2 |
|---|---|---|
| Orchestration | LangGraph StateGraph, SQLite node checkpoints, conditional repair and live SSE progress | Resume/approval API, Postgres checkpoints, distributed workers |
| Knowledge | Versioned JSON metric packs and deterministic retrieval | Embedding retrieval for larger knowledge collections |
| Evaluation | Olist v1 calculation regression plus v2.1.0 business-analysis suite, deterministic facts, multi-turn protocol, service tests and one complete Qwen3.6 Flash baseline | Additional model/repeated baselines, token and cost accounting, human review, semantic judge, external benchmark compatibility |
| Data sources | CSV | Excel, SQL, dashboard images, PDFs |
| Agents | One bounded analysis agent | No multi-agent system unless a real coordination need appears |

## Resume-Safe Claims

The repository currently demonstrates LangGraph planning and routing, local Skill selection, metric retrieval, dataset-scoped conversation memory, sandbox execution, deterministic validation, bounded repair, durable local checkpoints, real-time SSE node events, trace metadata, and persisted analysis artifacts. It does not yet implement checkpoint resume/approval controls, semantic/vector memory, MCP, or production SaaS isolation. Those capabilities should only be claimed after their acceptance criteria are implemented and tested.

## Multimodal Roadmap

Images should enter through an extraction layer instead of being treated as CSVs.

```mermaid
flowchart LR
    A["Image or PDF"] --> B["OCR / vision extraction"]
    B --> C["Typed observations with source regions and confidence"]
    C --> D["Normalized table or document artifact"]
    D --> E["Existing profile, plan, metric, execution, validation workflow"]
    E --> F["Answer with citations to image regions"]
```

The recommended first image scope is dashboard screenshots and photographed tables. They can be normalized into rows and columns, then reuse most of the current workflow. General photos require a different validation contract: detected objects and attributes, bounding regions, model confidence, and explicit uncertainty.

## Ownership

Engineering work such as orchestration, schemas, sandbox protocol, validation, UI evidence, tests, and documentation can be implemented independently. The user or a domain owner must approve business truth: metric formulas, inclusion and exclusion rules, time windows, representative datasets, and expected benchmark answers.
