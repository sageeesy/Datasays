"""Generate a typed analysis plan grounded in profiles, metrics, and skills."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from pydantic import ValidationError

from app.schemas.analysis import (
    AnalysisPlan,
    PlanCompletenessIssue,
    PlanCompletenessReport,
)
from app.services.code_service import (
    OPENROUTER_BASE_URL,
    _format_openrouter_http_error,
    _get_model,
    _get_openrouter_api_key,
)


EXPLICIT_DIMENSIONS: Dict[str, Dict[str, List[str]]] = {
    "channel": {
        "question_terms": ["channel", "渠道", "获客来源", "utm_source"],
        "column_aliases": ["channel", "source", "utm_source", "acquisition_channel"],
    },
}

CONCEPT_LABELS = {
    "paid_amount": "支付或收入金额（paid_amount）",
    "item_revenue": "商品收入（item_revenue）",
    "cost_amount": "成本金额（cost_amount）",
    "refund_amount": "退款金额（refund_amount）",
    "customer_id": "客户标识（customer_id）",
    "payment_time": "支付时间（payment_time）",
}

METRIC_LABELS = {
    "ecommerce.gross_profit": "利润/毛利（Gross Profit）",
}

DIMENSION_LABELS = {
    "channel": "获客渠道（channel）",
}


def _normalize_name(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def _profile_columns(profiles: List[Dict[str, Any]]) -> set[str]:
    return {
        _normalize_name(str(column.get("name", "")))
        for profile in profiles
        for column in profile.get("columns", [])
    }


def _apply_planning_guards(
    plan: AnalysisPlan,
    question: str,
    profiles: List[Dict[str, Any]],
    metric_matches: List[Dict[str, Any]],
) -> tuple[AnalysisPlan, Dict[str, Any]]:
    """Force clarification when requested evidence cannot exist in the supplied schema."""
    blockers: List[str] = []
    for match in metric_matches:
        missing = match.get("missing_concepts") or []
        if missing and match.get("matched_terms"):
            metric_name = METRIC_LABELS.get(
                str(match.get("id")),
                str(match.get("name") or match.get("id")),
            )
            missing_names = "、".join(CONCEPT_LABELS.get(item, item) for item in missing)
            blockers.append(f"{metric_name}缺少必要字段：{missing_names}")

    normalized_question = _normalize_name(question)
    columns = _profile_columns(profiles)
    for name, definition in EXPLICIT_DIMENSIONS.items():
        requested = any(_normalize_name(term) in normalized_question for term in definition["question_terms"])
        available = any(_normalize_name(alias) in columns for alias in definition["column_aliases"])
        if requested and not available:
            blockers.append(f"缺少请求的分析维度：{DIMENSION_LABELS.get(name, name)}")

    if not blockers:
        return plan, {"applied": False, "blockers": []}

    plan.needs_clarification = True
    plan.clarification_question = (
        "当前数据缺少完成该分析所必需的字段或业务口径，无法直接计算（"
        + "；".join(blockers)
        + "）。请补充相应字段，或确认要改用哪个可计算的替代指标。"
    )
    plan.assumptions = [
        *plan.assumptions,
        "Planning stopped because required evidence was absent from the uploaded schema.",
    ]
    return plan, {"applied": True, "blockers": blockers}


def _extract_json_object(content: str) -> Dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Planner response did not contain a JSON object")
    return json.loads(cleaned[start:end + 1])


def _dataset_catalog(profiles: List[Dict[str, Any]]) -> Dict[str, set[str]]:
    catalog: Dict[str, set[str]] = {}
    for profile in profiles:
        file_name = str(profile.get("file_name") or "").strip()
        if not file_name:
            continue
        columns = {str(item.get("name")) for item in profile.get("columns", []) if item.get("name")}
        catalog[_normalize_name(Path(file_name).stem)] = columns
    return catalog


def _dataset_key(dataset: str) -> str:
    return _normalize_name(Path(str(dataset)).stem)


def _resolve_dataset(dataset: str, catalog: Dict[str, set[str]]) -> Optional[set[str]]:
    return catalog.get(_dataset_key(dataset))


def _column_reference_parts(reference: str) -> tuple[Optional[str], str]:
    value = str(reference).strip()
    if "." not in value:
        return None, value
    dataset, column = value.rsplit(".", 1)
    return dataset, column


def _column_exists(reference: str, catalog: Dict[str, set[str]]) -> bool:
    dataset, column = _column_reference_parts(reference)
    if dataset:
        columns = _resolve_dataset(dataset, catalog)
        return columns is not None and column in columns
    return any(column in columns for columns in catalog.values())


def _datasets_for_column(reference: str, catalog: Dict[str, set[str]]) -> set[str]:
    dataset, column = _column_reference_parts(reference)
    if dataset:
        normalized = _dataset_key(dataset)
        return {normalized} if normalized in catalog and column in catalog[normalized] else set()
    return {name for name, columns in catalog.items() if column in columns}


def _issue(code: str, field: str, message: str) -> PlanCompletenessIssue:
    return PlanCompletenessIssue(code=code, field=field, message=message)


def evaluate_plan_completeness(
    plan: AnalysisPlan,
    profiles: List[Dict[str, Any]],
    metric_matches: List[Dict[str, Any]],
) -> PlanCompletenessReport:
    """Check whether a schema-valid plan contains enough semantics to generate code."""
    if plan.needs_clarification:
        if plan.clarification_question and plan.clarification_question.strip():
            return PlanCompletenessReport(
                ready_for_code_generation=False,
                valid_clarification=True,
            )
        return PlanCompletenessReport(
            ready_for_code_generation=False,
            issues=[_issue(
                "missing_clarification_question",
                "clarification_question",
                "needs_clarification is true, but no concrete clarification question was provided.",
            )],
        )

    issues: List[PlanCompletenessIssue] = []
    catalog = _dataset_catalog(profiles)

    if not plan.analysis_scope or not plan.analysis_scope.strip():
        issues.append(_issue("missing_analysis_scope", "analysis_scope", "Describe the population included in the analysis."))
    if not plan.entity_grain or not plan.entity_grain.strip():
        issues.append(_issue("missing_entity_grain", "entity_grain", "Define what one analytical row or entity represents."))
    if not plan.required_columns:
        issues.append(_issue("missing_required_columns", "required_columns", "List the columns required to perform the analysis."))
    if not plan.steps:
        issues.append(_issue("missing_steps", "steps", "Provide ordered, natural-language calculation steps."))

    for reference in [*plan.required_columns, *plan.dimensions]:
        if not _column_exists(reference, catalog):
            issues.append(_issue(
                "unknown_column",
                "required_columns" if reference in plan.required_columns else "dimensions",
                f"Column reference '{reference}' is not present in the dataset profiles.",
            ))
    if plan.time_field and not _column_exists(plan.time_field, catalog):
        issues.append(_issue("unknown_time_field", "time_field", f"Time field '{plan.time_field}' is not present in the dataset profiles."))

    all_filters = list(plan.filters)
    for metric in plan.metrics:
        all_filters.extend(metric.filters)
        if metric.numerator:
            all_filters.extend(metric.numerator.filters)
        if metric.denominator:
            all_filters.extend(metric.denominator.filters)
    for item in all_filters:
        columns = _resolve_dataset(item.dataset, catalog)
        if columns is None:
            issues.append(_issue("unknown_filter_dataset", "filters", f"Filter dataset '{item.dataset}' is not present in the profiles."))
        elif item.column not in columns:
            issues.append(_issue("unknown_filter_column", "filters", f"Filter column '{item.dataset}.{item.column}' is not present in the profiles."))
        if item.operator not in {"is_null", "not_null"} and item.value is None:
            issues.append(_issue("missing_filter_value", "filters", f"Filter '{item.dataset}.{item.column}' requires a value."))

    metric_required_intents = {"aggregation", "ranking", "trend", "cohort", "metric_diagnostic"}
    if plan.intent in metric_required_intents and not plan.metrics:
        issues.append(_issue("missing_metrics", "metrics", f"Intent '{plan.intent}' requires at least one planned metric."))

    metric_keys = [metric.key for metric in plan.metrics]
    if len(metric_keys) != len(set(metric_keys)):
        issues.append(_issue("duplicate_metric_key", "metrics", "Each planned metric must have a unique key."))
    for metric in plan.metrics:
        if metric.metric_type in {"rate", "share", "ratio"}:
            if metric.numerator is None:
                issues.append(_issue("missing_numerator", f"metrics.{metric.key}.numerator", f"Metric '{metric.key}' requires a numerator."))
            if metric.denominator is None:
                issues.append(_issue("missing_denominator", f"metrics.{metric.key}.denominator", f"Metric '{metric.key}' requires a denominator."))

    selected_metric_ids = {metric.metric_id for metric in plan.metrics if metric.metric_id}
    if set(plan.metric_ids) != selected_metric_ids:
        issues.append(_issue(
            "metric_id_mismatch",
            "metric_ids",
            "metric_ids must equal the set of non-empty metrics[].metric_id values.",
        ))
    retrieved_ids = {str(match.get("id")) for match in metric_matches if match.get("id")}
    invalid_ids = sorted(selected_metric_ids - retrieved_ids)
    if invalid_ids:
        issues.append(_issue(
            "unretrieved_metric_id",
            "metrics.metric_id",
            f"Metric IDs were not retrieved for this question: {', '.join(invalid_ids)}.",
        ))
    rejected_metric_ids = {item.metric_id for item in plan.rejected_metrics}
    invalid_rejected_ids = sorted(rejected_metric_ids - retrieved_ids)
    if invalid_rejected_ids:
        issues.append(_issue(
            "unretrieved_rejected_metric",
            "rejected_metrics",
            f"Rejected metric IDs were not retrieved candidates: {', '.join(invalid_rejected_ids)}.",
        ))
    conflicting_ids = sorted(selected_metric_ids.intersection(rejected_metric_ids))
    if conflicting_ids:
        issues.append(_issue(
            "selected_rejected_metric_conflict",
            "rejected_metrics",
            f"Metrics cannot be both selected and rejected: {', '.join(conflicting_ids)}.",
        ))
    for rejection in plan.rejected_metrics:
        if rejection.superseded_by and rejection.superseded_by not in selected_metric_ids:
            issues.append(_issue(
                "invalid_metric_supersession",
                "rejected_metrics.superseded_by",
                f"Rejected metric '{rejection.metric_id}' is superseded by "
                f"'{rejection.superseded_by}', which is not a selected metric.",
            ))
    decision_required_ids = {
        str(match["id"])
        for match in metric_matches
        if match.get("id") and match.get("decision_required") is True
    }
    unresolved_ids = sorted(decision_required_ids - selected_metric_ids - rejected_metric_ids)
    if unresolved_ids:
        issues.append(_issue(
            "unresolved_metric_candidate",
            "metrics",
            "Decision-required metric candidates must be selected, rejected, or resolved "
            f"through clarification: {', '.join(unresolved_ids)}.",
        ))

    if plan.intent in {"trend", "cohort"}:
        if not plan.time_field:
            issues.append(_issue("missing_time_field", "time_field", f"Intent '{plan.intent}' requires a time field."))
        if not plan.time_grain:
            issues.append(_issue("missing_time_grain", "time_grain", f"Intent '{plan.intent}' requires a time grain."))
    elif bool(plan.time_field) != bool(plan.time_grain):
        issues.append(_issue("incomplete_time_spec", "time_field", "time_field and time_grain must be provided together."))

    used_datasets: set[str] = set()
    for reference in [*plan.required_columns, *plan.dimensions, *([plan.time_field] if plan.time_field else [])]:
        used_datasets.update(_datasets_for_column(reference, catalog))
    for item in all_filters:
        normalized = _dataset_key(item.dataset)
        if normalized in catalog:
            used_datasets.add(normalized)

    join_edges: set[frozenset[str]] = set()
    for join in plan.joins:
        left = _dataset_key(join.left_dataset)
        right = _dataset_key(join.right_dataset)
        left_columns = _resolve_dataset(join.left_dataset, catalog)
        right_columns = _resolve_dataset(join.right_dataset, catalog)
        if left_columns is None or right_columns is None:
            issues.append(_issue("unknown_join_dataset", "joins", f"Join datasets '{join.left_dataset}' and '{join.right_dataset}' must exist in the profiles."))
        else:
            missing_keys = [key for key in join.join_keys if key not in left_columns or key not in right_columns]
            if missing_keys:
                issues.append(_issue("unknown_join_key", "joins.join_keys", f"Join keys are not present on both sides: {', '.join(missing_keys)}."))
        join_edges.add(frozenset({left, right}))
        if join.relationship == "many_to_many" and not (join.pre_join_aggregation or "").strip():
            issues.append(_issue(
                "missing_pre_join_aggregation",
                "joins.pre_join_aggregation",
                "A many-to-many join must state the pre-join aggregation or explicitly describe its audit-only handling.",
            ))

    if len(used_datasets) > 1:
        connected = set()
        if used_datasets:
            connected.add(next(iter(used_datasets)))
            changed = True
            while changed:
                changed = False
                for edge in join_edges:
                    if connected.intersection(edge) and not edge.issubset(connected):
                        connected.update(edge)
                        changed = True
        if not used_datasets.issubset(connected):
            issues.append(_issue(
                "missing_join_requirement",
                "joins",
                "The plan uses multiple datasets but does not provide join requirements that connect them.",
            ))

    return PlanCompletenessReport(
        ready_for_code_generation=not issues,
        valid_clarification=False,
        issues=issues,
    )


def _fallback_plan(
    profiles: List[Dict[str, Any]],
    metric_matches: List[Dict[str, Any]],
    skills: List[Dict[str, Any]],
) -> AnalysisPlan:
    required_columns = []
    assumptions = ["The planner used a deterministic fallback because structured planning was unavailable."]
    for match in metric_matches[:2]:
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
        intent=intent_map.get(selected, "filtering"),
        required_columns=sorted(set(required_columns)),
        steps=[
            "Inspect the profiled schema and select the required fields.",
            "Apply the retrieved metric definition and selected analysis playbook.",
            "Execute the calculation in the sandbox and return a structured result.",
            "Validate the result against the plan and available evidence.",
        ],
        assumptions=assumptions,
    )


def _build_planner_prompt(
    question: str,
    profiles: List[Dict[str, Any]],
    metric_matches: List[Dict[str, Any]],
    skills: List[Dict[str, Any]],
    conversation_context: Optional[Dict[str, Any]],
    retry_feedback: Optional[Dict[str, Any]] = None,
) -> str:
    feedback_section = ""
    if retry_feedback:
        feedback_section = (
            "\nPREVIOUS PLAN VALIDATION FEEDBACK\n"
            + json.dumps(retry_feedback, ensure_ascii=False, indent=2)
            + "\nCorrect every listed issue using information already present above. "
            "Do not ask the user merely because the previous plan omitted known information.\n"
        )

    return f"""Create an AnalysisPlan V1.5 for the user's data-analysis question.

