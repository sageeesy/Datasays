# DataSays Benchmark V2 Design

> Status: design proposal only. This document does not change existing cases, references, scoring, runners, or product behavior.

## 1. Purpose

Benchmark V2 should answer two different questions without compressing them into one misleading accuracy number:

1. **Capability breadth:** Can DataSays complete heterogeneous tabular-analysis tasks?
2. **Reliability depth:** Can DataSays preserve business semantics, data grain, denominators, joins, time definitions, Evidence, and safe clarification under difficult conditions?

The suite must keep easy foundations, applied analysis, and adversarial semantic cases. Code execution is a prerequisite, not proof that an analysis is correct.

## 2. Recommended Evaluation Architecture

V2 should expose three run views over two versioned benchmark families.

| View | Role | Recommended size | Relationship |
|---|---|---:|---|
| Core Regression Set | Fast milestone regression for stable, high-signal behaviors | 12 cases | A frozen subset of the two full benchmarks; no extra cases |
| Analysis Capability Benchmark V2 | Breadth across common analysis tasks | 24 cases | Evolves the current 13-case Capability Benchmark |
| Business Analytics Reliability Stress Set | Deep semantic and multi-table reliability | 24 cases | Retains the current Olist-24 unchanged for the first V2 release |

The initial V2 therefore contains **48 unique cases**, while routine development can run only the 12-case regression subset. Capability and reliability results remain separate; there is no mixed overall score.

### 2.1 Why this structure

- The 13-case benchmark already has deterministic fixtures, independent references, and a useful breadth runner.
- Olist-24 already contains expensive, realistic failures that should not be weakened or discarded.
- A subset view gives fast regression feedback without creating a third source of truth.
- Separate scorecards make `12/12 executed numerical references` and `3/24 strict reliability` interpretable rather than contradictory.

## 3. Capability Taxonomy

The Capability Benchmark V2 should use six user-goal-oriented tracks. SQL or Pandas operations such as `groupby`, joins, and distinct counts are execution primitives, not top-level capabilities.

| Track | User goal | Cases | Share of Capability V2 |
|---|---|---:|---:|
| Core Tabular Analysis | Describe, filter, aggregate, compare, rank, and summarize distributions | 5 | 21% |
| Time-Series & Diagnostic Analysis | Compare periods, identify change, decompose simple drivers, locate contributing segments | 4 | 17% |
| Behavioral Analysis | Evaluate funnel, cohort, retention, repeat behavior, and lifecycle segments | 4 | 17% |
| Data Quality & Analytical Boundaries | Detect missingness/duplicates, identify unsupported requests, and clarify material ambiguity | 3 | 12% |
| Statistical Analysis | Quantify uncertainty, compare groups, test hypotheses, and measure association/effect size | 4 | 17% |
| Predictive Analysis | Execute reproducible regression/classification and detect leakage or invalid setup | 4 | 17% |
| **Total** |  | **24** | **100%** |

The Reliability Stress Set continues to cover metric semantics, population, numerator/denominator, entity grain, multi-table joins, pre-aggregation, business-event time, clarification, memory, and structured Evidence. These are reported as reliability dimensions rather than duplicated as Capability tracks.

## 4. Difficulty Model

Difficulty describes reasoning and contract burden, not merely the number of rows or tables.

| Level | Definition | Target share in Capability V2 |
|---|---|---:|
| L1: Basic | One clear analysis goal, direct fields, deterministic result, little ambiguity | 8 cases / 33% |
| L2: Applied | Multiple outputs or transformations, explicit population, comparison or method choice | 11 cases / 46% |
| L3: Challenge | Ambiguity, denominator/grain risk, leakage risk, multiple valid methods, or fail-closed behavior | 5 cases / 21% |

Clarification and unsupported requests are behavioral expectations, not automatically the highest difficulty. Existing Olist difficulties should remain historically intact until a separately versioned remapping is audited.

## 5. Dataset Portfolio

Capability V2 should remain small enough to audit but diverse enough to prevent one schema from dominating.

