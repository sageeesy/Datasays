#!/usr/bin/env python3
"""
Lightweight benchmark runner for DataSays.

The runner uploads a CSV file, executes benchmark questions through the
FastAPI /api/query endpoint, and scores numeric answers against expected
values with tolerance.
"""

import argparse
import asyncio
import json
import mimetypes
import re
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib import request, error


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


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


async def _in_process_query(app: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://datasays.local",
        timeout=600,
    ) as client:
        response = await client.post("/api/query", json=payload)
    if response.status_code >= 400:
        raise RuntimeError(
            f"In-process HTTP {response.status_code} for POST /api/query: {response.text}"
        )
    return response.json()


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
        with request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Upload failed with HTTP {exc.code}: {body_text}") from exc

    return data["file"]["id"]


async def _stage_file_locally(file_path: Path) -> str:
    """Register a fixture directly in the local upload store without HTTP transfer."""
    from app.services.file_service import UPLOAD_DIR, extract_metadata, save_metadata

    temp_name = f"temp_{uuid.uuid4().hex}{file_path.suffix}"
    temp_path = UPLOAD_DIR / temp_name
    shutil.copy2(file_path, temp_path)
    try:
        metadata = await extract_metadata(str(temp_path), file_path.name, temp_name)
        final_path = UPLOAD_DIR / f"{metadata['id']}{file_path.suffix}"
        temp_path.rename(final_path)
        metadata["filePath"] = str(final_path)
        metadata["fileName"] = final_path.name
        await save_metadata(metadata)
        return metadata["id"]
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


async def _delete_local_file(file_id: str) -> None:
    from app.services.file_service import delete_file

    await delete_file(file_id)


def _numeric_candidates(response: Dict[str, Any], allow_legacy_text: bool = False) -> List[float]:
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

    if not allow_legacy_text:
        return []

    # Opt-in compatibility fallback for responses produced by the pre-P0 API.
    candidates: List[float] = []
    content = sandbox.get("content", "")
    for match in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", content):
        candidates.append(float(match))

    return candidates