USER QUESTION
{question}

DATASET PROFILES
{json.dumps(profiles, ensure_ascii=False, indent=2)}

RETRIEVED BUSINESS METRICS
{json.dumps(metric_matches, ensure_ascii=False, indent=2)}

SELECTED ANALYSIS PLAYBOOKS
{json.dumps(skills, ensure_ascii=False, indent=2)}

PRIOR CONVERSATION CONTEXT
{json.dumps(conversation_context or {}, ensure_ascii=False, indent=2)}
{feedback_section}
UNIVERSAL PLANNING SEMANTICS
- U1 Broadest Base Population: analysis_scope must describe the broadest shared base population required to compute every planned metric. Never replace it with the narrower subset used by only one metric.
- U2 Filter Locality: put a filter in top-level filters only when it applies to every planned metric. Put metric-specific, numerator-specific, and denominator-specific filters on the corresponding metric or operand.
- U3 Explicit Metric Populations: define the calculation population for every metric. For each rate, share, or ratio, separately state the numerator and denominator entities, filters, and aggregation.
- U4 Denominator Preservation: when a denominator population is broader than another metric's population, preserve or calculate that baseline before any restrictive filter or join.
- U5 Population-Safe Join: consider whether each join deletes entities or multiplies rows. Do not use an inner join before computing a denominator that must retain all left-side entities, unless the metric definition explicitly limits the denominator to matched entities.
- U6 Business-Event Time: select time_field from the business event requested by the user, such as purchase, payment, or delivery. Do not select a date merely because it exists or is more complete.
- U7 Overall/Trend Consistency: overall metrics and their time trends must use the same metric definitions, populations, and filters. A trend adds only the time grouping.

