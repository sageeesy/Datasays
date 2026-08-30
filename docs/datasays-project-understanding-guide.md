# DataSays 项目理解与面试手册

> 文档性质：供项目作者本人学习、复习和准备简历、面试、答辩使用的内部 Living Study Document。

## 使用说明

1. 本手册以当前真实源码、schema、service、route、test、evaluation runner、benchmark definition、knowledge file 和必要的 Git 历史为准；文档与实现冲突时，以当前代码为准并记录差异。
2. 学习顺序固定为：`Teach → Quiz → 回答 → 纠正 → 确认 → 写入本手册`。
3. 某章未完成理解题与纠正前，只保留目录占位，不提前生成正文。
4. 每章持续区分 Analysis Capability、Reliability Infrastructure、Engineering Infrastructure。
5. 本手册不把 prompt/code capable、固定 probe 可运行或实验性结果包装成正式产品支持。
6. 学习阶段发现的问题只记录现象、根因、所属层和未来修改价值；不顺手修改产品代码。

---

# One-page Architecture Cheat Sheet

> 状态：骨架。以下内容将在对应章节完成并确认后逐步补全。

## 1. DataSays 一句话定位

_待 Chapter 1 学习确认后填写。_

## 2. Main Query Flow

```text
Question + uploaded CSV file IDs
↓
Dataset Profile
↓
Conversation Memory + Analysis Skill Selection
↓
Metric Retrieval + Resolved Metric Candidates (RMC input)
↓
Planner → AnalysisPlan
↓
Plan Normalization + Readiness Gate
├─ Clarify / Stop safely
└─ Ready
   ↓
Code Generator
↓
Visualization Policy Check
↓
Python Sandbox → AnalysisResult + ResultEvidence
↓
Deterministic Artifact Validator
├─ Repair Code → re-execute（bounded loop）
└─ Pass / terminal failure
   ↓
Final-answer wording + numeric-faithfulness validation
↓
Final Answer + Dashboard-ready artifacts + Trace + persistence
```

_该流程是当前代码的初步 reality-check 骨架；模块语义和边界待后续章节逐项确认。_

## 3. Three Layers

### Analysis Capability

_待学习后补充。_

### Reliability Infrastructure

_待学习后补充。_

### Engineering Infrastructure

_待学习后补充。_

## 4. Module Cheat Sheet

| Module | 一句话解释 | 状态 |
|---|---|---|
| Dataset Profile | 待补充 | 未确认 |
| Metric Retrieval / RMC | 待补充 | 未确认 |
| Planner / AnalysisPlan | 待补充 | 未确认 |
| Normalizer / Readiness Gate | 待补充 | 未确认 |
| Code Generator | 待补充 | 未确认 |
| Python Sandbox | 待补充 | 未确认 |
| AnalysisResult / ResultEvidence | 待补充 | 未确认 |
| Validator | 待补充 | 未确认 |
| Replan / Repair | 待补充 | 未确认 |
| LangGraph / AgentState | 待补充 | 未确认 |
| FastAPI / SQLite / SSE / React / Docker | 待补充 | 未确认 |

---

# Chapter 目录

- [ ] Chapter 1 — DataSays 到底解决什么问题
- [ ] Chapter 2 — 完整 Architecture：一次 Query 的生命周期
- [ ] Chapter 3 — Dataset Profile：Agent 如何认识数据
- [ ] Chapter 4 — Metric Retrieval + RMC：如何理解业务指标
- [ ] Chapter 5 — Planner + AnalysisPlan：如何决定 WHAT to compute
- [ ] Chapter 6 — Normalizer + Readiness Gate：为什么 Plan 不能直接执行
- [ ] Chapter 7 — Code Generator + Python Sandbox：HOW to compute
- [ ] Chapter 8 — AnalysisResult + Result Evidence：如何让结果机器可读、可追踪
- [ ] Chapter 9 — Validator：验证什么，以及不能验证什么
- [ ] Chapter 10 — Replan / Repair / Failure Recovery
- [ ] Chapter 11 — LangGraph Orchestration + Agent State
- [ ] Chapter 12 — FastAPI / SQLite / SSE / React / Docker
- [ ] Chapter 13 — Analysis Capability Benchmark V1
- [ ] Chapter 14 — Olist-24 Business Analytics Reliability Benchmark
- [ ] Chapter 15 — 经典 Failure Cases
- [ ] Chapter 16 — 当前 Capability Matrix 与真实能力边界
- [ ] Chapter 17 — Limitations / Technical Debt / Architecture Trade-offs
- [ ] Chapter 18 — 如果从零重新设计 DataSays
- [ ] Chapter 19 — 简历、项目介绍与面试答辩

> Chapter 正文将在对应章节完成理解题、纠正并确认后，按固定格式追加。

---

# Interview Question Bank

> 状态：空结构。学习过程中逐步维护。

## Basic

_待补充。_

## Architecture

_待补充。_

## Reliability

_待补充。_

## Evaluation

_待补充。_

## Engineering

_待补充。_

## Challenge Questions

_待补充。_

## Questions I Got Wrong

_待补充。_