def _score_case(
    response: Dict[str, Any],
    case: Dict[str, Any],
    default_tolerance: float,
    allow_legacy_text: bool,
) -> Dict[str, Any]:
    expected = float(case["expected_value"])
    tolerance = float(case.get("tolerance", default_tolerance))
    candidates = _numeric_candidates(response, allow_legacy_text)

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

    relative_error = absolute_error / abs(expected) if expected else absolute_error
    return {
        "passed": absolute_error <= tolerance,
        "observed_value": observed,
        "absolute_error": absolute_error,
        "relative_error": relative_error,
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


def _expectation_passed(expected: Sequence[str], observed: Sequence[str]) -> Optional[bool]:
    if not expected:
        return None
    return set(expected).issubset(set(observed))


def _category_summary(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    summaries: Dict[str, Dict[str, Any]] = {}
    for item in results:
        category = item.get("category") or "uncategorized"
        summary = summaries.setdefault(category, {"total": 0, "passed": 0})
        summary["total"] += 1
        summary["passed"] += int(item["passed"])
    for summary in summaries.values():
        summary["pass_rate"] = summary["passed"] / summary["total"]
    return summaries


async def run_eval(
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
    prompt_style = defaults.get("prompt_style", "zero")
    model = model_override or defaults.get("model")
    tolerance = float(defaults.get("tolerance", 0.001))
    allow_legacy_text = bool(defaults.get("allow_legacy_text_scoring", False))

    cases = config["cases"]
    if case_ids:
        requested = set(case_ids)
        available = {case["id"] for case in cases}
        missing = sorted(requested - available)
        if missing:
            raise ValueError(f"Unknown benchmark case IDs: {', '.join(missing)}")
        cases = [case for case in cases if case["id"] in requested]

    required_dataset_names = {
        dataset_name
        for case in cases
        for dataset_name in case.get("datasets", [])
    }
    if required_dataset_names:
        datasets = {
            name: dataset
            for name, dataset in datasets.items()
            if name in required_dataset_names
        }

    uploaded_file_ids: Dict[str, str] = {}
    results = []
    asgi_app = None

    if in_process_api:
        local_files = True
        from main import app

        asgi_app = app

    try:
        for dataset_name, dataset_config in datasets.items():
            dataset_path = cases_path.parent / dataset_config["path"]
            uploaded_file_ids[dataset_name] = (
                await _stage_file_locally(dataset_path)
                if local_files
                else await asyncio.to_thread(_upload_file, api_base, dataset_path)
            )

        for case in cases:
            case_dataset_names = case.get("datasets")
            if not case_dataset_names:
                case_dataset_names = [next(iter(uploaded_file_ids.keys()))]

            file_ids = [
                uploaded_file_ids[dataset_name]
                for dataset_name in case_dataset_names
            ]

            started = time.perf_counter()
            query_payload = {
                "question": case["question"],
                "fileIds": file_ids,
                "prompt_style": case.get("prompt_style", prompt_style),
                "model": case.get("model", model),
            }
            response = (
                await _in_process_query(asgi_app, query_payload)
                if asgi_app is not None
                else await asyncio.to_thread(
                    _json_request,
                    f"{api_base}/api/query",
                    "POST",
                    query_payload,
                )
            )
            latency = time.perf_counter() - started
            score = _score_case(response, case, tolerance, allow_legacy_text)
            sandbox = response.get("sandboxResponse", {})
            metadata = sandbox.get("metadata") or {}
            output = sandbox.get("output") or {}
            analysis_result = output.get("analysis_result") or metadata.get("analysis_result")
            validation = metadata.get("validation_report") or {}
            attempts = metadata.get("execution_attempts", [])
            plan = metadata.get("plan") or {}
            metric_ids = plan.get("metric_ids", [])
            visualization_types = [
                item.get("type")
                for item in (analysis_result or {}).get("visualizations", [])
                if item.get("type")
            ]
            expected_metric_ids = case.get("expected_metric_ids", [])
            expected_visualization_types = case.get("expected_visualization_types", [])

            results.append({
                "id": case["id"],
                "category": case.get("category"),
                "difficulty": case.get("difficulty"),
                "language": case.get("language"),
                "datasets": case_dataset_names,
                "question": case["question"],
                "metric_definition": case.get("metric_definition"),
                "failure_mode": case.get("failure_mode"),
                "expected_value": case["expected_value"],
                "observed_value": score["observed_value"],
                "absolute_error": score["absolute_error"],
                "relative_error": score.get("relative_error"),
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
                "metric_ids": metric_ids,
                "expected_metric_ids": expected_metric_ids,
                "metric_expectation_passed": _expectation_passed(expected_metric_ids, metric_ids),
                "visualization_types": visualization_types,
                "expected_visualization_types": expected_visualization_types,
                "visualization_expectation_passed": _expectation_passed(
                    expected_visualization_types,
                    visualization_types,
                ),
                "planner": (metadata.get("planner") or {}).get("planner"),
            })
    finally:
        for dataset_name, file_id in uploaded_file_ids.items():
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
                print(f"Warning: failed to delete uploaded eval file {dataset_name}/{file_id}: {exc}")

    passed = sum(1 for item in results if item["passed"])
    total = len(results)
    execution_successes = sum(item["sandbox_status"] == "success" for item in results)
    structured_results = sum(item["structured_result_present"] for item in results)
    validated_results = sum(item["validation_passed"] is True for item in results)
    repaired_cases = [item for item in results if (item.get("repair_attempts") or 0) > 0]
    repaired_successes = sum(item["repair_succeeded"] for item in repaired_cases)
    metric_cases = [item for item in results if item["expected_metric_ids"]]
    visualization_cases = [item for item in results if item["expected_visualization_types"]]

    return {
        "benchmark_name": config.get("benchmark_name", "datasays_eval"),
        "benchmark_version": config.get("version"),
        "model": model,
        "file_transport": "local_store" if local_files else "http_upload",
        "api_transport": "in_process_asgi" if in_process_api else "http",
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
        "metric_expectation_rate": (
            sum(item["metric_expectation_passed"] is True for item in metric_cases) / len(metric_cases)
            if metric_cases else None
        ),
        "visualization_expectation_rate": (
            sum(item["visualization_expectation_passed"] is True for item in visualization_cases)
            / len(visualization_cases)
            if visualization_cases else None
        ),
        "average_latency_seconds": (
            sum(item["latency_seconds"] for item in results) / total
            if total
            else 0
        ),
        "category_summary": _category_summary(results),
        "results": results
    }


async def _run_cli(args: argparse.Namespace) -> int:
    summary = await run_eval(
        args.api_base.rstrip("/"),
        Path(args.cases),
        args.case_ids,
        model_override=args.model,
        local_files=args.local_files,
        in_process_api=args.in_process_api,
    )
    rendered = json.dumps(summary, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    display = (
        {key: value for key, value in summary.items() if key != "results"}
        if args.summary_only
        else summary
    )
    print(json.dumps(display, indent=2, ensure_ascii=False))
    return 0 if summary["failed"] == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DataSays benchmark cases.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--cases", default=str(Path(__file__).with_name("benchmark_cases.json")))
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="Run only the specified case ID. Repeat this option for multiple cases.",
    )
    parser.add_argument(
        "--model",
        help="Explicit OpenRouter model ID. Recommended for reproducible baselines.",
    )
    parser.add_argument(
        "--local-files",
        action="store_true",
        help="Stage fixtures in the local upload store instead of sending multipart HTTP uploads.",
    )
    parser.add_argument(
        "--in-process-api",
        action="store_true",
        help="Call the real FastAPI route through in-process ASGI instead of localhost TCP.",
    )
    parser.add_argument("--output", type=Path, help="Optional path for the JSON result report.")
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print aggregate metrics only while still saving full results with --output.",
    )
    args = parser.parse_args()

    return asyncio.run(_run_cli(args))


if __name__ == "__main__":
    raise SystemExit(main())
