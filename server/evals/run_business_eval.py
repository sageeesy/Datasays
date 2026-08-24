#!/usr/bin/env python3
"""Run and score the capability-oriented Olist business benchmark."""

import argparse
import asyncio
import json
import math
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from evals.run_eval import (  # noqa: E402
    _delete_local_file,
    _in_process_query,
    _json_request,
    _load_dataset_config,
    _stage_file_locally,
    _upload_file,
)


def _analysis_result(response: Dict[str, Any]) -> Dict[str, Any]:
    sandbox = response.get("sandboxResponse") or {}
    output = sandbox.get("output") or {}
    metadata = sandbox.get("metadata") or {}
    result = output.get("analysis_result") or metadata.get("analysis_result") or {}
    return result if isinstance(result, dict) else {}


def _text_corpus(response: Dict[str, Any]) -> str:
    sandbox = response.get("sandboxResponse") or {}
    metadata = sandbox.get("metadata") or {}
    values = [
        sandbox.get("content", ""),
        _analysis_result(response),
        metadata.get("plan") or {},
    ]
    return "\n".join(
        item if isinstance(item, str) else json.dumps(item, ensure_ascii=False, default=str)
        for item in values
    )


def _contains_term(corpus: str, term: Any) -> bool:
    needle = str(term).strip()
    if not needle:
        return False
    if needle.isascii() and needle.isalnum() and len(needle) <= 3:
        return re.search(rf"(?<![A-Za-z0-9_]){re.escape(needle)}(?![A-Za-z0-9_])", corpus, re.I) is not None
    return needle.casefold() in corpus.casefold()


def _flatten_numbers(value: Any) -> List[float]:
    numbers: List[float] = []
    if isinstance(value, bool):
        return numbers
    if isinstance(value, (int, float)):
        number = float(value)
        if math.isfinite(number):
            numbers.append(number)
        return numbers
    if isinstance(value, dict):
        for item in value.values():
            numbers.extend(_flatten_numbers(item))
    elif isinstance(value, list):
        for item in value:
            numbers.extend(_flatten_numbers(item))
    return numbers


def _score_fact(fact: Dict[str, Any], response: Dict[str, Any]) -> Dict[str, Any]:
    expected = fact.get("value")
    corpus = _text_corpus(response)
    matched_value: Any = None
    absolute_error: Optional[float] = None

    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        candidates = _flatten_numbers(_analysis_result(response))
        tolerance = float(fact.get("tolerance", 0.001))
        if candidates:
            errors = [abs(candidate - float(expected)) for candidate in candidates]
            index = min(range(len(errors)), key=errors.__getitem__)
            matched_value = candidates[index]
            absolute_error = errors[index]
            value_passed = absolute_error <= tolerance
        else:
            value_passed = False
    else:
        value_passed = _contains_term(corpus, expected)
        matched_value = expected if value_passed else None

    terms = fact.get("terms") or []
    context_passed = not terms or any(_contains_term(corpus, term) for term in terms)
    return {
        "id": fact.get("id"),
        "expected": expected,
        "observed": matched_value,
        "absolute_error": absolute_error,
        "value_passed": value_passed,
        "context_passed": context_passed,
        "passed": value_passed and context_passed,
    }


def _score_term_groups(groups: Sequence[Sequence[str]], corpus: str) -> Dict[str, Any]:
    results = [
        {
            "terms": list(group),
            "matched": [term for term in group if _contains_term(corpus, term)],
        }
        for group in groups
    ]
    covered = sum(bool(item["matched"]) for item in results)
    return {
        "covered": covered,
        "total": len(results),
        "coverage": covered / len(results) if results else 1.0,
        "groups": results,
    }


