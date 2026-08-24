#!/usr/bin/env python3
"""Generate the capability-oriented Olist Business Analysis Suite v2."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from evals.olist_business_reference import calculate_business_reference


EVAL_DIR = Path(__file__).resolve().parent
DATA_DIR = EVAL_DIR / "data" / "olist"
OUTPUT_PATH = EVAL_DIR / "business_benchmark_cases.json"

ALL_DATASETS = [
    "olist_orders_2017",
    "olist_order_items_2017",
    "olist_order_payments_2017",
    "olist_order_reviews_2017",
    "olist_products_2017",
]


def fact(
    identifier: str,
    value: Any,
    tolerance: float = 0.001,
    terms: Optional[List[str]] = None,
) -> Dict[str, Any]:
    stable_value = round(value, 12) if isinstance(value, float) else value
    payload: Dict[str, Any] = {"id": identifier, "value": stable_value}
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        payload["tolerance"] = tolerance
    if terms:
        payload["terms"] = terms
    return payload


def expected(
    facts: Optional[List[Dict[str, Any]]] = None,
    term_groups: Optional[List[List[str]]] = None,
    metric_ids: Optional[List[str]] = None,
    visualization_types: Optional[List[str]] = None,
    plan_intents: Optional[List[str]] = None,
    clarification: bool = False,
    clarification_terms: Optional[List[str]] = None,
    memory_used: Optional[bool] = None,
    min_fact_recall: float = 1.0,
    min_term_coverage: float = 0.5,
) -> Dict[str, Any]:
    return {
        "facts": facts or [],
        "required_term_groups": term_groups or [],
        "metric_ids": metric_ids or [],
        "visualization_types": visualization_types or [],
        "plan_intents": plan_intents or [],
        "clarification": clarification,
        "clarification_terms": clarification_terms or [],
        "memory_used": memory_used,
        "min_fact_recall": min_fact_recall,
        "min_term_coverage": min_term_coverage,
    }


def case(
    identifier: str,
    category: str,
    question: str,
    datasets: List[str],
    expectation: Dict[str, Any],
    user_need: str,
    capability: str,
    difficulty: str = "hard",
) -> Dict[str, Any]:
    return {
        "id": identifier,
        "category": category,
        "difficulty": difficulty,
        "language": "zh",
        "datasets": datasets,
        "question": question,
        "user_need": user_need,
        "capability": capability,
        "expected": expectation,
    }


def build_cases(r: Dict[str, Any]) -> List[Dict[str, Any]]:
    cases = [
        case(
            "executive_business_snapshot", "metric_execution",
            "请给管理层做一页2017年经营概览：说明已交付订单规模、支付GMV、AOV和交付率，并用月度趋势图展示经营变化。明确你的指标口径和数据限制。",
            ["olist_orders_2017", "olist_order_payments_2017"],
            expected(
                facts=[
                    fact("delivered_orders", r["delivered_orders"], 0, ["订单"]),
                    fact("gmv", r["gmv"], 0.01, ["GMV"]),
                    fact("aov", r["aov"], 0.01, ["AOV", "客单价"]),
                    fact("delivered_rate", r["delivered_rate"], 0.0001, ["交付率", "妥投率"]),
                ],
                term_groups=[["口径", "定义"], ["限制", "仅包含", "2017"]],
                metric_ids=["ecommerce.order_count", "ecommerce.gmv", "ecommerce.aov"],
                visualization_types=["line"], plan_intents=["metric_diagnostic", "trend"],
            ),
            "管理层快速判断业务规模和趋势", "多指标经营概览与可视化",
        ),
        case(
            "monthly_peak_diagnosis", "metric_execution",
            "2017年已交付业务在哪个月达到峰值？请同时检查月度GMV、订单量和AOV，判断峰值更可能由哪个指标驱动，并返回支持判断的月度趋势。",
            ["olist_orders_2017", "olist_order_payments_2017"],
            expected(
                facts=[
                    fact("peak_month", r["peak_month"]),
                    fact("peak_month_gmv", r["peak_month_gmv"], 0.01),
                    fact("peak_month_orders", r["peak_month_orders"], 0),
                ],
                term_groups=[["订单量", "订单数"], ["AOV", "客单价"], ["驱动", "贡献"]],
                visualization_types=["line"], plan_intents=["trend"], min_term_coverage=0.67,
            ),
            "理解经营峰值由规模还是价格驱动", "时间趋势与驱动拆解",
        ),
        case(
            "state_revenue_concentration", "metric_execution",
            "经营收入是否过度集中在少数州？请计算已交付订单的州级支付GMV，给出第一名州、其GMV占比以及前三州合计占比，并提供州级排名图。",
            ["olist_orders_2017", "olist_order_payments_2017"],
            expected(
                facts=[fact("top_state", r["top_state"]), fact("top_state_gmv", r["top_state_gmv"], 0.01),
                       fact("top_state_share", r["top_state_share"], 0.0001), fact("top3_state_share", r["top3_state_share"], 0.0001)],
                term_groups=[["集中", "占比"], ["前三", "Top 3", "top3"]],
                metric_ids=["ecommerce.gmv"], visualization_types=["bar"], plan_intents=["ranking"],
            ),
            "识别地区收入集中风险", "分组排名与集中度",
        ),
        case(
            "category_revenue_concentration", "metric_execution",
            "哪些商品品类构成收入基本盘？按已交付商品price计算品类收入，给出第一品类、第一品类占比和前五品类合计占比，并展示品类排名。不要把运费算作商品收入。",
            ["olist_orders_2017", "olist_order_items_2017", "olist_products_2017"],
            expected(
                facts=[fact("top_category", r["top_category"]), fact("top_category_revenue", r["top_category_revenue"], 0.01),
                       fact("top_category_share", r["top_category_share"], 0.0001), fact("top5_category_share", r["top5_category_share"], 0.0001)],
                term_groups=[["price", "商品收入"], ["运费", "freight"], ["前五", "Top 5", "top5"]],
                visualization_types=["bar"], plan_intents=["ranking"], min_term_coverage=0.67,
            ),
            "识别核心品类与集中风险", "多表品类排名",
        ),
        case(
            "repeat_customer_health", "metric_execution",
            "请评估2017年已交付客户的复购健康度。说明应使用哪个客户标识，计算至少下单两次的客户数量和复购客户占比，并解释这一结果不能代表完整生命周期复购率的原因。",
            ["olist_orders_2017"],
            expected(
                facts=[fact("repeat_buyer_count", r["repeat_buyer_count"], 0), fact("repeat_buyer_rate", r["repeat_buyer_rate"], 0.0001)],
                term_groups=[["customer_unique_id"], ["customer_id"], ["完整生命周期", "仅2017", "观察窗口"]],
                metric_ids=["ecommerce.repeat_purchase_rate"], plan_intents=["cohort", "metric_diagnostic"], min_term_coverage=0.67,
            ),
            "判断客户留存和复购基础", "客户身份与观察窗口",
        ),
        case(
            "payment_structure_risk", "metric_execution",
            "请分析已交付订单的支付结构：比较信用卡和boleto的支付金额占比，并计算多次支付订单占比。说明这些结果反映的是支付结构，不要把金额占比和订单占比混为一谈。",
            ["olist_orders_2017", "olist_order_payments_2017"],
            expected(
                facts=[fact("credit_card_share", r["credit_card_share"], 0.0001), fact("boleto_share", r["boleto_share"], 0.0001),
                       fact("multi_payment_rate", r["multi_payment_rate"], 0.0001)],
                term_groups=[["金额占比"], ["订单占比", "多次支付"]], plan_intents=["aggregation", "metric_diagnostic"],
            ),
            "理解支付渠道结构和复杂支付比例", "不同分母的指标计算",
        ),
        case(
            "fact_table_join_audit", "data_quality_grain",
            "财务同事担心商品明细和支付明细直接关联会把金额放大。请自行审计两张事实表的粒度，量化直接Join造成的支付金额膨胀和商品收入膨胀，并核对正确支付总额与商品加运费总额的差异比例。给出安全Join建议。",
            ["olist_orders_2017", "olist_order_items_2017", "olist_order_payments_2017"],
            expected(
                facts=[fact("payment_join_inflation", r["payment_join_inflation"], 0.0001), fact("item_join_inflation", r["item_join_inflation"], 0.0001),
                       fact("reconciliation_gap_rate", r["reconciliation_gap_rate"], 0.00001)],
                term_groups=[["粒度", "grain"], ["多对多", "many-to-many"], ["先聚合", "汇总后关联"]],
                plan_intents=["data_quality", "metric_diagnostic"], min_term_coverage=0.67,
            ),
            "避免经营金额因错误Join失真", "事实表粒度审计",
        ),
        case(
            "review_grain_audit", "data_quality_grain",
            "评价表是否能直接按行计算平均分？请检查一笔订单多条评价的问题，给出存在重复评价的订单数，并比较原始评价行均值与订单级均值。解释推荐口径。",
            ["olist_orders_2017", "olist_order_reviews_2017"],
            expected(
                facts=[fact("duplicate_review_orders", r["duplicate_review_orders"], 0), fact("raw_review_mean", r["raw_review_mean"], 0.0001),
                       fact("order_review_mean", r["order_review_mean"], 0.0001), fact("review_grain_delta", r["review_grain_delta"], 0.0001)],
                term_groups=[["订单级", "按订单"], ["重复评价", "多条评价"], ["加权", "重权"]], plan_intents=["data_quality"], min_term_coverage=0.67,
            ),
            "避免重复评价改变客户体验指标", "重复记录与分析粒度",
        ),
        case(
            "customer_identity_audit", "data_quality_grain",
            "复购分析应该使用customer_id还是customer_unique_id？请用数据验证两种标识得到的复购率差异，并解释选择理由。",
            ["olist_orders_2017"],
            expected(
                facts=[fact("unique_id_repeat_rate", r["repeat_buyer_rate"], 0.0001), fact("customer_id_repeat_rate", r["customer_id_repeat_rate"], 0.000001)],
                term_groups=[["customer_unique_id"], ["customer_id"], ["订单级", "稳定客户"]],
                metric_ids=["ecommerce.repeat_purchase_rate"], plan_intents=["data_quality", "metric_diagnostic"], min_term_coverage=1.0,
            ),
            "确认复购分析的客户主键", "实体标识审计",
        ),
        case(
            "missingness_business_impact", "data_quality_grain",
            "请检查会影响履约和评价分析的数据缺失：已交付订单缺少实际送达时间的数量、没有任何评价记录的订单数量及比例、评价行缺少评论正文的比例。区分这三类缺失的业务含义。",
            ["olist_orders_2017", "olist_order_reviews_2017"],
            expected(
                facts=[fact("missing_delivery", r["missing_actual_delivery"], 0), fact("orders_without_review", r["orders_without_review"], 0),
                       fact("orders_without_review_rate", r["orders_without_review_rate"], 0.0001), fact("missing_comment_rate", r["missing_review_comment_rate"], 0.0001)],
                term_groups=[["送达时间"], ["没有评价", "无评价记录"], ["评论正文", "has_review_comment"]],
                plan_intents=["data_quality"], min_term_coverage=1.0,
            ),
            "理解缺失数据对经营结论的影响", "数据画像与业务含义",
        ),
        case(
            "late_delivery_experience_gap", "business_diagnosis",
            "履约延迟与客户评分之间有什么关系？请比较准时和延迟订单的订单级平均评分、评分差距和延迟率，并明确这只能说明相关关系。提供对比图。",
            ["olist_orders_2017", "olist_order_reviews_2017"],
            expected(
                facts=[fact("late_rate", r["late_delivery_rate"], 0.0001), fact("late_score", r["late_review_score"], 0.001),
                       fact("on_time_score", r["on_time_review_score"], 0.001), fact("score_gap", r["review_score_gap"], 0.001)],
                term_groups=[["相关", "关联"], ["不能证明", "不代表因果"], ["订单级", "按订单"]],
                visualization_types=["bar"], plan_intents=["metric_diagnostic"], min_term_coverage=0.67,
            ),
            "判断履约问题是否伴随体验下降", "分组比较与因果边界",
        ),
        case(
            "state_delivery_hotspot", "business_diagnosis",
            "为了避免小样本误导，只比较至少500个已交付订单的州。哪个州延迟率最高？请给出该州订单数、延迟率和平均评价分，并展示州级延迟率排名。",
            ["olist_orders_2017", "olist_order_reviews_2017"],
            expected(
                facts=[fact("state", r["state_delay_hotspot"]), fact("orders", r["state_delay_hotspot_orders"], 0),
                       fact("late_rate", r["state_delay_hotspot_rate"], 0.0001), fact("review", r["state_delay_hotspot_review"], 0.001)],
                term_groups=[["500", "样本量"], ["延迟率"]], visualization_types=["bar"], plan_intents=["ranking"],
            ),
            "定位履约改善优先区域", "样本门槛与风险排名",
        ),
        case(
            "category_experience_problem", "business_diagnosis",
            "在至少500个已交付订单的品类中，找出平均评价最低的品类。请同时给出其商品收入和延迟率，判断它是否属于值得优先改善的高影响问题。",
            ["olist_orders_2017", "olist_order_items_2017", "olist_products_2017", "olist_order_reviews_2017"],
            expected(
                facts=[fact("category", r["category_problem"]), fact("revenue", r["category_problem_revenue"], 0.01),
                       fact("review", r["category_problem_review"], 0.001), fact("late_rate", r["category_problem_late_rate"], 0.0001)],
                term_groups=[["500", "样本量"], ["优先", "改善"], ["影响", "收入"]], visualization_types=["scatter", "bar"],
                plan_intents=["ranking", "metric_diagnostic"], min_term_coverage=0.67,
            ),
            "寻找高影响低体验品类", "多指标优先级诊断",
        ),
        case(
            "seller_risk_diagnosis", "business_diagnosis",
            "请在收入前10%且至少50个已交付订单的卖家中，找出延迟率最高的卖家。给出卖家ID、收入、订单量、延迟率和评价分，并说明筛选门槛。",
            ["olist_orders_2017", "olist_order_items_2017", "olist_order_reviews_2017"],
            expected(
                facts=[fact("seller", r["seller_risk"]), fact("revenue", r["seller_risk_revenue"], 0.01), fact("orders", r["seller_risk_orders"], 0),
                       fact("late_rate", r["seller_risk_late_rate"], 0.0001), fact("review", r["seller_risk_review"], 0.001)],
                term_groups=[["前10%", "top 10"], ["50", "样本量"], ["延迟率"]], plan_intents=["ranking"], min_term_coverage=0.67,
            ),
            "识别需要治理的高影响卖家", "约束筛选与风险排名",
        ),
        case(
            "monthly_decline_decomposition", "business_diagnosis",
            "排除12月后，在2月至11月中找出GMV环比下降最严重的月份，并将变化拆解为订单量环比和AOV环比。说明主要下降驱动。",
            ["olist_orders_2017", "olist_order_payments_2017"],
            expected(
                facts=[fact("month", r["largest_decline_month"]), fact("gmv_mom", r["largest_decline_gmv_mom"], 0.0001),
                       fact("orders_mom", r["largest_decline_orders_mom"], 0.0001), fact("aov_mom", r["largest_decline_aov_mom"], 0.0001)],
                term_groups=[["订单量", "订单数"], ["AOV", "客单价"], ["主要", "驱动"]], visualization_types=["line"],
                plan_intents=["trend"], min_term_coverage=1.0,
            ),
            "解释经营下滑来自量还是价", "环比异常与驱动拆解",
        ),
        case(
            "regional_growth_priority", "decision_support",
            "如果暂不考虑SP，希望选择一个已有规模基础的州作为下一步重点市场，请基于已交付支付GMV、订单规模和AOV提出优先州，并用数据解释建议和风险。",
            ["olist_orders_2017", "olist_order_payments_2017"],
            expected(
                facts=[fact("state", r["non_sp_growth_state"]), fact("gmv", r["non_sp_growth_gmv"], 0.01), fact("aov", r["non_sp_growth_aov"], 0.01)],
                term_groups=[["建议", "优先"], ["风险", "限制"], ["订单", "规模"]], visualization_types=["bar", "scatter"],
                plan_intents=["ranking", "metric_diagnostic"], min_term_coverage=0.67,
            ),
            "选择重点市场并说明依据", "证据驱动的经营建议",
        ),
        case(
            "fulfillment_action_plan", "decision_support",
            "请制定履约改善优先级：量化总体延迟订单规模和延迟率、评分损失，并指出最需要关注的州。最后给出两项与证据对应的行动建议，不要声称已经证明因果。",
            ["olist_orders_2017", "olist_order_reviews_2017"],
            expected(
                facts=[fact("late_orders", r["late_delivery_count"], 0), fact("late_rate", r["late_delivery_rate"], 0.0001),
                       fact("score_gap", r["review_score_gap"], 0.001), fact("state", r["state_delay_hotspot"])],
                term_groups=[["建议", "行动"], ["相关", "不能证明"], ["优先", "关注"]], min_term_coverage=1.0,
            ),
            "把履约分析转成行动优先级", "量化诊断与可执行建议",
        ),
        case(
            "category_portfolio_strategy", "decision_support",
            "请把品类经营分成“保持增长”和“优先改善”两类：识别收入第一的核心品类，以及在至少500单品类中评价最低的问题品类，并给出各自的关键证据和建议。",
            ["olist_orders_2017", "olist_order_items_2017", "olist_products_2017", "olist_order_reviews_2017"],
            expected(
                facts=[fact("growth_category", r["top_category"]), fact("growth_revenue", r["top_category_revenue"], 0.01),
                       fact("problem_category", r["category_problem"]), fact("problem_review", r["category_problem_review"], 0.001)],
                term_groups=[["保持增长", "增长"], ["优先改善", "改善"], ["证据", "收入", "评价"]], min_term_coverage=1.0,
            ),
            "形成品类组合策略", "多目标分类与建议",
        ),
        case(
            "seller_governance_strategy", "decision_support",
            "请为卖家治理提出一个可执行的优先对象：限定收入前10%且订单数不少于50，选择延迟风险最高的卖家，说明其规模、履约和评价证据，并提出后续核查动作。",
            ["olist_orders_2017", "olist_order_items_2017", "olist_order_reviews_2017"],
            expected(
                facts=[fact("seller", r["seller_risk"]), fact("orders", r["seller_risk_orders"], 0),
                       fact("late_rate", r["seller_risk_late_rate"], 0.0001), fact("review", r["seller_risk_review"], 0.001)],
                term_groups=[["核查", "建议", "行动"], ["收入前10%", "top 10"], ["50"]], min_term_coverage=0.67,
            ),
            "形成卖家治理对象和后续动作", "风险筛选与行动建议",
        ),
        case(
            "channel_quality_clarification", "clarification_boundary",
            "哪个获客渠道的新客质量最好？请比较各渠道的新客复购和客单价。",
            ["olist_orders_2017", "olist_order_payments_2017"],
            expected(
                clarification=True,
                clarification_terms=["渠道", "字段", "新客", "首次"],
                term_groups=[["缺少", "没有", "无法"], ["渠道"], ["新客", "首次"]], min_term_coverage=0.67,
            ),
            "在数据不足时先澄清而不是编造", "缺字段与指标口径澄清",
        ),
        case(
            "profit_metric_clarification", "clarification_boundary",
            "哪个商品品类利润最高？请给出利润额和利润率排名。",
            ["olist_orders_2017", "olist_order_items_2017", "olist_products_2017"],
            expected(
                clarification=True,
                clarification_terms=["成本", "利润", "毛利", "字段"],
                term_groups=[["成本", "进货成本"], ["利润", "毛利"], ["缺少", "没有", "无法"]], min_term_coverage=1.0,
            ),
            "在利润数据缺失时拒绝伪造", "不可计算指标澄清",
        ),
        case(
            "causal_claim_boundary", "clarification_boundary",
            "请证明延迟送达导致客户评分下降，并告诉我延迟造成了多少评分损失。",
            ["olist_orders_2017", "olist_order_reviews_2017"],
            expected(
                facts=[fact("late_rate", r["late_delivery_rate"], 0.0001), fact("association_gap", r["review_score_gap"], 0.001)],
                term_groups=[["不能证明", "无法证明", "不代表因果"], ["相关", "关联"], ["混杂", "其他因素", "实验"]],
                plan_intents=["metric_diagnostic"], min_term_coverage=0.67,
            ),
            "避免把观察数据相关性写成因果", "统计边界与谨慎表达",
        ),
    ]

    cases.append({
        "id": "state_category_followup", "category": "multi_turn_memory", "difficulty": "hard", "language": "zh",
        "datasets": ["olist_orders_2017", "olist_order_items_2017", "olist_order_payments_2017", "olist_products_2017"],
        "user_need": "基于前一轮结果继续缩小分析范围", "capability": "指代消解、可信记忆与重新计算",
        "turns": [
            {"question": "2017年已交付支付GMV最高的是哪个州？给出该州GMV。",
             "expected": expected(facts=[fact("state", r["top_state"]), fact("gmv", r["top_state_gmv"], 0.01)], metric_ids=["ecommerce.gmv"])},
            {"question": "只看这个州，哪个商品品类收入最高？商品收入只计算price，并给出该品类收入。",
             "expected": expected(facts=[fact("category", r["top_state_category"]), fact("revenue", r["top_state_category_revenue"], 0.01)],
                                  term_groups=[[r["top_state"]], ["price", "商品收入"]], memory_used=True, min_term_coverage=1.0)},
        ],
    })
    cases.append({
        "id": "experience_executive_followup", "category": "multi_turn_memory", "difficulty": "hard", "language": "zh",
        "datasets": ["olist_orders_2017", "olist_order_reviews_2017"],
        "user_need": "将已有分析转成管理层摘要", "capability": "多轮记忆、重算与报告组织",
        "turns": [
            {"question": "分析已交付订单的延迟与评价关系，比较准时和延迟订单评分并说明边界。",
             "expected": expected(facts=[fact("late", r["late_review_score"], 0.001), fact("on_time", r["on_time_review_score"], 0.001),
                                               fact("gap", r["review_score_gap"], 0.001)], term_groups=[["相关", "不代表因果"]])},
            {"question": "把刚才的分析整理成管理层摘要：保留关键数字、结论、限制和两项下一步建议。",
             "expected": expected(facts=[fact("late_rate", r["late_delivery_rate"], 0.0001), fact("gap", r["review_score_gap"], 0.001)],
                                  term_groups=[["限制", "边界"], ["建议", "下一步"], ["相关", "因果"]], memory_used=True, min_term_coverage=1.0)},
        ],
    })
    return cases


def build_config() -> Dict[str, Any]:
    references = calculate_business_reference(DATA_DIR)
    return {
        "benchmark_name": "datasays_olist_business_analysis_v2",
        "version": "2.1.0",
        "description": "A 24-case capability benchmark for metric execution, data-grain safety, diagnosis, decision support, clarification, and multi-turn memory.",
        "description_zh": "面向指标计算、数据粒度、经营诊断、决策支持、澄清边界和多轮记忆的24题能力评测。",
        "source": {
            "name": "Brazilian E-Commerce Public Dataset by Olist",
            "url": "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce",
            "license": "CC BY-NC-SA 4.0",
            "prepared_scope": (
                f"Deterministic customer-level sample of {references['orders_total']:,} orders "
                "purchased during calendar year 2017"
            ),
            "prepared_scope_zh": (
                f"2017 自然年内下单的 {references['orders_total']:,} 笔客户级确定性抽样订单及关联记录"
            ),
            "sampling": {
                "target_orders": 15000,
                "actual_orders": references["orders_total"],
                "unit": "customer_unique_id",
                "method": "sha256_ranked_customer_sample",
                "relationship_policy": "keep_all_selected_customer_orders_and_filter_child_tables_by_foreign_key",
            },
        },
        "datasets": {
            "olist_orders_2017": {"path": "data/olist/olist_orders_2017.csv", "grain": "one row per order"},
            "olist_order_items_2017": {"path": "data/olist/olist_order_items_2017.csv", "grain": "one row per order item"},
            "olist_order_payments_2017": {"path": "data/olist/olist_order_payments_2017.csv", "grain": "one row per payment sequence"},
            "olist_order_reviews_2017": {"path": "data/olist/olist_order_reviews_2017.csv", "grain": "one row per review record"},
            "olist_products_2017": {"path": "data/olist/olist_products_2017.csv", "grain": "one row per product"},
        },
        "defaults": {"prompt_style": "zero", "fact_tolerance": 0.001},
        "capability_dimensions": [
            "metric_execution", "data_quality_grain", "business_diagnosis",
            "decision_support", "clarification_boundary", "multi_turn_memory",
        ],
        "cases": build_cases(references),
    }


def main() -> None:
    config = build_config()
    OUTPUT_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(config['cases'])} cases to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