Rules:
- intent is required. Choose the closest supported intent; there is no generic 'other' escape hatch.
- For an executable plan, analysis_scope must define the included population and entity_grain must define one analytical row/entity.
- Use exact dataset file names from the profiles in filters and joins. Keep required_columns, dimensions, and time_field as exact raw CSV column names for compatibility with downstream validation; use JoinSpec to disambiguate shared names.
- filters must be structured objects with dataset, column, operator, and value. Never hide material scope filters only in assumptions or steps.
- For aggregation, ranking, trend, cohort, or metric-diagnostic work, list every requested output in metrics.
- A rate, share, or ratio metric must explicitly describe its numerator and denominator, including their different filters or grains.
- value_scale is raw for counts/currency, fraction for values such as 0.25, and percent only when the stored value itself is 25 rather than 0.25.
- metric_ids must exactly equal all non-null metrics[].metric_id values. A non-null metric_id must come from RETRIEVED BUSINESS METRICS.
- RETRIEVED BUSINESS METRICS are candidates, not automatically mandatory outputs. Only candidates with decision_required=true require an explicit decision.
- For every decision_required=true candidate, either select it through metrics[].metric_id and metric_ids, reject it in rejected_metrics with a concise reason, or request clarification when the business meaning is genuinely unresolved.
- Candidates with decision_required=false, including token-overlap and shadowed candidates, do not require rejection and may be omitted without explanation.
- A rejected metric_id must come from RETRIEVED BUSINESS METRICS, cannot also be selected, and superseded_by may only reference a selected metric_id.
- A trend or cohort plan must include both time_field and time_grain.
- If columns from multiple datasets are used, add joins. State both source grains, relationship, keys, and how.
- For a many-to-many join, pre_join_aggregation must explain the safe aggregation requirement. If a direct many-to-many join is intentionally measured for an audit, explicitly state that it is audit-only and how independent baseline totals are preserved.
- steps are concise, ordered natural-language calculations, not executable code.
- Set needs_clarification=true only when missing business information, missing fields, an unknown entity definition, or a material ambiguity cannot be resolved from the supplied evidence.
- Planner omissions are not user ambiguities: fill them from the supplied profiles, metrics, and skills.
- Do not invent unavailable columns, filters, dates, metric definitions, or prior findings.
- intent must be one of: lookup, filtering, aggregation, ranking, trend, cohort, data_quality, metric_diagnostic, modeling.
- analysis_scope and entity_grain must each be a string, never an object.
- metric_type must be one of: count, sum, average, rate, share, ratio, difference, other.
- value_scale must be one of: raw, fraction, percent.
- Put count_distinct in calculation or MetricOperand.aggregation; count_distinct is not a metric_type.
- Every join must use left_dataset, right_dataset, join_keys, how, left_grain, right_grain, and relationship.
- Top-level aggregation is a V1.5 legacy compatibility field and must be null. Never put group_by, metrics, or other structured calculation information in aggregation. Put grouping in dimensions, time_field, and time_grain; put metric calculations in metrics.
- dimensions may contain only non-time grouping columns that exist in the dataset profiles. Express time grouping only with time_field and time_grain; never put derived time buckets such as month, month_of_year, quarter, year, year_month, or order_month in dimensions. For a combined grouping such as state by month, put the real business column such as customer_state in dimensions and keep the monthly grouping in time_field and time_grain.
- Return JSON only and match the supplied schema exactly.