| Dataset family | Structure | Main use |
|---|---|---|
| Retail transactions | Single-table categorical and numeric data | Core filtering, aggregation, ranking, distributions |
| Operational time series | Timestamp, entity, segment, numerator and denominator measures | Trend and diagnostic cases |
| Behavioral events | User, event, event time, session/cohort identifiers | Funnel, cohort, retention, repeat behavior |
| Experiment/statistical groups | Treatment/group, outcome, covariates | Confidence intervals, tests, effect sizes, association |
| Classification and regression fixtures | Fixed targets, features, leakage traps, deterministic splits | Predictive cases |
| Dirty operational table | Missing values, duplicates, malformed dates, suspicious keys | Data quality and fail-closed behavior |
| Olist 2017 multi-table fixture | Orders, payments, items, products, reviews | Reliability Stress Set only |

Prefer committed synthetic or deterministically sampled fixtures. Every generated fixture must store a seed, generator version, row count, schema, and content hash. Dataset diversity should come from genuinely different analytical structures, not cosmetic column renaming.

## 6. Case Template

V2 can initially represent the following as benchmark metadata without changing the product schema.

```yaml
id: stable_case_id
benchmark: capability_v2 | reliability_olist_v2
track: statistical_analysis
capability: group_comparison
difficulty: L2
question: user-facing request
datasets: [dataset_id]
project_id: null

expected_behavior:
  branch: analysis | clarification | unsupported
  analysis_unit: optional explicit unit
  required_method_properties: []
  prohibited_assumptions: []

expected_outputs:
  - key: stable_fact_identity
    kind: scalar | dataset | ranking | interval | model_metric
    value_scale: raw | fraction | percent | null
    required: true

reference:
  type: deterministic | deterministic_plus_rubric | rubric
  source: independent_reference_function
  tolerance: explicit tolerance policy

scoring:
  strict_requirements: []
  diagnostic_checks: []

audit:
  fixture_hash: sha256
  reference_version: version
  reviewed_by: human review record
```

The template separates user intent, expected behavior, output identity, and scoring. It must not embed generated Agent answers as ground truth.

## 7. Reference Generation And Audit

### 7.1 Shared principles

1. Generate numerical references with independent Python code that does not import Agent planning, code generation, or result parsing.
2. Commit fixtures, generators, reference outputs, seeds, splits, and critical parameters.
3. Use explicit tolerances based on computation type, not a single global percentage.
4. Record `dataset_hash`, `reference_version`, Python/library versions, and random seed in reference metadata.
5. Audit every new case in two passes: calculation review and question/reference alignment review.
6. Never use the Agent's own answer to create or repair expected values.

### 7.2 Reference method by case type

| Case type | Reference | Required checks |
|---|---|---|
| Deterministic metric/aggregation | Pandas/NumPy reference | Exact entity/population, aggregation, value and scale |
| Ranking/segmentation | Deterministic ordered records | Identity, value, sort direction, N, tie policy, eligibility |
| Trend/diagnostic | Deterministic period table plus compact rubric | Period boundaries, overall/period consistency, change values, supported driver ordering |
| Funnel/cohort | Deterministic event-state reference | Analysis unit, eligibility, event order, entry event, return event, denominator and window |
| Statistical analysis | SciPy/statsmodels reference plus method rubric | Method, statistic, p-value/CI, effect size, direction, uncertainty and non-causal conclusion |
| Predictive modeling | scikit-learn reference with frozen setup | Target, features, preprocessing, split, seed, leakage checks, model family and multiple metrics |
| Clarification/unsupported | Authored semantic rubric | Missing authority, required clarification points, prohibited execution or causal claim |

Different but valid statistical or modeling methods should not automatically fail. The scorer should first check whether the method satisfies the case's required properties, then compare method-compatible outputs. If outputs are not directly comparable, the case uses an audited rubric instead of forcing one reference number.

## 8. Scoring Model

### 8.1 Per-case dimensions

Each case should report these dimensions independently:

1. **Plan validity:** canonical Plan exists.
2. **Readiness behavior:** Ready, clarification, or fail-closed branch matches the case.
3. **Semantic contract:** population, denominator, grain, time, target, method, and assumptions match required semantics.
4. **Code adherence and execution:** generated code implements the Plan and executes successfully.
5. **Result validity:** `AnalysisResult` satisfies its schema and requested output types.
6. **Evidence coverage:** every required output has stable machine-readable Evidence.
7. **Reference correctness:** numerical, set, ranking, interval, or model outputs pass their reference checks.
8. **Interpretation boundary:** final answer explains the result without unsupported causal or certainty claims.
9. **Clarification correctness:** required clarification stops safely; unnecessary clarification is also visible.

### 8.2 Strict E2E pass

A strict pass requires every case-level hard requirement. Execution success alone never passes a case. Supporting diagnostics such as latency, token usage, replan, and repair remain visible without replacing correctness.

### 8.3 Reported scorecards

Publish separate scorecards rather than one weighted score:

- capability-track strict E2E rate;
- numerical/reference correctness among executed cases;
- semantic-contract correctness;
- Evidence completeness;
- expected clarification and fail-closed correctness;
- execution and result-validity rates;
- replan and repair rates;
- failure-layer distribution;
- L1/L2/L3 performance.

No combined Capability-plus-Olist accuracy should be calculated.

## 9. Deterministic Versus Rubric Evaluation

| Output | Deterministic reference? | Rubric needed? |
|---|---:|---:|
| Counts, sums, means, ratios, quantiles | Yes | Only for explanation boundaries |
| Top-N and segments | Yes, with tie policy | Sometimes for segment interpretation |
| Time-series rows and period change | Yes | Yes for driver claims |
| Funnel and cohort tables | Yes after semantics are fixed | Yes for unsupported assumptions |
| Statistical estimates | Yes, method-compatible | Yes for method suitability and causal boundary |
| Predictive metrics | Yes under frozen setup | Yes when an alternative valid model is allowed |
| Business recommendations | Partially | Yes, with explicit evidence requirements |
| Clarification and unsupported requests | Usually no scalar reference | Yes, deterministic keyword checks may support but not replace review |

An LLM judge may be added later as a secondary diagnostic, never as the sole source of truth for deterministic facts or hard safety behavior.

## 10. First-Failure Taxonomy

Every failed turn should be assigned to the earliest layer that made success impossible:

1. Fixture/reference defect
2. Upload/profile/data access
3. Retrieval or metric grounding
4. RMC/project knowledge resolution
5. Planner semantic reasoning
6. Plan serialization/normalization
7. Readiness Gate decision
8. Code adherence or generation
9. Sandbox/runtime
10. Result contract
11. Evidence coverage
12. Validator false negative/positive
13. Final-answer interpretation
14. Scorer/representation
15. Benchmark/spec ambiguity

The Gate is not automatically the root cause when it correctly exposes an incomplete Plan. A benchmark failure is not automatically a product semantic failure when the calculation is correct but the scorer or reference is defective.

## 11. Core Regression Set

The 12-case Core Regression Set should be selected only after each candidate has a stable reference and expected product branch.

Recommended composition:

| Source | Count | Coverage |
|---|---:|---|
| Capability V2 | 8 | Basic descriptive, filter, ranking, time, one statistical, one predictive, one data-quality, one behavioral or clarification case |
| Olist-24 | 4 | Executive metric golden case, time/metric case, payment grain case, and expected clarification |

Selection rules:

- include both successful analyses and expected fail-closed behavior;
- prefer deterministic, high-signal cases with low reference ambiguity;
- include at least one multi-table grain/denominator regression;
- exclude cases with unresolved benchmark assumptions until the spec is versioned;
- freeze case IDs and reference hashes for a milestone;
- replace a regression case only through an explicit benchmark version change.

Run policy:

- deterministic unit/reference tests on every relevant code change;
- Core Regression Set before a milestone or reliability commit;
- Capability V2 before a public capability baseline;
- Olist-24 before a reliability baseline;
- repeat stochastic baseline runs three times before making stability claims.

## 12. Artifact And Reproducibility Contract

Each run artifact should record:

- benchmark name and version;
- case and reference versions;
- timestamp and Git commit;
- configured and actual model/provider when available;
- prompt/configuration version;
- dataset hashes and seeds;
- Python/library versions for deterministic references;
- per-turn Plan, Gate, code, sandbox, AnalysisResult, Evidence, Validator, and final answer;
- replan/repair counts and latency;
- per-dimension score and first failure layer.

Artifacts containing generated outputs remain Git-ignored; publishable baseline summaries must preserve aggregate facts, known scorer issues, and links to committed case/reference definitions.

## 13. Recommended V2 Case Portfolio

### 13.1 Capability Benchmark V2: 24 cases

| Track | L1 | L2 | L3 | Total | Typical cases |
|---|---:|---:|---:|---:|---|
| Core Tabular | 3 | 2 | 0 | 5 | Descriptive, conditional metric, grouped comparison, ranking, distribution |
| Time & Diagnostic | 1 | 2 | 1 | 4 | Period trend, MoM comparison, segment contribution, misleading aggregate |
| Behavioral | 1 | 2 | 1 | 4 | Funnel, cohort retention, repeat behavior, lifecycle segment |
| Data Quality & Boundaries | 1 | 1 | 1 | 3 | Missingness/duplicates, ambiguous request, unsupported causal or unavailable-data request |
| Statistical | 1 | 2 | 1 | 4 | CI, group comparison/effect size, correlation, method-boundary case |
| Predictive | 1 | 2 | 1 | 4 | Logistic, random forest, linear regression, leakage/fail-closed case |
| **Total** | **8** | **11** | **5** | **24** |  |

### 13.2 Reliability Stress Set: 24 cases

Keep Olist-24 frozen in the first V2 release. Do not silently repair historical expected values. Cases with confirmed scorer defects or hidden assumptions should retain their raw historical result and receive an explicit `spec_status` in a future benchmark metadata version before rescoring.

Future cross-domain reliability cases may be added only after V2 is stable; they should not delay the initial V2 capability expansion.

## 14. Migration From Current V1

1. **Freeze current evidence.** Preserve the 13-case capability artifact, post-RMC Olist artifact, commit hashes, and current documentation.
2. **Map, do not rewrite.** Assign the existing 13 Capability cases and 24 Olist cases to the V2 taxonomy and failure taxonomy without changing expected values.
3. **Audit current references.** Record fixture hashes, tolerance rationale, output identities, and known ambiguity/scorer issues.
4. **Select Core Regression candidates.** Choose 12 stable existing cases first; do not create new cases merely to fill the subset.
5. **Add only demonstrated gaps.** Design the 11 additional Capability cases in small batches, starting with time/diagnostic, data quality/boundaries, and one additional behavioral case.
6. **Generate independent references.** Add or extend deterministic reference scripts before running the Agent.
7. **Pilot each new case.** Run as a probe, diagnose reference or contract ambiguity, then freeze the case. Do not patch the product solely to make a probe pass.
8. **Version the suite.** Freeze Capability V2 case JSON, reference JSON, fixture hashes, and scoring contract together.
9. **Run the baseline.** Use a fixed model/configuration, save full artifacts, manually audit pass and fail samples, and publish track-level results.
10. **Keep historical scores.** V1 and Olist historical baselines remain available and are never overwritten.

## 15. Complexity Guardrails

This is a portfolio product, not a research benchmark platform.

- Reuse the existing capability and business runners before considering a unified runner.
- Add benchmark metadata before adding product schema.
- Prefer deterministic references and explicit rubrics over a validator framework or multi-Agent judge.
- Do not add a new product contract until a repeated probe demonstrates a real product failure that prompt, Skill, or benchmark metadata cannot express.
- Every architectural addition must be explainable in one or two interview minutes: the failure, the minimal fix, and the measured result.
- Do not add forecasting, clustering, causal inference, image analysis, SQL sources, or model deployment to V2 merely for coverage.

## 16. Initial V2 Recommendation

The first implementation phase should do only two things:

1. formalize the 12-case Core Regression subset from existing stable cases;
2. add a small, independently referenced batch for Time/Diagnostic and Data Quality/Boundary gaps.

Funnel/cohort, advanced statistical alternatives, and predictive leakage cases should continue through **Probe → Audit → Freeze** before becoming scored V2 cases.
