"""Local business-metric semantic layer and deterministic retrieval."""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.schemas.analysis import MetricDefinition, MetricMatch


KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"
PROJECT_OVERRIDES_DIR = KNOWLEDGE_DIR / "project_overrides"

CONCEPT_ALIASES: Dict[str, List[str]] = {
    "order_id": ["order_id", "orderid", "transaction_id", "transactionid", "订单id", "订单号", "交易号"],
    "order_status": ["order_status", "status", "订单状态"],
    "customer_id": ["customer_id", "customerid", "customer_unique_id", "user_id", "userid", "buyer_id", "account_id", "用户id", "客户id", "买家id"],
    "account_id": ["account_id", "accountid", "customer_id", "customerid", "company_id", "workspace_id", "账户id", "客户id"],
    "subscription_id": ["subscription_id", "subscriptionid", "订阅id"],
    "order_amount": ["order_amount", "amount", "sales", "gmv", "revenue", "total_amount", "payment_value", "订单金额", "成交金额", "销售额"],
    "item_revenue": ["item_revenue", "item_price", "price", "product_revenue", "商品收入", "商品售价", "售价"],
    "paid_amount": ["paid_amount", "payment_amount", "payment_value", "net_sales", "revenue", "sales", "实付金额", "支付金额", "净销售额"],
    "payment_type": ["payment_type", "payment_method", "payment_channel", "支付方式", "支付渠道"],
    "payment_sequence": ["payment_sequence", "payment_sequential", "payment_count", "支付序号", "支付次数"],
    "refund_amount": ["refund_amount", "refunded_amount", "return_amount", "退款金额", "退货金额"],
    "cost_amount": ["cost_amount", "cost", "cogs", "unit_cost", "purchase_cost", "商品成本", "销售成本", "进货成本", "成本"],
    "order_time": ["order_time", "order_date", "order_purchase_timestamp", "created_at", "date", "订单时间", "下单时间", "日期"],
    "payment_time": ["payment_time", "paid_at", "purchase_time", "purchase_date", "order_purchase_timestamp", "date", "支付时间", "购买时间", "日期"],
    "event_time": ["event_time", "timestamp", "occurred_at", "date", "事件时间", "时间", "日期"],
    "channel": ["channel", "source", "utm_source", "acquisition_channel", "渠道", "来源"],
    "acquisition_channel": ["acquisition_channel", "channel", "source", "utm_source", "获客渠道", "渠道"],
    "region": ["region", "country", "city", "market", "customer_state", "seller_state", "地区", "区域", "国家", "城市"],
    "product_category": ["product_category", "product_category_name", "product_category_name_english", "category", "product", "商品类目", "品类", "产品"],
    "purchase_flag": ["purchase_flag", "is_purchase", "purchased", "converted", "是否购买", "购买标记"],
    "eligible_user_flag": ["eligible_user", "visitor", "session_id", "eligible", "访问用户", "会话id"],
    "recurring_amount": ["mrr", "recurring_amount", "subscription_amount", "monthly_amount", "月费", "订阅金额"],
    "billing_interval": ["billing_interval", "billing_period", "interval", "计费周期"],
    "subscription_status": ["subscription_status", "status", "customer_status", "订阅状态", "客户状态"],
    "subscription_time": ["subscription_time", "started_at", "ended_at", "date", "订阅时间", "日期"],
    "mrr_movement": ["mrr_movement", "mrr_change", "movement_amount", "MRR变动", "MRR变化"],
    "movement_type": ["movement_type", "change_type", "event_type", "变动类型", "事件类型"],
    "movement_time": ["movement_time", "changed_at", "event_time", "date", "变动时间", "日期"],
    "signup_time": ["signup_time", "signed_up_at", "created_at", "注册时间"],
    "activation_flag": ["activation_flag", "is_activated", "activated", "激活标记", "是否激活"],
    "activation_time": ["activation_time", "activated_at", "激活时间"],
}