STRICT V1.5 FIELD-SHAPE SKELETON
Use this only as a structural template. Replace generic placeholders with supplied evidence, and use empty lists or null for optional structures that do not apply.
{{
  "intent": "aggregation",
  "analysis_scope": "Describe the included analysis population.",
  "entity_grain": "Describe what one analytical entity represents.",
  "metric_ids": [],
  "rejected_metrics": [],
  "metrics": [
    {{
      "key": "sample_metric",
      "label": "Sample metric",
      "metric_id": null,
      "metric_type": "ratio",
      "definition": "Describe the metric's business meaning.",
      "calculation": "Describe how the numerator and denominator form the metric.",
      "numerator": {{
        "description": "Describe the numerator population.",
        "aggregation": "count_distinct(entity_id)",
        "filters": []
      }},
      "denominator": {{
        "description": "Describe the denominator population.",
        "aggregation": "count_distinct(entity_id)",
        "filters": []
      }},
      "filters": [],
      "value_scale": "fraction"
    }}
  ],
  "required_columns": ["exact_column_name"],
  "dimensions": [],
  "filters": [
    {{
      "dataset": "exact_file_name.csv",
      "column": "exact_column_name",
      "operator": "eq",
      "value": "required_value"
    }}
  ],
  "aggregation": null,
  "time_field": "exact_time_column",
  "time_grain": "month",
  "joins": [
    {{
      "left_dataset": "left_file.csv",
      "right_dataset": "right_file.csv",
      "join_keys": ["shared_key"],
      "how": "left",
      "left_grain": "Describe the left-side grain.",
      "right_grain": "Describe the right-side grain.",
      "relationship": "one_to_many",
      "pre_join_aggregation": null
    }}
  ],
  "steps": ["Describe the first ordered calculation step."],
  "assumptions": [],
  "needs_clarification": false,
  "clarification_question": null
}}
"""


async def _request_planner_payload(
    client: httpx.AsyncClient,
    selected_model: str,
    prompt: str,
) -> Dict[str, Any]:
    messages = [
        {
            "role": "system",
            "content": (
                "You are the planning component of an evidence-first data analysis agent. "
                "Produce a complete business-semantics contract, not code and not an answer."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    request_body: Dict[str, Any] = {
        "model": selected_model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 3500,
        "reasoning": {"effort": "none", "exclude": True},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "analysis_plan_v1_5",
                "strict": True,
                "schema": AnalysisPlan.model_json_schema(),
            },
        },
    }
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
    return response.json()


async def generate_analysis_plan(
    question: str,
    profiles: List[Dict[str, Any]],
    metric_matches: List[Dict[str, Any]],
    skills: List[Dict[str, Any]],
    model: Optional[str] = None,
    conversation_context: Optional[Dict[str, Any]] = None,
) -> tuple[AnalysisPlan, Dict[str, Any]]:
    selected_model = _get_model(model)
    attempts: List[Dict[str, Any]] = []
    retry_feedback: Optional[Dict[str, Any]] = None
    last_plan: Optional[AnalysisPlan] = None
    last_report: Optional[PlanCompletenessReport] = None
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            for attempt_number in range(1, 3):
                prompt = _build_planner_prompt(
                    question,
                    profiles,
                    metric_matches,
                    skills,
                    conversation_context,
                    retry_feedback,
                )
                payload = await _request_planner_payload(client, selected_model, prompt)
                content = payload["choices"][0]["message"]["content"] or ""
                try:
                    plan = AnalysisPlan.model_validate(_extract_json_object(content))
                except (json.JSONDecodeError, ValidationError, ValueError, KeyError) as error:
                    attempts.append({
                        "attempt": attempt_number,
                        "schema_valid": False,
                        "ready_for_code_generation": False,
                        "error": str(error),
                        "usage": payload.get("usage", {}),
                    })
                    retry_feedback = {
                        "schema_valid": False,
                        "errors": [str(error)],
                    }
                    continue

                plan, guard = _apply_planning_guards(plan, question, profiles, metric_matches)
                report = evaluate_plan_completeness(plan, profiles, metric_matches)
                last_plan = plan
                last_report = report
                attempts.append({
                    "attempt": attempt_number,
                    "schema_valid": True,
                    "ready_for_code_generation": report.ready_for_code_generation,
                    "valid_clarification": report.valid_clarification,
                    "issues": [item.model_dump(mode="json") for item in report.issues],
                    "usage": payload.get("usage", {}),
                    "deterministic_guard": guard,
                })
                if report.ready_for_code_generation or report.valid_clarification:
                    return plan, {
                        "planner": "llm_structured_output",
                        "model": selected_model,
                        "attempt_count": attempt_number,
                        "replanned": attempt_number > 1,
                        "attempts": attempts,
                        "deterministic_guard": guard,
                        "completeness": report.model_dump(mode="json"),
                    }
                retry_feedback = report.model_dump(mode="json")

        if last_plan is None:
            last_plan, guard = _apply_planning_guards(
                _fallback_plan(profiles, metric_matches, skills),
                question,
                profiles,
                metric_matches,
            )
            last_report = evaluate_plan_completeness(last_plan, profiles, metric_matches)
            planner_name = "deterministic_incomplete_fallback"
        else:
            guard = attempts[-1].get("deterministic_guard", {"applied": False, "blockers": []})
            planner_name = "llm_structured_output_incomplete"
        return last_plan, {
            "planner": planner_name,
            "model": selected_model,
            "attempt_count": 2,
            "replanned": True,
            "attempts": attempts,
            "deterministic_guard": guard,
            "completeness": last_report.model_dump(mode="json") if last_report else None,
        }
    except httpx.HTTPStatusError as error:
        raise ValueError(_format_openrouter_http_error(error, selected_model)) from error