def _score_response(response: Dict[str, Any], expectation: Dict[str, Any]) -> Dict[str, Any]:
    sandbox = response.get("sandboxResponse") or {}
    metadata = sandbox.get("metadata") or {}
    result = _analysis_result(response)
    corpus = _text_corpus(response)
    plan = metadata.get("plan") or {}

    fact_results = [_score_fact(item, response) for item in expectation.get("facts", [])]
    fact_recall = (
        sum(item["passed"] for item in fact_results) / len(fact_results)
        if fact_results else 1.0
    )
    term_score = _score_term_groups(expectation.get("required_term_groups", []), corpus)

    expected_clarification = bool(expectation.get("clarification"))
    observed_clarification = bool(plan.get("needs_clarification"))
    clarification_terms = expectation.get("clarification_terms") or []
    clarification_term_coverage = (
        sum(_contains_term(corpus, term) for term in clarification_terms) / len(clarification_terms)
        if clarification_terms else 1.0
    )
    clarification_passed = (
        observed_clarification and not result and clarification_term_coverage >= 0.5
        if expected_clarification else not observed_clarification
    )

    expected_memory = expectation.get("memory_used")
    observed_memory = bool((metadata.get("memory") or {}).get("used"))
    memory_passed = None if expected_memory is None else observed_memory is bool(expected_memory)

    expected_metrics = expectation.get("metric_ids") or []
    observed_metrics = plan.get("metric_ids") or []
    metric_passed = None if not expected_metrics else set(expected_metrics).issubset(set(observed_metrics))

    expected_visuals = expectation.get("visualization_types") or []
    observed_visuals = [
        item.get("type") for item in result.get("visualizations", [])
        if isinstance(item, dict) and item.get("type")
    ]
    visualization_passed = (
        None if not expected_visuals else bool(set(expected_visuals).intersection(observed_visuals))
    )

    expected_intents = expectation.get("plan_intents") or []
    observed_intent = plan.get("intent")
    intent_passed = None if not expected_intents else observed_intent in expected_intents
    status_passed = sandbox.get("status") == "success"
    structured_passed = not result if expected_clarification else bool(result)

    hard_checks = [
        status_passed,
        structured_passed,
        fact_recall >= float(expectation.get("min_fact_recall", 1.0)),
        term_score["coverage"] >= float(expectation.get("min_term_coverage", 0.5)),
        clarification_passed,
    ]
    if memory_passed is not None:
        hard_checks.append(memory_passed)

    return {
        "passed": all(hard_checks),
        "status_passed": status_passed,
        "structured_result_present": bool(result),
        "structured_contract_passed": structured_passed,
        "fact_recall": fact_recall,
        "fact_results": fact_results,
        "term_coverage": term_score["coverage"],
        "term_groups": term_score["groups"],
        "clarification_expected": expected_clarification,
        "clarification_observed": observed_clarification,
        "clarification_term_coverage": clarification_term_coverage,
        "clarification_passed": clarification_passed,
        "memory_expected": expected_memory,
        "memory_observed": observed_memory,
        "memory_passed": memory_passed,
        "expected_metric_ids": expected_metrics,
        "observed_metric_ids": observed_metrics,
        "metric_expectation_passed": metric_passed,
        "expected_visualization_types": expected_visuals,
        "observed_visualization_types": observed_visuals,
        "visualization_expectation_passed": visualization_passed,
        "expected_plan_intents": expected_intents,
        "observed_plan_intent": observed_intent,
        "plan_intent_passed": intent_passed,
        "validation_passed": (metadata.get("validation_report") or {}).get("passed"),
        "repair_attempts": metadata.get("repair_attempts", 0),
    }


def _mean(values: Iterable[Optional[float]]) -> Optional[float]:
    present = [float(value) for value in values if value is not None]
    return sum(present) / len(present) if present else None


async def _create_conversation(api_base: str, file_ids: List[str], in_process: bool) -> str:
    if in_process:
        from app.services.conversation_service import create_conversation

        conversation = await asyncio.to_thread(
            create_conversation, "Benchmark conversation", file_ids
        )
        return conversation["id"]
    response = await asyncio.to_thread(
        _json_request,
        f"{api_base}/api/conversations",
        "POST",
        {"title": "Benchmark conversation", "activeFileIds": file_ids},
    )
    return response["conversation"]["id"]


