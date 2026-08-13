#!/usr/bin/env python3
"""
Lightweight benchmark runner for DataSays.

The runner uploads a CSV file, executes benchmark questions through the
FastAPI /api/query endpoint, and scores numeric answers against expected
values with tolerance.
"""

import argparse
import json
import mimetypes
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import request, error


def _json_request(url: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} for {method} {url}: {body}") from exc


def _upload_file(api_base: str, file_path: Path) -> str:
    boundary = f"----datasays-eval-{uuid.uuid4().hex}"
    mime_type = mimetypes.guess_type(file_path.name)[0] or "text/csv"
    file_bytes = file_path.read_bytes()

    body = b"".join([
        f"--{boundary}\r\n".encode("utf-8"),
        (
            f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8"),
        file_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ])

    req = request.Request(
        f"{api_base}/api/files/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Upload failed with HTTP {exc.code}: {body_text}") from exc

    return data["file"]["id"]


def _numeric_candidates(response: Dict[str, Any]) -> List[float]:
    sandbox = response.get("sandboxResponse", {})
    output = sandbox.get("output") or {}
    metadata = sandbox.get("metadata") or {}
    structured = output.get("analysis_result") or metadata.get("analysis_result") or {}

    primary_value = structured.get("primary_value")
    if isinstance(primary_value, (int, float)) and not isinstance(primary_value, bool):
        return [float(primary_value)]

    if output.get("type") == "number":
        data = output.get("data") or {}
        if "value" in data:
            return [float(data["value"])]

    # Backward-compatible fallback for responses produced by the pre-P0 API.
    candidates: List[float] = []
    content = sandbox.get("content", "")
    for match in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", content):
        candidates.append(float(match))

    return candidates


def _score_case(response: Dict[str, Any], case: Dict[str, Any], default_tolerance: float) -> Dict[str, Any]:
    expected = float(case["expected_value"])
    tolerance = float(case.get("tolerance", default_tolerance))
    candidates = _numeric_candidates(response)

    if not candidates:
        return {
            "passed": False,
            "observed_value": None,
            "absolute_error": None,
            "reason": "No numeric answer found"
        }

    errors = [abs(candidate - expected) for candidate in candidates]
    best_index = min(range(len(errors)), key=lambda idx: errors[idx])
    observed = candidates[best_index]
    absolute_error = errors[best_index]

    return {
        "passed": absolute_error <= tolerance,
        "observed_value": observed,
        "absolute_error": absolute_error,
        "reason": None if absolute_error <= tolerance else "Numeric value outside tolerance"
    }


def _load_dataset_config(config: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """Support both the original single-dataset format and the multi-dataset format."""
    if "datasets" in config:
        return config["datasets"]

    dataset = config["dataset"]
    return {
        dataset["name"]: {
            "path": dataset["path"]
        }
    }


def run_eval(api_base: str, cases_path: Path) -> Dict[str, Any]:
    config = json.loads(cases_path.read_text(encoding="utf-8"))
    datasets = _load_dataset_config(config)
    defaults = config.get("defaults", {})
    prompt_style = defaults.get("prompt_style", "zero")
    model = defaults.get("model")
    tolerance = float(defaults.get("tolerance", 0.001))

    uploaded_file_ids: Dict[str, str] = {}
    results = []

    try:
        for dataset_name, dataset_config in datasets.items():
            dataset_path = cases_path.parent / dataset_config["path"]
            uploaded_file_ids[dataset_name] = _upload_file(api_base, dataset_path)

        for case in config["cases"]:
            case_dataset_names = case.get("datasets")
            if not case_dataset_names:
                case_dataset_names = [next(iter(uploaded_file_ids.keys()))]

            file_ids = [
                uploaded_file_ids[dataset_name]
                for dataset_name in case_dataset_names
            ]

            started = time.perf_counter()
            response = _json_request(
                f"{api_base}/api/query",
                method="POST",
                payload={
                    "question": case["question"],
                    "fileIds": file_ids,
                    "prompt_style": case.get("prompt_style", prompt_style),
                    "model": case.get("model", model),
                }
            )
            latency = time.perf_counter() - started
            score = _score_case(response, case, tolerance)
            sandbox = response.get("sandboxResponse", {})
            metadata = sandbox.get("metadata") or {}
            output = sandbox.get("output") or {}
            analysis_result = output.get("analysis_result") or metadata.get("analysis_result")
            validation = metadata.get("validation_report") or {}
            attempts = metadata.get("execution_attempts", [])

            results.append({
                "id": case["id"],
                "category": case.get("category"),
                "difficulty": case.get("difficulty"),
                "datasets": case_dataset_names,
                "inspired_by": case.get("inspired_by", []),
                "question": case["question"],
                "expected_value": case["expected_value"],
                "observed_value": score["observed_value"],
                "absolute_error": score["absolute_error"],
                "passed": score["passed"],
                "reason": score["reason"],
                "latency_seconds": round(latency, 3),
                "sandbox_status": sandbox.get("status"),
                "repair_attempts": metadata.get("repair_attempts"),
                "repair_succeeded": any(
                    item.get("stage") == "repair" and item.get("validation_passed")
                    for item in attempts
                ),
                "execution_attempts": attempts,
                "structured_result": analysis_result,
                "structured_result_present": bool(analysis_result),
                "validation_passed": validation.get("passed"),
                "validation_confidence": validation.get("confidence"),
                "metric_ids": (metadata.get("plan") or {}).get("metric_ids", []),
                "planner": (metadata.get("planner") or {}).get("planner"),
            })
    finally:
        for dataset_name, file_id in uploaded_file_ids.items():
            try:
                _json_request(f"{api_base}/api/files/{file_id}", method="DELETE")
            except Exception as exc:
                print(f"Warning: failed to delete uploaded eval file {dataset_name}/{file_id}: {exc}")

    passed = sum(1 for item in results if item["passed"])
    total = len(results)
    execution_successes = sum(item["sandbox_status"] == "success" for item in results)
    structured_results = sum(item["structured_result_present"] for item in results)
    validated_results = sum(item["validation_passed"] is True for item in results)
    repaired_cases = [item for item in results if (item.get("repair_attempts") or 0) > 0]
    repaired_successes = sum(item["repair_succeeded"] for item in repaired_cases)

    return {
        "benchmark_name": config.get("benchmark_name", "datasays_eval"),
        "datasets": list(datasets.keys()),
        "total_cases": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / total if total else 0,
        "execution_success_rate": execution_successes / total if total else 0,
        "structured_result_rate": structured_results / total if total else 0,
        "validation_pass_rate": validated_results / total if total else 0,
        "repair_success_rate": (
            repaired_successes / len(repaired_cases) if repaired_cases else None
        ),
        "average_latency_seconds": (
            sum(item["latency_seconds"] for item in results) / total
            if total
            else 0
        ),
        "results": results
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DataSays benchmark cases.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--cases", default=str(Path(__file__).with_name("benchmark_cases.json")))
    args = parser.parse_args()

    summary = run_eval(args.api_base.rstrip("/"), Path(args.cases))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
