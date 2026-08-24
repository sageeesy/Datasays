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


def _direct_match_terms(question: str, metric: MetricDefinition) -> List[str]:
    normalized_question = _normalize(question)
    return sorted({
        candidate
        for candidate in [metric.name, metric.id, *metric.aliases]
        if _normalize(candidate) and _normalize(candidate) in normalized_question
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

        if score <= 0:
            continue
        knowledge_context = _metric_knowledge_context(metric, project_override)
        bindings, missing, time_field_candidates = bind_metric_fields(
            metric,
            profiles,
            project_override=project_override,
            time_concept=knowledge_context["effective"]["time_concept"],
        )
        coverage = (len(metric.required_concepts) - len(missing)) / max(len(metric.required_concepts), 1)
        score += coverage * 2.0
        match_type = "exact" if matched_terms else "token_overlap"
        shadowed_by = _find_nested_alias_shadow(
            metric.id,
            matched_terms,
            direct_terms_by_metric,
        )
        matches.append(MetricMatch(
            metric=metric,
            score=round(score, 3),
            matched_terms=sorted(set(matched_terms)),
            match_type=match_type,
            decision_required=match_type == "exact" and shadowed_by is None,
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
