#!/usr/bin/env python3
"""Run the frozen Core-5 benchmark and experimental capability probes."""

import argparse
import asyncio
import json
import math
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from dotenv import load_dotenv


SERVER_DIR = Path(__file__).resolve().parents[1]
EVAL_DIR = Path(__file__).resolve().parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

load_dotenv(SERVER_DIR / ".env")

from evals.run_eval import _delete_local_file, _in_process_query, _stage_file_locally


def _flatten(value: Any, path: str = "") -> List[Tuple[str, Any]]:
    leaves: List[Tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            leaves.extend(_flatten(item, f"{path}.{key}" if path else str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            leaves.extend(_flatten(item, f"{path}[{index}]"))
    elif value is not None:
        leaves.append((path, value))
    return leaves


def _resolve_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        current = current[part]
    return current


def _numeric_match(expected: float, observed: Iterable[Any], final_answer: bool = False) -> bool:
    tolerance = max(1e-6, abs(expected) * (0.015 if final_answer else 0.002))
    for value in observed:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if math.isfinite(float(value)) and abs(float(value) - expected) <= tolerance:
                return True
    return False


def _leaf_match(expected: Any, observed: List[Tuple[str, Any]], final_answer: bool = False) -> bool:
    values = [item for _, item in observed]
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return _numeric_match(float(expected), values, final_answer)
    if isinstance(expected, str):
        rendered = json.dumps(values, ensure_ascii=False).lower()
        return expected.lower() in rendered
    return expected in values


def _expected_checks(reference: Dict[str, Any], paths: List[str], observed: Any) -> Dict[str, Any]:
    observed_leaves = _flatten(observed)
    checks: List[Dict[str, Any]] = []
    for path in paths:
        expected_value = _resolve_path(reference, path)
        expected_leaves = _flatten(expected_value, path)
        matched = sum(_leaf_match(value, observed_leaves) for _, value in expected_leaves)
        checks.append({
            "path": path,
            "expected_leaf_count": len(expected_leaves),
            "matched_leaf_count": matched,
            "passed": matched == len(expected_leaves),
        })
    total = sum(item["expected_leaf_count"] for item in checks)
    matched = sum(item["matched_leaf_count"] for item in checks)
    return {"checks": checks, "matched": matched, "total": total, "coverage": matched / total if total else 1.0}


def _evidence_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    datasets = {item.get("id"): item for item in result.get("datasets", [])}
    evidence = result.get("evidence", [])
    linked_rows = []
    for item in evidence:
        if item.get("kind") == "dataset" and item.get("dataset_id") in datasets:
            linked_rows.append(datasets[item["dataset_id"]])
    return {"evidence": evidence, "linked_datasets": linked_rows}


def _final_answer_values(content: str) -> List[Tuple[str, Any]]:
    values: List[Tuple[str, Any]] = [("text", content)]
    for index, token in enumerate(re.findall(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?:[eE][-+]?\d+)?", content)):
        try:
            values.append((f"number[{index}]", float(token.replace(",", ""))))
        except ValueError:
            pass
    return values


def _method_check(code: str, tokens: List[str]) -> Dict[str, Any]:
    compact_code = re.sub(r"\s+", "", code).lower()
    missing = [token for token in tokens if re.sub(r"\s+", "", token).lower() not in compact_code]
    return {"passed": not missing, "missing_tokens": missing}


def _plan_ready(metadata: Dict[str, Any]) -> bool:
    return bool(((metadata.get("planner") or {}).get("completeness") or {}).get("ready_for_code_generation"))


def _first_failure(
    plan_ready: bool,
    code: str,
    sandbox_status: str,
    calculation_coverage: float,
    evidence_coverage: float,
    validation_passed: Optional[bool],
) -> str:
    if not plan_ready:
        return "Planner / Gate"
    if not code:
        return "Code Generator"
    if sandbox_status != "success":
        return "Sandbox / Execution"
    if calculation_coverage < 1.0:
        return "Calculation / Method"
    if evidence_coverage < 1.0:
        return "Evidence / Output Contract"
    if validation_passed is not True:
        return "Validator"
    return "None"


def _classification(item: Dict[str, Any]) -> str:
    if not item["plan_ready"] or item["sandbox_status"] != "success":
        return "Unsupported" if not item["code_generated"] else "Unstable"
    if item["calculation"]["coverage"] == 1.0 and item["evidence_score"]["coverage"] == 1.0:
        return "Product-ready" if item["track"] == "core" and item["method"]["passed"] else "Works with current generic architecture"
    if item["calculation"]["coverage"] == 1.0:
        return "Works computationally but lacks structured contract"
    return "Unstable"


async def _run_case(case: Dict[str, Any], reference: Dict[str, Any], file_id: str, model: str) -> Dict[str, Any]:
    from main import app

    started = time.perf_counter()
    try:
        response = await _in_process_query(app, {
            "question": case["question"],
            "fileIds": [file_id],
            "model": model,
            "prompt_style": "zero",
        })
    except Exception as exc:
        return {
            "id": case["id"], "track": case["track"], "capability": case["capability"],
            "question": case["question"], "latency_seconds": round(time.perf_counter() - started, 3),
            "request_error": str(exc), "first_failure_layer": "API / Workflow", "classification": "Unsupported",
        }

    sandbox = response.get("sandboxResponse") or {}
    metadata = sandbox.get("metadata") or {}
    output = sandbox.get("output") or {}
    result = output.get("analysis_result") or metadata.get("analysis_result") or {}
    validation = metadata.get("validation_report") or {}
    code = sandbox.get("code") or ""
    calculation = _expected_checks(reference, case["expected_paths"], result)
    evidence_score = _expected_checks(reference, case["expected_paths"], _evidence_payload(result))
    final_leaves = _final_answer_values(sandbox.get("content") or "")
    final_matched = sum(
        _leaf_match(value, final_leaves, final_answer=True)
        for path in case["expected_paths"]
        for _, value in _flatten(_resolve_path(reference, path), path)
    )
    final_total = sum(len(_flatten(_resolve_path(reference, path), path)) for path in case["expected_paths"])
    method = _method_check(code, case.get("method_tokens", []))
    plan = metadata.get("plan") or {}
    plan_text = json.dumps(plan, ensure_ascii=False).lower()
    fields = {column.lower(): column.lower() in plan_text or column.lower() in code.lower() for column in case["required_columns"]}
    ready = _plan_ready(metadata)
    first_failure = _first_failure(
        ready, code, sandbox.get("status"), calculation["coverage"], evidence_score["coverage"], validation.get("passed")
    )
    item = {
        "id": case["id"], "track": case["track"], "capability": case["capability"],
        "difficulty": case["difficulty"], "dataset": case["dataset"], "question": case["question"],
        "reference": reference, "latency_seconds": round(time.perf_counter() - started, 3),
        "plan": plan, "planner": metadata.get("planner"), "plan_ready": ready,
        "retrieved_metrics": metadata.get("retrieved_metrics", []),
        "resolved_metric_candidates": metadata.get("resolved_metric_candidates", []),
        "field_selection": {"passed": all(fields.values()), "fields": fields},
        "selected_skills": metadata.get("selected_skills", []),
        "code_generated": bool(code), "generated_code": code, "method": method,
        "sandbox_status": sandbox.get("status"), "analysis_result": result,
        "calculation": calculation, "evidence_score": evidence_score,
        "final_answer": sandbox.get("content"),
        "final_answer_reference_coverage": final_matched / final_total if final_total else 1.0,
        "validation": validation, "repair_attempts": metadata.get("repair_attempts", 0),
        "execution_attempts": metadata.get("execution_attempts", []),
        "first_failure_layer": first_failure,
    }
    item["classification"] = _classification(item)
    return item


async def run(cases_path: Path, output_path: Path, case_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    config = json.loads(cases_path.read_text(encoding="utf-8"))
    references = json.loads((cases_path.parent / "capability_probe_references.json").read_text(encoding="utf-8"))
    cases = config["cases"]
    if case_ids:
        requested = set(case_ids)
        cases = [case for case in cases if case["id"] in requested]
    dataset_keys = list(dict.fromkeys(case["dataset"] for case in cases))
    file_ids: Dict[str, str] = {}
    results: List[Dict[str, Any]] = []
    output_path.parent.mkdir(parents=True, exist_ok=True)
    artifact: Dict[str, Any] = {
        "name": "DataSays Analysis Capability Probe",
        "design": "Probe -> Freeze -> Implement",
        "generated_at": datetime.now().isoformat(),
        "model": config["model"], "project_id": None,
        "reference_source": "independent deterministic Python",
        "results": results,
    }
    try:
        for key in dataset_keys:
            file_ids[key] = await _stage_file_locally(cases_path.parent / config["datasets"][key])
        for index, case in enumerate(cases, start=1):
            print(f"[{index}/{len(cases)}] {case['id']}", flush=True)
            result = await _run_case(case, references[case["id"]], file_ids[case["dataset"]], config["model"])
            results.append(result)
            output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            print(
                f"  {result.get('sandbox_status')} | calc={result.get('calculation', {}).get('coverage')} "
                f"| evidence={result.get('evidence_score', {}).get('coverage')} | {result.get('classification')}",
                flush=True,
            )
    finally:
        for file_id in file_ids.values():
            await _delete_local_file(file_id)

    artifact["summary"] = {
        "total": len(results),
        "core": sum(item.get("track") == "core" for item in results),
        "experimental": sum(item.get("track") == "experimental" for item in results),
        "plan_ready": sum(item.get("plan_ready") is True for item in results),
        "sandbox_success": sum(item.get("sandbox_status") == "success" for item in results),
        "calculation_complete": sum((item.get("calculation") or {}).get("coverage") == 1.0 for item in results),
        "evidence_complete": sum((item.get("evidence_score") or {}).get("coverage") == 1.0 for item in results),
        "classifications": {
            label: sum(item.get("classification") == label for item in results)
            for label in [
                "Product-ready", "Works with current generic architecture",
                "Works computationally but lacks structured contract", "Unstable", "Unsupported",
            ]
        },
    }
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=EVAL_DIR / "capability_probe_cases.json")
    parser.add_argument("--output", type=Path, default=EVAL_DIR / "results" / "analysis-capability-probe-20260827.json")
    parser.add_argument("--case-id", action="append", dest="case_ids")
    args = parser.parse_args()
    artifact = asyncio.run(run(args.cases, args.output, args.case_ids))
    print(json.dumps(artifact["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
