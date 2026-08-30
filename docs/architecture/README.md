# DataSays Architecture Maps

这个目录放置从当前源码核实后生成的架构沟通产物，不参与产品运行，也不修改当前 DataSays UI 或业务逻辑。

## 01 — Single Query Sequence

- 交互式架构图：[`datasays-single-query.html`](./datasays-single-query.html)
- Archify typed source：[`datasays-single-query.sequence.json`](./datasays-single-query.sequence.json)

### 读图边界

这是 high-level sequence，用 8 个语义参与方表达一次查询的主路径。为保持一屏可读，图中的聚合节点不等于一个单独类或函数：

- `Agent Graph` 内部依次执行 `profile_data → load_memory → select_skills → retrieve_metrics → plan_analysis`，然后进入生成、执行、验证、有界修复与最终回答。
- `Checks` 聚合了 plan normalization/completeness、执行产物验证、visualization policy 和 final-answer numeric faithfulness；这些检查分布在不同 service 中。
- `Local State` 聚合了 CSV/uploads 与 metadata JSON、Conversation SQLite，以及 LangGraph checkpoint SQLite；它们是三类不同的持久化机制。
- 图中的紫色虚线表示可选的有界修复/润色路径，不表示每次请求都会重试。
- 计划不完整、需要 clarification、sandbox 不可修复错误等旁路不展开在这张 high-level 图中；它们由 [`datasays-analysis-lifecycle.html`](./datasays-analysis-lifecycle.html) 表达。

### 主要源码证据

| 事实 | 源码位置 |
|---|---|
| Query 准备、文件验证、对话上下文 | `server/app/routes/query.py:44` |
| SSE query endpoint 与 result persistence | `server/app/routes/query.py:152` |
| Dataset profile | `server/app/services/agent_service.py:205` |
| AnalysisPlan 生成与 completeness gate | `server/app/services/agent_service.py:273` |
| 代码生成 | `server/app/services/agent_service.py:388` |
| Sandbox 调用 | `server/app/services/agent_service.py:460` |
| Execution artifact validation | `server/app/services/agent_service.py:482` |
| Bounded repair | `server/app/services/agent_service.py:532` |
| 回答润色、numeric faithfulness 与 grounded fallback | `server/app/services/agent_service.py:560` |
| StateGraph 真实节点与边 | `server/app/services/agent_service.py:631` |
| LangGraph stream 与 SQLite checkpoints | `server/app/services/agent_service.py:756` |
| Conversation/message/analysis-run persistence | `server/app/services/conversation_service.py:258` |
| Docker/Python sandbox 实现 | `server/app/services/sandbox_service.py:26` |
| Deterministic artifact validation | `server/app/services/validation_service.py:33` |
| Final-answer numeric validation | `server/app/services/validation_service.py:199` |
| 前端 SSE 消费 | `lib/client.ts:434` |
| Answer、KPI、Evidence 与 Trace 呈现 | `components/VerifiedAnswerMessage.tsx:151` |

### 验证回执

- Archify diagram type: `sequence`
- Showcase validation: `9/9`, `0 errors`, `0 warnings`
- Specification SHA-256: `f0065faa95dedb8106508b424e307a4c60c25d86588ea397350f43ca391a931b`
- HTML SHA-256: `12268509a2afb6a07398c5557e0113da13bd5173da7d575489ac32ad43b2f83a`
- Desktop containment: passed at `1440×900`, `1600×1000`, `1920×1080`, `2048×1320`
- Light/dark screenshot review: passed
- Visual correction rounds: `1`
- Relevant backend tests: `57 passed`

## 02 — Runtime Architecture

- 交互式架构图：[`datasays-runtime.html`](./datasays-runtime.html)
- Archify typed source：[`datasays-runtime.architecture.json`](./datasays-runtime.architecture.json)

### 读图边界

