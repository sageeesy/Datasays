#!/usr/bin/env python3
"""Run a small planner-only evaluation without code generation or scoring."""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from dotenv import load_dotenv


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))
load_dotenv(SERVER_DIR / ".env")

from app.services.metric_service import (  # noqa: E402
    compact_metric_match,
    retrieve_metric_definitions,
)
from app.services.plan_service import generate_analysis_plan  # noqa: E402
from app.services.profile_service import build_dataset_profile, compact_profile  # noqa: E402
from app.services.skill_service import compact_skill, select_analysis_skills  # noqa: E402


DEFAULT_CASE_IDS = [
    "executive_business_snapshot",
    "monthly_peak_diagnosis",
    "payment_structure_risk",
    "fact_table_join_audit",
    "review_grain_audit",
    "customer_identity_audit",
    "channel_quality_clarification",
    "profit_metric_clarification",
]


def _load_suite(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _select_cases(
    suite: Dict[str, Any],
    case_ids: Optional[Sequence[str]],
) -> List[Dict[str, Any]]:
    selected_ids = list(case_ids or DEFAULT_CASE_IDS)
    cases_by_id = {case["id"]: case for case in suite.get("cases", [])}
    missing = [case_id for case_id in selected_ids if case_id not in cases_by_id]
    if missing:
        raise ValueError(f"Unknown planner evaluation cases: {', '.join(missing)}")
    return [cases_by_id[case_id] for case_id in selected_ids]


async def run_planner_eval(
    cases_path: str | Path = SERVER_DIR / "evals" / "business_benchmark_cases.json",
    case_ids: Optional[Sequence[str]] = None,
    model: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluate only profile-to-plan behavior for a representative case subset."""
    suite_path = Path(cases_path).resolve()
    suite = _load_suite(suite_path)
    selected_cases = _select_cases(suite, case_ids)
    dataset_config = suite.get("datasets", {})
    profile_cache: Dict[str, Dict[str, Any]] = {}
    results: List[Dict[str, Any]] = []

    for case in selected_cases:
        profiles = []
        for dataset_id in case.get("datasets", []):
            if dataset_id not in profile_cache:
                config = dataset_config.get(dataset_id)
                if not config:
                    raise ValueError(f"Dataset '{dataset_id}' is not defined in the suite")
                dataset_path = (suite_path.parent / config["path"]).resolve()
                profile_cache[dataset_id] = compact_profile(
                    build_dataset_profile(dataset_path, dataset_path.name)
                )
            profiles.append(profile_cache[dataset_id])

        selected_skills = select_analysis_skills(case["question"])
        skills = [compact_skill(skill) for skill in selected_skills]
        metric_matches = [
            compact_metric_match(match)
            for match in retrieve_metric_definitions(
                case["question"],
                profiles,
                project_id=project_id,
            )
        ]

        started = time.perf_counter()
        plan, metadata = await generate_analysis_plan(
            question=case["question"],
            profiles=profiles,
            metric_matches=metric_matches,
            skills=skills,
            model=model,
        )
        completeness = metadata.get("completeness") or {}
        results.append({
            "case_id": case["id"],
            "question": case["question"],
            "datasets": list(case.get("datasets", [])),
            "selected_skill_ids": [skill["id"] for skill in skills],
            "retrieved_metric_ids": [match["id"] for match in metric_matches],
            "retrieved_metrics": metric_matches,
            "plan": plan.model_dump(mode="json"),
            "planner": metadata.get("planner"),
            "model": metadata.get("model"),
            "attempt_count": metadata.get("attempt_count"),
            "replanned": bool(metadata.get("replanned")),
            "attempts": metadata.get("attempts", []),
            "completeness": completeness,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        })

    return {
        "evaluation": "planner_only_v1_5",
        "benchmark": suite.get("benchmark_name"),
        "project_id": project_id,
        "case_count": len(results),
        "summary": {
            "ready_for_code_generation": sum(
                bool(item["completeness"].get("ready_for_code_generation"))
                for item in results
            ),
            "valid_clarifications": sum(
                bool(item["completeness"].get("valid_clarification"))
                for item in results
            ),
            "blocked_incomplete": sum(
                not item["completeness"].get("ready_for_code_generation")
                and not item["completeness"].get("valid_clarification")
                for item in results
            ),
            "replanned": sum(bool(item["replanned"]) for item in results),
        },
        "cases": results,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases",
        default=str(SERVER_DIR / "evals" / "business_benchmark_cases.json"),
        help="Path to the business benchmark JSON file.",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="Case ID to run. Repeat to select multiple cases.",
    )
    parser.add_argument("--model", help="Optional OpenRouter model override.")
    parser.add_argument("--project-id", help="Explicit project metric-knowledge scope.")
    parser.add_argument("--output", help="Optional path for the JSON report.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = asyncio.run(
        run_planner_eval(
            cases_path=args.cases,
            case_ids=args.case_ids,
            model=args.model,
            project_id=args.project_id,
        )
    )
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
        print(f"Planner evaluation written to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
