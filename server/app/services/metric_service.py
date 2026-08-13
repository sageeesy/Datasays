"""Local business-metric semantic layer and deterministic retrieval."""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List

from app.schemas.analysis import MetricDefinition, MetricMatch


KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"

CONCEPT_ALIASES: Dict[str, List[str]] = {
    "order_id": ["order_id", "orderid", "transaction_id", "transactionid", "订单id", "订单号", "交易号"],
    "customer_id": ["customer_id", "customerid", "user_id", "userid", "buyer_id", "account_id", "用户id", "客户id", "买家id"],
    "account_id": ["account_id", "accountid", "customer_id", "customerid", "company_id", "workspace_id", "账户id", "客户id"],
    "subscription_id": ["subscription_id", "subscriptionid", "订阅id"],
    "order_amount": ["order_amount", "amount", "sales", "gmv", "revenue", "total_amount", "订单金额", "成交金额", "销售额"],
    "paid_amount": ["paid_amount", "payment_amount", "net_sales", "revenue", "sales", "实付金额", "支付金额", "净销售额"],
    "refund_amount": ["refund_amount", "refunded_amount", "return_amount", "退款金额", "退货金额"],
    "order_time": ["order_time", "order_date", "created_at", "date", "订单时间", "下单时间", "日期"],
    "payment_time": ["payment_time", "paid_at", "purchase_time", "purchase_date", "date", "支付时间", "购买时间", "日期"],
    "event_time": ["event_time", "timestamp", "occurred_at", "date", "事件时间", "时间", "日期"],
    "channel": ["channel", "source", "utm_source", "acquisition_channel", "渠道", "来源"],
    "acquisition_channel": ["acquisition_channel", "channel", "source", "utm_source", "获客渠道", "渠道"],
    "region": ["region", "country", "city", "market", "地区", "区域", "国家", "城市"],
    "product_category": ["product_category", "category", "product", "商品类目", "品类", "产品"],
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


@lru_cache(maxsize=1)
def load_metric_definitions() -> List[MetricDefinition]:
    records: List[Dict[str, Any]] = []
    for filename in ("ecommerce_metrics.json", "saas_metrics.json"):
        records.extend(json.loads((KNOWLEDGE_DIR / filename).read_text(encoding="utf-8")))
    return [MetricDefinition.model_validate(record) for record in records]


def _all_profile_columns(profiles: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
    columns = []
    for profile in profiles:
        file_name = str(profile.get("file_name", "dataset"))
        for item in profile.get("columns", []):
            columns.append({"file_name": file_name, "column": str(item.get("name", ""))})
    return columns


def bind_metric_fields(metric: MetricDefinition, profiles: List[Dict[str, Any]]) -> tuple[Dict[str, List[Dict[str, str]]], List[str]]:
    available = _all_profile_columns(profiles)
    bindings: Dict[str, List[Dict[str, str]]] = {}
    missing = []

    for concept in metric.required_concepts:
        aliases = [_normalize(alias) for alias in CONCEPT_ALIASES.get(concept, [concept])]
        matches = [item for item in available if _normalize(item["column"]) in aliases]
        if matches:
            bindings[concept] = matches
        else:
            missing.append(concept)
    return bindings, missing


def retrieve_metric_definitions(question: str, profiles: List[Dict[str, Any]], limit: int = 4) -> List[MetricMatch]:
    normalized_question = _normalize(question)
    question_tokens = _tokens(question)
    matches: List[MetricMatch] = []

    for metric in load_metric_definitions():
        score = 0.0
        matched_terms: List[str] = []
        candidates = [metric.name, metric.id, *metric.aliases]
        for candidate in candidates:
            normalized_candidate = _normalize(candidate)
            if normalized_candidate and normalized_candidate in normalized_question:
                score += 8.0 if candidate in metric.aliases else 5.0
                matched_terms.append(candidate)
            overlap = question_tokens.intersection(_tokens(candidate))
            if overlap:
                score += float(len(overlap))

        if score <= 0:
            continue
        bindings, missing = bind_metric_fields(metric, profiles)
        coverage = (len(metric.required_concepts) - len(missing)) / max(len(metric.required_concepts), 1)
        score += coverage * 2.0
        matches.append(MetricMatch(
            metric=metric,
            score=round(score, 3),
            matched_terms=sorted(set(matched_terms)),
            field_bindings=bindings,
            missing_concepts=missing,
        ))

    matches.sort(key=lambda item: item.score, reverse=True)
    return matches[:limit]


def compact_metric_match(match: MetricMatch) -> Dict[str, Any]:
    metric = match.metric
    return {
        "id": metric.id,
        "name": metric.name,
        "description": metric.description,
        "formula": metric.formula,
        "entity": metric.entity,
        "grain": metric.grain,
        "required_concepts": metric.required_concepts,
        "default_filters": metric.default_filters,
        "allowed_dimensions": metric.allowed_dimensions,
        "caveats": metric.caveats,
        "field_bindings": match.field_bindings,
        "missing_concepts": match.missing_concepts,
        "retrieval_score": match.score,
    }