def _normalize(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", value.lower()))


def _matches_direct_term(question: str, candidate: str) -> bool:
    """Match explicit metric terms without manufacturing cross-word acronyms."""
    if not candidate.strip():
        return False
    if re.search(r"[\u4e00-\u9fff]", candidate):
        normalized_candidate = _normalize(candidate)
        return bool(normalized_candidate and normalized_candidate in _normalize(question))

    words = re.findall(r"[a-z0-9]+", candidate.lower())
    if not words:
        return False
    phrase = r"[\W_]+".join(re.escape(word) for word in words)
    return re.search(rf"(?<![a-z0-9]){phrase}(?![a-z0-9])", question.lower()) is not None


def _direct_match_terms(question: str, metric: MetricDefinition) -> List[str]:
    return sorted({
        candidate
        for candidate in [metric.name, metric.id, *metric.aliases]
        if _matches_direct_term(question, candidate)
    })


def _find_nested_alias_shadow(
    metric_id: str,
    matched_terms: List[str],
    direct_terms_by_metric: Dict[str, List[str]],
) -> Optional[str]:
    """Return a more specific directly matched metric for an obvious nested phrase."""
    if not matched_terms:
        return None
    current_term = max((_normalize(term) for term in matched_terms), key=len)
    shadows: List[tuple[int, str]] = []
    for other_id, other_terms in direct_terms_by_metric.items():
        if other_id == metric_id:
            continue
        for other_term in other_terms:
            normalized_other = _normalize(other_term)
            if current_term and current_term != normalized_other and current_term in normalized_other:
                shadows.append((len(normalized_other), other_id))
    return max(shadows)[1] if shadows else None


@lru_cache(maxsize=1)
def load_metric_definitions() -> List[MetricDefinition]:
    records: List[Dict[str, Any]] = []
    for filename in ("ecommerce_metrics.json", "saas_metrics.json"):
        records.extend(json.loads((KNOWLEDGE_DIR / filename).read_text(encoding="utf-8")))
    return [MetricDefinition.model_validate(record) for record in records]


@lru_cache(maxsize=8)
def load_project_override(project_id: str) -> Dict[str, Any]:
    """Load an explicitly selected project knowledge overlay."""
    if not re.fullmatch(r"[a-z0-9_-]+", project_id):
        raise ValueError(f"Invalid project_id: {project_id}")
    path = PROJECT_OVERRIDES_DIR / f"{project_id}.json"
    if not path.exists():
        raise ValueError(f"Unknown metric knowledge project_id: {project_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("project_id") != project_id:
        raise ValueError(f"Project override ID mismatch in {path.name}")
    return payload


def _all_profile_columns(profiles: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
    columns = []
    for profile in profiles:
        file_name = str(profile.get("file_name", "dataset"))
        for item in profile.get("columns", []):
            columns.append({"file_name": file_name, "column": str(item.get("name", ""))})
    return columns


def _bind_concept(
    concept: str,
    available: List[Dict[str, str]],
    project_override: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    project_aliases = (project_override or {}).get("concept_bindings", {}).get(concept, [])
    normalized_project_aliases = {_normalize(alias) for alias in project_aliases}
    project_matches = [
        {**item, "binding_source": "project_override"}
        for item in available
        if _normalize(item["column"]) in normalized_project_aliases
    ]
    if project_matches:
        return project_matches

    aliases = {_normalize(alias) for alias in CONCEPT_ALIASES.get(concept, [concept])}
    return [
        {**item, "binding_source": "domain_alias"}
        for item in available
        if _normalize(item["column"]) in aliases
    ]


def bind_metric_fields(
    metric: MetricDefinition,
    profiles: List[Dict[str, Any]],
    project_override: Optional[Dict[str, Any]] = None,
    time_concept: Optional[str] = None,
) -> tuple[Dict[str, List[Dict[str, str]]], List[str], List[Dict[str, str]]]:
    available = _all_profile_columns(profiles)
    bindings: Dict[str, List[Dict[str, str]]] = {}
    missing = []

    for concept in metric.required_concepts:
        matches = _bind_concept(concept, available, project_override)
        if matches:
            bindings[concept] = matches
        else:
            missing.append(concept)

    effective_time_concept = time_concept or metric.time_concept
    time_field_candidates: List[Dict[str, str]] = []
    if effective_time_concept:
        time_field_candidates = _bind_concept(
            effective_time_concept,
            available,
            project_override,
        )
        bindings.setdefault(effective_time_concept, time_field_candidates)
    return bindings, missing, time_field_candidates


def _metric_knowledge_context(
    metric: MetricDefinition,
    project_override: Optional[Dict[str, Any]],
    canonical_metric_mapping: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    metric_override = (project_override or {}).get("metric_overrides", {}).get(metric.id, {})
    effective = {
        "time_concept": metric_override.get("time_concept", metric.time_concept),
        "default_population": metric_override.get("default_population", metric.default_population),
        "denominator_policy": metric_override.get("denominator_policy", metric.denominator_policy),
    }
    return {
        "precedence": "user_explicit > project_override > domain_default > clarification",
        "project_id": (project_override or {}).get("project_id"),
        "project_policies": (project_override or {}).get("policies", {}),
        "applied_metric_override": metric_override,
        "canonical_metric_mapping": canonical_metric_mapping,
        "effective": effective,
    }


def retrieve_metric_definitions(
    question: str,
    profiles: List[Dict[str, Any]],
    limit: int = 4,
    project_id: Optional[str] = None,
) -> List[MetricMatch]:
    question_tokens = _tokens(question)
    matches: List[MetricMatch] = []
    project_override = load_project_override(project_id) if project_id else None
    definitions = load_metric_definitions()
    direct_terms_by_metric = {
        metric.id: _direct_match_terms(question, metric)
        for metric in definitions
    }
    definition_ids = {metric.id for metric in definitions}
    configured_canonical_mappings = (project_override or {}).get(
        "canonical_metric_mappings",
        {},
    )
    active_canonical_mappings = {
        source_id: target_id
        for source_id, target_id in configured_canonical_mappings.items()
        if source_id in definition_ids
        and target_id in definition_ids
        and direct_terms_by_metric.get(source_id)
    }
    canonical_sources_by_target = {
        target_id: source_id
        for source_id, target_id in active_canonical_mappings.items()
    }

    for metric in definitions:
        score = 0.0
        matched_terms = direct_terms_by_metric[metric.id]
        candidates = [metric.name, metric.id, *metric.aliases]
        for candidate in candidates:
            if candidate in matched_terms:
                score += 8.0 if candidate in metric.aliases else 5.0
            overlap = question_tokens.intersection(_tokens(candidate))
            if overlap:
                score += float(len(overlap))

        canonical_source_id = canonical_sources_by_target.get(metric.id)
        canonical_target_id = active_canonical_mappings.get(metric.id)
        if score <= 0 and canonical_source_id:
            # Explicit project identity, rather than retrieval score, makes the
            # canonical target available for the Planner decision.
            score = 1.0
        if score <= 0:
            continue
        canonical_metric_mapping = None
        if canonical_source_id:
            canonical_metric_mapping = {
                "role": "canonical_target",
                "source_metric_id": canonical_source_id,
                "target_metric_id": metric.id,
                "source": "project_override",
            }
        elif canonical_target_id:
            canonical_metric_mapping = {
                "role": "mapped_source",
                "source_metric_id": metric.id,
                "target_metric_id": canonical_target_id,
                "source": "project_override",
            }
        knowledge_context = _metric_knowledge_context(
            metric,
            project_override,
            canonical_metric_mapping=canonical_metric_mapping,
        )
        bindings, missing, time_field_candidates = bind_metric_fields(
            metric,
            profiles,
            project_override=project_override,
            time_concept=knowledge_context["effective"]["time_concept"],
        )
        metric_override = knowledge_context.get("applied_metric_override", {})
        policy_ids = {
            *metric_override.get("population_policies", []),
            *metric_override.get("numerator_population_policies", []),
            *metric_override.get("denominator_population_policies", []),
        }
        available = _all_profile_columns(profiles)
        policy_contracts = (project_override or {}).get("policy_contracts", {})
        for policy_id in policy_ids:
            for item in policy_contracts.get(policy_id, {}).get("filters", []):
                concept = str(item.get("concept", ""))
                if concept and concept not in bindings:
                    policy_bindings = _bind_concept(concept, available, project_override)
                    if policy_bindings:
                        bindings[concept] = policy_bindings
        coverage = (len(metric.required_concepts) - len(missing)) / max(len(metric.required_concepts), 1)
        score += coverage * 2.0
        match_type = "exact" if matched_terms else "token_overlap"
        shadowed_by = _find_nested_alias_shadow(
            metric.id,
            matched_terms,
            direct_terms_by_metric,
        )
        if canonical_target_id:
            shadowed_by = canonical_target_id
        matches.append(MetricMatch(
            metric=metric,
            score=round(score, 3),
            matched_terms=sorted(set(matched_terms)),
            match_type=match_type,
            decision_required=(
                canonical_source_id is not None
                or (match_type == "exact" and shadowed_by is None)
            ),
            shadowed_by=shadowed_by,
            field_bindings=bindings,
            missing_concepts=missing,
            time_field_candidates=time_field_candidates,
            knowledge_context=knowledge_context,
        ))

    matches.sort(key=lambda item: item.score, reverse=True)
    return matches[:limit]


def compact_metric_match(match: MetricMatch) -> Dict[str, Any]:
    metric = match.metric
    effective = match.knowledge_context.get("effective", {})
    time_concept = effective.get("time_concept", metric.time_concept)
    return {
        "id": metric.id,
        "name": metric.name,
        "description": metric.description,
        "formula": metric.formula,
        "entity": metric.entity,
        "grain": metric.grain,
        "required_concepts": metric.required_concepts,
        "time_concept": time_concept,
        "domain_time_concept": metric.time_concept,
        "time_field_candidates": match.time_field_candidates,
        "time_binding_status": (
            "resolved" if match.time_field_candidates else "unresolved"
        ) if time_concept else "not_applicable",
        "default_population": effective.get("default_population", metric.default_population),
        "domain_default_population": metric.default_population,
        "denominator_policy": effective.get("denominator_policy", metric.denominator_policy),
        "domain_denominator_policy": metric.denominator_policy,
        "default_filters": metric.default_filters,
        "allowed_dimensions": metric.allowed_dimensions,
        "caveats": metric.caveats,
        "matched_terms": match.matched_terms,
        "match_type": match.match_type,
        "decision_required": match.decision_required,
        "shadowed_by": match.shadowed_by,
        "field_bindings": match.field_bindings,
        "missing_concepts": match.missing_concepts,
        "knowledge_context": match.knowledge_context,
        "retrieval_score": match.score,
    }


def _resolved_field(item: Dict[str, str]) -> Dict[str, str]:
    return {
        "dataset": item["file_name"],
        "column": item["column"],
        "binding_source": item.get("binding_source", "domain_alias"),
    }


def _resolve_policy_filters(
    policy_ids: List[str],
    project_override: Optional[Dict[str, Any]],
    available: List[Dict[str, str]],
) -> tuple[List[Dict[str, Any]], List[str]]:
    filters: List[Dict[str, Any]] = []
    unresolved: List[str] = []
    policy_contracts = (project_override or {}).get("policy_contracts", {})
    for policy_id in policy_ids:
        policy = policy_contracts.get(policy_id)
        if not policy:
            unresolved.append(f"Project policy contract '{policy_id}' is not defined.")
            continue
        for item in policy.get("filters", []):
            concept = str(item.get("concept", ""))
            bindings = _bind_concept(concept, available, project_override)
            if len(bindings) != 1:
                unresolved.append(
                    f"Policy '{policy_id}' requires one unambiguous binding for "
                    f"'{concept}', found {len(bindings)}."
                )
                continue
            filters.append({
                "dataset": bindings[0]["file_name"],
                "column": bindings[0]["column"],
                "operator": item.get("operator"),
                "value": item.get("value"),
            })
    return filters, unresolved


def _formula_operands(formula: str) -> tuple[str, Optional[str]]:
    numerator, separator, denominator = formula.partition("/")
    return numerator.strip(), denominator.strip() if separator else None


def resolve_metric_contract(match: MetricMatch) -> Dict[str, Any]:
    """Compile one metric match into the sole effective semantic view for Planner."""
    metric = match.metric
    context = match.knowledge_context
    effective = context.get("effective", {})
    metric_override = context.get("applied_metric_override", {})
    project_id = context.get("project_id")
    project_override = load_project_override(project_id) if project_id else None
    available = _all_profile_columns_from_bindings(match)

    population_policy_ids = list(metric_override.get("population_policies", []))
    numerator_policy_ids = list(metric_override.get("numerator_population_policies", []))
    denominator_policy_ids = list(metric_override.get("denominator_population_policies", []))
    population_filters, population_issues = _resolve_policy_filters(
        population_policy_ids,
        project_override,
        available,
    )
    numerator_filters, numerator_issues = _resolve_policy_filters(
        numerator_policy_ids,
        project_override,
        available,
    )
    denominator_filters, denominator_issues = _resolve_policy_filters(
        denominator_policy_ids,
        project_override,
        available,
    )
    if not numerator_policy_ids:
        numerator_filters = list(population_filters)
    if not denominator_policy_ids:
        denominator_filters = list(population_filters)

    unresolved = [
        *(f"Required concept '{concept}' is not bound." for concept in match.missing_concepts),
        *population_issues,
        *numerator_issues,
        *denominator_issues,
    ]
    time_concept = effective.get("time_concept", metric.time_concept)
    resolved_time_field = None
    if time_concept:
        if len(match.time_field_candidates) == 1:
            resolved_time_field = _resolved_field(match.time_field_candidates[0])
        else:
            unresolved.append(
                f"Time concept '{time_concept}' has {len(match.time_field_candidates)} candidate bindings."
            )

    policy_descriptions = (project_override or {}).get("policies", {})
    pre_aggregation_policy_ids = list(metric_override.get("pre_aggregation_policies", []))
    pre_aggregation_requirements = []
    for policy_id in pre_aggregation_policy_ids:
        description = policy_descriptions.get(policy_id)
        if description:
            pre_aggregation_requirements.append(description)
        else:
            unresolved.append(f"Pre-aggregation policy '{policy_id}' is not defined.")

    numerator_formula, denominator_formula = _formula_operands(metric.formula)
    source_by_semantic = {
        "formula": "domain_metric_definition",
        "population": (
            "project_override" if "default_population" in metric_override else "domain_metric_definition"
        ) if effective.get("default_population", metric.default_population) else None,
        "denominator": (
            "project_override" if "denominator_policy" in metric_override else "domain_metric_definition"
        ) if effective.get("denominator_policy", metric.denominator_policy) else None,
        "time": (
            "project_override" if "time_concept" in metric_override else "domain_metric_definition"
        ) if time_concept else None,
        "pre_aggregation": "project_override" if pre_aggregation_policy_ids else None,
    }
    return {
        "metric_id": metric.id,
        "label": metric.name,
        "formula": metric.formula,
        "entity": metric.entity,
        "grain": metric.grain,
        "resolved_population": {
            "description": effective.get("default_population", metric.default_population),
            "filters": population_filters,
        },
        "resolved_numerator": {
            "calculation_semantics": numerator_formula,
            "filters": numerator_filters,
        },
        "resolved_denominator": (
            {
                "calculation_semantics": denominator_formula,
                "policy": effective.get("denominator_policy", metric.denominator_policy),
                "filters": denominator_filters,
            }
            if denominator_formula or effective.get("denominator_policy", metric.denominator_policy)
            else None
        ),
        "time_concept": time_concept,
        "resolved_time_field": resolved_time_field,
        "required_bindings": {
            concept: [_resolved_field(item) for item in bindings]
            for concept, bindings in match.field_bindings.items()
        },
        "pre_aggregation_requirements": pre_aggregation_requirements,
        "allowed_dimensions": metric.allowed_dimensions,
        "caveats": metric.caveats,
        "resolution_status": "unresolved" if unresolved else "resolved",
        "unresolved_requirements": unresolved,
        "provenance": {
            "project_id": project_id,
            "canonical_metric_mapping": context.get("canonical_metric_mapping"),
            "source_by_semantic": source_by_semantic,
            "population_policy_ids": population_policy_ids,
            "numerator_population_policy_ids": numerator_policy_ids,
            "denominator_population_policy_ids": denominator_policy_ids,
            "pre_aggregation_policy_ids": pre_aggregation_policy_ids,
        },
    }


def _all_profile_columns_from_bindings(match: MetricMatch) -> List[Dict[str, str]]:
    unique: Dict[tuple[str, str], Dict[str, str]] = {}
    for bindings in match.field_bindings.values():
        for item in bindings:
            unique[(item["file_name"], item["column"])] = {
                "file_name": item["file_name"],
                "column": item["column"],
            }
    return list(unique.values())


def resolved_metric_candidate(match: MetricMatch) -> Dict[str, Any]:
    """Return resolved semantics plus only the candidate metadata Planner needs."""
    contract = resolve_metric_contract(match)
    return {
        "id": contract["metric_id"],
        **contract,
        "decision_required": match.decision_required,
        "shadowed_by": match.shadowed_by,
        "match_type": match.match_type,
        "matched_terms": match.matched_terms,
        "missing_concepts": match.missing_concepts,
    }