async def _delete_conversation(api_base: str, conversation_id: str, in_process: bool) -> None:
    if in_process:
        from app.services.conversation_service import delete_conversation

        await asyncio.to_thread(delete_conversation, conversation_id)
        return
    await asyncio.to_thread(
        _json_request,
        f"{api_base}/api/conversations/{conversation_id}",
        "DELETE",
    )


def _case_turns(case: Dict[str, Any]) -> List[Dict[str, Any]]:
    if case.get("turns"):
        return case["turns"]
    return [{"question": case["question"], "expected": case["expected"]}]


def _category_summary(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    summaries: Dict[str, Dict[str, Any]] = {}
    for item in results:
        summary = summaries.setdefault(item["category"], {"total": 0, "passed": 0})
        summary["total"] += 1
        summary["passed"] += int(item["passed"])
    for summary in summaries.values():
        summary["pass_rate"] = summary["passed"] / summary["total"]
    return summaries


async def run_business_eval(
    api_base: str,
    cases_path: Path,
    case_ids: Optional[Sequence[str]] = None,
    model_override: Optional[str] = None,
    local_files: bool = False,
    in_process_api: bool = False,
) -> Dict[str, Any]:
    config = json.loads(cases_path.read_text(encoding="utf-8"))
    datasets = _load_dataset_config(config)
    defaults = config.get("defaults", {})
    model = model_override or defaults.get("model")
    prompt_style = defaults.get("prompt_style", "zero")
    cases = config["cases"]

    if case_ids:
        requested = set(case_ids)
        missing = requested - {case["id"] for case in cases}
        if missing:
            raise ValueError(f"Unknown benchmark case IDs: {', '.join(sorted(missing))}")
        cases = [case for case in cases if case["id"] in requested]

    required = {name for case in cases for name in case.get("datasets", [])}
    datasets = {name: value for name, value in datasets.items() if name in required}
    uploaded: Dict[str, str] = {}
    results: List[Dict[str, Any]] = []
    asgi_app = None
    if in_process_api:
        local_files = True
        from main import app

        asgi_app = app

    try:
        for name, dataset in datasets.items():
            path = cases_path.parent / dataset["path"]
            uploaded[name] = (
                await _stage_file_locally(path)
                if local_files
                else await asyncio.to_thread(_upload_file, api_base, path)
            )

        for case in cases:
            file_ids = [uploaded[name] for name in case["datasets"]]
            turns = _case_turns(case)
            conversation_id = (
                await _create_conversation(api_base, file_ids, in_process_api)
                if len(turns) > 1
                else None
            )
            turn_results: List[Dict[str, Any]] = []
            try:
                for index, turn in enumerate(turns, start=1):
                    payload = {
                        "question": turn["question"],
                        "fileIds": file_ids,
                        "prompt_style": turn.get("prompt_style", case.get("prompt_style", prompt_style)),
                        "model": turn.get("model", case.get("model", model)),
                    }
                    if conversation_id:
                        payload["conversationId"] = conversation_id
                    started = time.perf_counter()
                    response = (
                        await _in_process_query(asgi_app, payload)
                        if asgi_app is not None
                        else await asyncio.to_thread(
                            _json_request,
                            f"{api_base}/api/query",
                            "POST",
                            payload,
                        )
                    )
                    score = _score_response(response, turn["expected"])
                    sandbox = response.get("sandboxResponse") or {}
                    metadata = sandbox.get("metadata") or {}
                    turn_results.append({
                        "turn": index,
                        "question": turn["question"],
                        "latency_seconds": round(time.perf_counter() - started, 3),
                        **score,
                        "answer": sandbox.get("content"),
                        "structured_result": _analysis_result(response) or None,
                        "plan": metadata.get("plan") or {},
                        "memory": metadata.get("memory") or {},
                        "validation_report": metadata.get("validation_report") or None,
                    })
            finally:
                if conversation_id:
                    await _delete_conversation(api_base, conversation_id, in_process_api)

            results.append({
                "id": case["id"],
                "category": case["category"],
                "difficulty": case.get("difficulty"),
                "user_need": case.get("user_need"),
                "capability": case.get("capability"),
                "datasets": case["datasets"],
                "passed": all(turn["passed"] for turn in turn_results),
                "turns": turn_results,
            })
    finally:
        for name, file_id in uploaded.items():
            try:
                if local_files:
                    await _delete_local_file(file_id)
                else:
                    await asyncio.to_thread(
                        _json_request,
                        f"{api_base}/api/files/{file_id}",
                        "DELETE",
                    )
            except Exception as exc:
                print(f"Warning: failed to delete eval file {name}/{file_id}: {exc}")

    turns = [turn for case in results for turn in case["turns"]]
    passed = sum(case["passed"] for case in results)
    clarification_turns = [turn for turn in turns if turn["clarification_expected"]]
    memory_turns = [turn for turn in turns if turn["memory_expected"] is not None]
    metric_turns = [turn for turn in turns if turn["metric_expectation_passed"] is not None]
    visual_turns = [turn for turn in turns if turn["visualization_expectation_passed"] is not None]
    intent_turns = [turn for turn in turns if turn["plan_intent_passed"] is not None]

    return {
        "benchmark_name": config.get("benchmark_name"),
        "benchmark_version": config.get("version"),
        "model": model,
        "file_transport": "local_store" if local_files else "http_upload",
        "api_transport": "in_process_asgi" if in_process_api else "http",
        "total_cases": len(results),
        "total_turns": len(turns),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": passed / len(results) if results else 0,
        "fact_recall": _mean(turn["fact_recall"] for turn in turns),
        "business_term_coverage": _mean(turn["term_coverage"] for turn in turns),
        "execution_success_rate": _mean(float(turn["status_passed"]) for turn in turns),
        "structured_result_rate": _mean(float(turn["structured_result_present"]) for turn in turns if not turn["clarification_expected"]),
        "validation_pass_rate": _mean(float(turn["validation_passed"]) for turn in turns if turn["validation_passed"] is not None),
        "clarification_accuracy": _mean(float(turn["clarification_passed"]) for turn in clarification_turns),
        "memory_accuracy": _mean(float(turn["memory_passed"]) for turn in memory_turns),
        "metric_adoption_rate": _mean(float(turn["metric_expectation_passed"]) for turn in metric_turns),
        "visualization_coverage": _mean(float(turn["visualization_expectation_passed"]) for turn in visual_turns),
        "plan_intent_accuracy": _mean(float(turn["plan_intent_passed"]) for turn in intent_turns),
        "average_latency_seconds": _mean(turn["latency_seconds"] for turn in turns),
        "category_summary": _category_summary(results),
        "results": results,
    }


async def _run_cli(args: argparse.Namespace) -> int:
    report = await run_business_eval(
        args.api_base.rstrip("/"), Path(args.cases), args.case_ids,
        model_override=args.model, local_files=args.local_files,
        in_process_api=args.in_process_api,
    )
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(json.dumps(
        {key: value for key, value in report.items() if key != "results"}
        if args.summary_only else report,
        indent=2,
        ensure_ascii=False,
    ))
    return 0 if report["failed"] == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DataSays Olist Business Analysis Suite v2.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--cases", default=str(Path(__file__).with_name("business_benchmark_cases.json")))
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--model")
    parser.add_argument("--local-files", action="store_true")
    parser.add_argument("--in-process-api", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()

    return asyncio.run(_run_cli(args))


if __name__ == "__main__":
    raise SystemExit(main())
