"""Generate a typed analysis plan grounded in profiles, metrics, and skills."""

import json
import re
from typing import Any, Dict, List, Optional

import httpx

from app.schemas.analysis import AnalysisPlan
from app.services.code_service import (
    OPENROUTER_BASE_URL,
    _format_openrouter_http_error,
    _get_model,
    _get_openrouter_api_key,
)


def _extract_json_object(content: str) -> Dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Planner response did not contain a JSON object")
    return json.loads(cleaned[start:end + 1])


def _fallback_plan(
    profiles: List[Dict[str, Any]],
    metric_matches: List[Dict[str, Any]],
    skills: List[Dict[str, Any]],
) -> AnalysisPlan:
    required_columns = []
    metric_ids = []
    assumptions = ["The planner used a deterministic fallback because structured planning was unavailable."]
    for match in metric_matches[:2]:
        metric_ids.append(match["id"])
        for bindings in match.get("field_bindings", {}).values():
            required_columns.extend(item["column"] for item in bindings)

    selected = skills[0]["id"] if skills else "aggregation_ranking"
    intent_map = {
        "data_quality": "data_quality",
        "aggregation_ranking": "aggregation",
        "time_series_cohort": "trend",
        "metric_diagnostics": "metric_diagnostic",
    }
    return AnalysisPlan(
        intent=intent_map.get(selected, "other"),
        metric_ids=metric_ids,
        required_columns=sorted(set(required_columns)),
        steps=[
            "Inspect the profiled schema and select the required fields.",
            "Apply the retrieved metric definition and selected analysis playbook.",
            "Execute the calculation in the sandbox and return a structured result.",
            "Validate the result against the plan and available evidence.",
        ],
        assumptions=assumptions,
    )


async def generate_analysis_plan(
    question: str,
    profiles: List[Dict[str, Any]],
    metric_matches: List[Dict[str, Any]],
    skills: List[Dict[str, Any]],
    model: Optional[str] = None,
) -> tuple[AnalysisPlan, Dict[str, Any]]:
    prompt = f"""Create a bounded data-analysis plan for the user's question.

USER QUESTION
{question}

DATASET PROFILES
{json.dumps(profiles, ensure_ascii=False, indent=2)}

RETRIEVED BUSINESS METRICS
{json.dumps(metric_matches, ensure_ascii=False, indent=2)}

SELECTED ANALYSIS PLAYBOOKS
{json.dumps(skills, ensure_ascii=False, indent=2)}

Rules:
- Use exact uploaded column names in required_columns whenever they can be identified.
- Use only retrieved metric IDs. Leave metric_ids empty if no metric definition applies.
- Do not invent unavailable fields, filters, dates, or business definitions.
- Set needs_clarification=true only when ambiguity or missing data would materially change the answer.
- Keep the plan concise and executable in pandas.
- Return JSON only.
"""
    messages = [
        {
            "role": "system",
            "content": (
                "You are the planning component of an evidence-first data analysis agent. "
                "Return a typed plan grounded only in the supplied dataset profiles and metric definitions."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    selected_model = _get_model(model)
    request_body: Dict[str, Any] = {
        "model": selected_model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 1400,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "analysis_plan",
                "strict": True,
                "schema": AnalysisPlan.model_json_schema(),
            },
        },
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {_get_openrouter_api_key()}",
                    "Content-Type": "application/json",
                },
                json=request_body,
            )
            if response.status_code == 400:
                request_body.pop("response_format", None)
                messages[-1]["content"] += "\nThe JSON must match this schema:\n" + json.dumps(
                    AnalysisPlan.model_json_schema(), ensure_ascii=False
                )
                response = await client.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {_get_openrouter_api_key()}",
                        "Content-Type": "application/json",
                    },
                    json=request_body,
                )
            response.raise_for_status()
            payload = response.json()

        content = payload["choices"][0]["message"]["content"] or ""
        plan = AnalysisPlan.model_validate(_extract_json_object(content))
        return plan, {
            "planner": "llm_structured_output",
            "model": selected_model,
            "usage": payload.get("usage", {}),
        }
    except httpx.HTTPStatusError as error:
        raise ValueError(_format_openrouter_http_error(error, selected_model)) from error
    except (json.JSONDecodeError, ValueError, KeyError) as error:
        return _fallback_plan(profiles, metric_matches, skills), {
            "planner": "deterministic_fallback",
            "model": selected_model,
            "warning": str(error),
        }
