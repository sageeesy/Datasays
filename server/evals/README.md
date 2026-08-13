# DataSays Evaluation Harness

This folder contains a lightweight benchmark harness for tabular QA evaluation.

It is intentionally small: the goal is to turn the prototype from subjective demo testing into repeatable checks with expected answers.

The case design is inspired by common public benchmarks:

- DS-1000 style: executable data-science code generation with pass/fail scoring.
- DABench/DABstep style: closed-form data analysis questions over CSV-like tabular data.
- MLE-bench style: basic machine-learning workflow execution, represented here by a small RandomForest training-accuracy case.

## What It Measures

- Execution success rate
- Structured `AnalysisResult` coverage
- Deterministic validation pass rate and confidence
- Numeric answer pass/fail with tolerance
- Absolute numeric error
- End-to-end latency
- Repair-loop metadata returned by `/api/query`
- Repair success rate after an initial execution or validation failure

## Task Coverage

The default mini benchmark currently contains 24 balanced closed-form cases across 4 small CSV datasets. It covers:

- `basic_statistics`: row count, max/min style questions
- `filter_aggregate`: filtered sum/mean questions
- `groupby_aggregate`: group-by aggregation
- `multi_table_join`: joining multiple CSV files before aggregation
- `multi_step_join_groupby`: join + derived metric + group-by
- `date_time_analysis`: date filtering and date-range calculations
- `data_quality`: missing-value and data-cleaning checks
- `basic_ml_workflow`: a small sklearn RandomForest workflow

## Run

Start the FastAPI backend first:

```bash
cd server
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Then run:

```bash
cd server
python3 evals/run_eval.py
```

Optional:

```bash
python3 evals/run_eval.py --api-base http://127.0.0.1:8000 --cases evals/benchmark_cases.json
```

## Notes

- The backend still needs `OPENROUTER_API_KEY` for LLM calls.
- The benchmark uploads the CSV files under `evals/data/`, runs each question through `/api/query`, scores the structured sandbox `primary_value`, and deletes uploaded files afterward.
- Text-number extraction is only a compatibility fallback for responses produced by the pre-P0 API.
- Add more cases to `benchmark_cases.json` to expand coverage.
- Cases can specify one or more datasets via the `datasets` field. The runner maps those dataset names to uploaded `fileIds`.