- 主链路是 `分析用户 → React Workspace → FastAPI → Agent Graph → Model Services → OpenRouter`。
- `Context Layer` 聚合 profile、bounded memory 与 semantic context，不表示单一运行时类。
- `Execution trust boundary` 显式隔离生成代码的执行；File Store 仅以 read-only CSV copy 进入 sandbox。
- `Conversation DB`、`Checkpoint DB` 和 `File Store` 是不同持久化机制，只在图中共享本地状态边界。

### 验证回执

- Archify diagram type: `architecture`
- Showcase validation: `9/9`, `0 errors`, `0 warnings`
- Specification SHA-256: `844204333c7e9a1e8b6895fc3a94f708549d2725d2bba1f3a51e0a19192eecde`
- HTML SHA-256: `fc71f7411a12af5738b2986c0c4e45d99119b7f5cc23656c2d81168c555da7e7`
- Desktop containment: passed at `1440×900`, `1600×1000`, `1920×1080`, `2048×1320`
- Light/dark screenshot review: passed
- Visual correction rounds: `1`

## 03 — Evidence & Data Lineage

- 交互式数据血缘图：[`datasays-evidence-lineage.html`](./datasays-evidence-lineage.html)
- Archify typed source：[`datasays-evidence-lineage.dataflow.json`](./datasays-evidence-lineage.dataflow.json)

### 读图边界

- 图的五个阶段是 `Evidence Inputs → Grounding → Analysis → Verification → Verified UI`。
- `File Evidence` 将 CSV rows、metadata 和 profile 作为一个血缘节点，便于区分原始证据与生成代码。
- `Artifact Gate` 检查结构化执行产物；`Answer Gate` 检查最终文字中的数字忠实性。
- `Evidence Workspace` 表达前端中 KPI、chart、evidence 与 trace 的组合，不暗示这些数据是前端重新计算的。

### 验证回执

- Archify diagram type: `dataflow`
- Showcase validation: `9/9`, `0 errors`, `0 warnings`
- Specification SHA-256: `1d14e9e58a9ad8bcdb6c2d98eaeaecabb90a21f6f64174a2e518dcda29e751e0`
- HTML SHA-256: `ba3b13623b3a35ee0d37c25bf8ec2dbf983bacf3811f73ccbec1e208fbb2dd3f`
- Desktop containment: passed at `1440×900`, `1600×1000`, `1920×1080`, `2048×1320`
- Light/dark screenshot review: passed
- Visual correction rounds: `1`

## 04 — Analysis Lifecycle

- 交互式生命周期图：[`datasays-analysis-lifecycle.html`](./datasays-analysis-lifecycle.html)
- Archify typed source：[`datasays-analysis-lifecycle.lifecycle.json`](./datasays-analysis-lifecycle.lifecycle.json)

### 读图边界

- 主状态轨是 `Accepted → Grounding → Planning → Analyzing → Completed`。
- `Planning` 节点的 `max 2` 表示当前 planner completeness 的有界尝试，不单独展开为低价值重复节点。
- `Needs Clarification` 是等待新用户输入的产品状态；当前 run 在返回 clarification 后结束。
- `Repair Gate` 聚合 visualization policy、execution 与 artifact validation 的可修复判断；只在错误可修复且仍有 budget 时返回 `Analyzing`。
- `Completed` 包含验证通过的结果，也包含 final numeric gate 触发的 grounded safe fallback。

### 验证回执

- Archify diagram type: `lifecycle`
- Showcase validation: `9/9`, `0 errors`, `0 warnings`
- Specification SHA-256: `6e4bd591a9d18c21b87514705f7ec4c002ed9106ff57673b68e2b4f1d8257fb8`
- HTML SHA-256: `2eeb83927f20e40dae83cac6c3890a275174fcad24fbfcf65c1dfa278e5ad04e`
- Desktop containment: passed at `1440×900`, `1600×1000`, `1920×1080`, `2048×1320`
- Light/dark screenshot review: passed
- Visual correction rounds: `0`
