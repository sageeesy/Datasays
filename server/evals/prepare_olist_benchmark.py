#!/usr/bin/env python3
"""Prepare the Olist 2017 fixtures and the 24-case DataSays benchmark."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

try:
    from evals.olist_reference import calculate_reference_answers
except ModuleNotFoundError:  # Support direct execution from the server directory.
    from olist_reference import calculate_reference_answers


SOURCE_FILES = {
    "customers": "olist_customers_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "translations": "product_category_name_translation.csv",
}

DEFAULT_TARGET_ORDERS = 15_000


def _sample_customers_with_complete_order_history(
    orders: pd.DataFrame,
    target_orders: int,
) -> pd.DataFrame:
    """Select a deterministic customer sample without breaking repeat-order history."""
    if target_orders <= 0 or len(orders) <= target_orders:
        return orders.copy()

    order_counts = orders.groupby("customer_unique_id", dropna=False).size().to_dict()
    ranked_customers = sorted(
        order_counts,
        key=lambda value: hashlib.sha256(str(value).encode("utf-8")).hexdigest(),
    )
    selected_customers = []
    selected_order_count = 0
    for customer_id in ranked_customers:
        selected_customers.append(customer_id)
        selected_order_count += int(order_counts[customer_id])
        if selected_order_count >= target_orders:
            break

    return orders.loc[orders["customer_unique_id"].isin(selected_customers)].copy()


def _case(
    case_id: str,
    datasets: List[str],
    category: str,
    difficulty: str,
    language: str,
    question: str,
    expected_value: float,
    tolerance: float,
    metric_definition: str,
    failure_mode: str,
    expected_metric_ids: List[str] | None = None,
    expected_visualization_types: List[str] | None = None,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "id": case_id,
        "datasets": datasets,
        "category": category,
        "difficulty": difficulty,
        "language": language,
        "source": "Olist Brazilian E-Commerce Public Dataset",
        "question": question,
        "expected_type": "number",
        "expected_value": expected_value,
        "tolerance": tolerance,
        "metric_definition": metric_definition,
        "failure_mode": failure_mode,
    }
    if expected_metric_ids:
        result["expected_metric_ids"] = expected_metric_ids
    if expected_visualization_types:
        result["expected_visualization_types"] = expected_visualization_types
    return result


def _build_cases(answers: Dict[str, float]) -> List[Dict[str, Any]]:
    orders = ["olist_orders_2017"]
    orders_payments = ["olist_orders_2017", "olist_order_payments_2017"]
    orders_items = ["olist_orders_2017", "olist_order_items_2017"]
    item_products = ["olist_orders_2017", "olist_order_items_2017", "olist_products_2017"]
    order_reviews = ["olist_orders_2017", "olist_order_reviews_2017"]
    all_transactions = ["olist_orders_2017", "olist_order_items_2017", "olist_order_payments_2017"]

    return [
        _case(
            "orders_total_2017", orders, "order_lifecycle", "easy", "en",
            "How many orders were purchased during calendar year 2017 in the orders CSV? Count distinct order_id and return one number.",
            answers["orders_total_2017"], 0, "count_distinct(order_id)",
            "Counting rows without checking the order grain.", ["ecommerce.order_count"],
        ),
        _case(
            "delivered_order_rate", orders, "order_lifecycle", "easy", "zh",
            "2017 年订单中，order_status 等于 delivered 的订单占全部订单的比例是多少？返回 0 到 1 之间的一个数字。",
            answers["delivered_order_rate"], 0.0001,
            "delivered distinct orders / all distinct orders",
            "Returning a percentage from 0 to 100 instead of a fraction from 0 to 1.",
        ),
        _case(
            "peak_delivered_month_order_count", orders, "order_lifecycle", "medium", "en",
            "For delivered orders, group distinct order_id by purchase calendar month. What is the highest monthly order count? Return that count as primary_value and include the monthly series for a line chart.",
            answers["peak_delivered_month_order_count"], 0,
            "max(monthly count_distinct(order_id))",
            "Counting item rows or using incomplete months outside the prepared 2017 fixture.",
            ["ecommerce.order_count"], ["line"],
        ),
        _case(
            "late_delivery_rate", orders, "order_lifecycle", "medium", "zh",
            "仅对 delivered 且实际送达日期和预计送达日期都不为空的订单，实际送达时间晚于预计送达时间的订单比例是多少？返回 0 到 1 之间的一个数字。",
            answers["late_delivery_rate"], 0.0001,
            "late delivered orders / delivered orders with both delivery dates",
            "Including missing delivery dates in the denominator.",
        ),
        _case(
            "median_delivery_days", orders, "order_lifecycle", "medium", "en",
            "Among delivered orders with an actual delivery timestamp, what is the median elapsed time in days from order_purchase_timestamp to order_delivered_customer_date? Use exact timestamp differences and return one number.",
            answers["median_delivery_days"], 0.001,
            "median((delivered_at - purchased_at).total_seconds / 86400)",
            "Using date-only differences or the mean instead of the median.",
        ),
        _case(
            "delivered_payment_gmv", orders_payments, "payments", "medium", "zh",
            "将订单表与支付表按 order_id 关联，仅保留 delivered 订单。以 payment_value 之和定义本题 GMV，GMV 是多少？返回一个金额数字。",
            answers["delivered_payment_gmv"], 0.01,
            "sum(payment_value for delivered orders)",
            "Joining payments to item rows and multiplying payment values.", ["ecommerce.gmv"],
        ),
        _case(
            "delivered_aov", orders_payments, "payments", "medium", "en",
            "For delivered orders with payment records, define AOV as total payment_value divided by the distinct number of paid delivered order_id values. What is the AOV? Return one number.",
            answers["delivered_aov"], 0.01,
            "sum(payment_value) / count_distinct(paid delivered order_id)",
            "Averaging payment rows instead of aggregating payments to order grain.", ["ecommerce.aov"],
        ),
        _case(
            "credit_card_payment_value_share", orders_payments, "payments", "medium", "zh",
            "在 delivered 订单的全部 payment_value 中，payment_type 为 credit_card 的金额占比是多少？返回 0 到 1 之间的一个数字。",
            answers["credit_card_payment_value_share"], 0.0001,
            "credit-card payment value / all payment value for delivered orders",
            "Using payment-row count share instead of payment-value share.",
        ),
        _case(
            "multi_payment_order_rate", orders_payments, "payments", "hard", "en",
            "Among delivered orders that have at least one payment row, what fraction have more than one payment row? Aggregate payment rows by order_id first and return a number between 0 and 1.",
            answers["multi_payment_order_rate"], 0.0001,
            "orders with payment row count > 1 / delivered orders with payments",
            "Using payment_sequential values or payment-row share as the denominator.",
        ),
        _case(
            "sp_delivered_payment_gmv", orders_payments, "payments", "medium", "zh",
            "仅统计 customer_state 为 SP 且状态为 delivered 的订单，先按订单汇总 payment_value，再计算支付 GMV。结果是多少？返回一个金额数字，并附上各州 GMV 用于柱状图。",
            answers["sp_delivered_payment_gmv"], 0.01,
            "sum(order-level payment_value for delivered SP orders)",
            "Duplicating payment values or filtering state after an unsafe join.", ["ecommerce.gmv"], ["bar"],
        ),
        _case(
            "delivered_item_revenue", orders_items, "merchandising", "medium", "en",
            "For delivered orders, what is the total merchandise value defined strictly as the sum of item price, excluding freight? Return one number.",
            answers["delivered_item_revenue"], 0.01,
            "sum(item price for delivered orders)",
            "Including freight or counting non-delivered orders.",
        ),
        _case(
            "freight_share_of_item_billed_value", orders_items, "merchandising", "medium", "zh",
            "对 delivered 订单明细，以 sum(freight_value) / (sum(price) + sum(freight_value)) 计算运费占商品加运费总额的比例。返回 0 到 1 之间的一个数字。",
            answers["freight_share_of_item_billed_value"], 0.0001,
            "sum(freight) / (sum(item price) + sum(freight))",
            "Averaging row-level freight percentages instead of using ratio of sums.",
        ),
        _case(
            "top_category_item_revenue", item_products, "merchandising", "hard", "en",
            "Join delivered order items to products on product_id, group by product_category_name_english, and sum item price. What is the highest category revenue? Return that revenue as primary_value and include the category ranking for a bar chart.",
            answers["top_category_item_revenue"], 0.01,
            "max(category sum(item price))",
            "Joining on the wrong key, including freight, or returning the category label instead of its value.",
            None, ["bar"],
        ),
        _case(
            "top_category_item_count", item_products, "merchandising", "hard", "zh",
            "将 delivered 订单明细与商品表按 product_id 关联，按 product_category_name_english 分组。销量最高品类的商品明细行数是多少？返回最高行数，不要返回品类名称。",
            answers["top_category_item_count"], 0,
            "max(category count(order-item rows))",
            "Counting distinct orders or products instead of sold item rows.",
        ),
        _case(
            "top_seller_item_revenue", orders_items, "merchandising", "hard", "en",
            "For delivered order items, group by seller_id and sum item price. What is the highest revenue achieved by any one seller? Return only that highest revenue value.",
            answers["top_seller_item_revenue"], 0.01,
            "max(seller sum(item price))",
            "Returning the seller ID, using freight, or failing to filter delivered orders.",
        ),
        _case(
            "multi_item_order_rate", orders_items, "merchandising", "hard", "zh",
            "在至少有一条商品明细的 delivered 订单中，包含多于一条 order item 的订单比例是多少？先按 order_id 统计明细行数，返回 0 到 1 之间的数字。",
            answers["multi_item_order_rate"], 0.0001,
            "delivered orders with item row count > 1 / delivered orders with items",
            "Using the share of item rows belonging to multi-item orders.",
        ),
        _case(
            "repeat_buyer_rate", orders, "customer_experience", "hard", "en",
            "Within the prepared 2017 data, among customer_unique_id values with at least one delivered order, what fraction placed more than one distinct delivered order? Return a number between 0 and 1.",
            answers["repeat_buyer_rate"], 0.0001,
            "customers with >1 distinct delivered order / delivered purchasing customers",
            "Using customer_id, which is order-scoped in Olist, instead of customer_unique_id.",
            ["ecommerce.repeat_purchase_rate"],
        ),
        _case(
            "delivered_average_review_score", order_reviews, "customer_experience", "medium", "zh",
            "对 delivered 订单，若同一 order_id 有多条评价，先计算该订单的平均 review_score，再计算所有有评价订单的平均分。结果是多少？",
            answers["delivered_average_review_score"], 0.001,
            "mean(order-level mean review_score for delivered orders)",
            "Averaging raw review rows without resolving duplicate reviews per order.",
        ),
        _case(
            "late_delivery_average_review_score", order_reviews, "customer_experience", "hard", "en",
            "For delivered orders with both actual and estimated delivery dates, mark an order late when actual delivery is after the estimate. After averaging duplicate reviews per order, what is the average review score for late orders? Return one number and include the on-time versus late comparison for a bar chart.",
            answers["late_delivery_average_review_score"], 0.001,
            "mean(order-level review score where actual delivery > estimate)",
            "Comparing the wrong timestamps or allowing duplicate review rows to reweight orders.",
            None, ["bar"],
        ),
        _case(
            "on_time_minus_late_review_gap", order_reviews, "customer_experience", "hard", "zh",
            "按订单先汇总评价分数，并按实际送达是否晚于预计送达分组。准时订单平均评分减去延迟订单平均评分等于多少？返回一个数字。",
            answers["on_time_minus_late_review_gap"], 0.001,
            "mean(on-time order review) - mean(late order review)",
            "Reversing the subtraction or using unaggregated duplicate reviews.",
        ),
        _case(
            "missing_review_comment_rate", order_reviews, "customer_experience", "medium", "en",
            "Among review rows linked to delivered orders, what fraction do not have a review comment? Use has_review_comment and return a number between 0 and 1.",
            answers["missing_review_comment_rate"], 0.0001,
            "1 - mean(has_review_comment) for delivered-order reviews",
            "Using missing review titles, or counting orders without any review row.",
        ),
        _case(
            "raw_join_payment_inflation_rate", all_transactions, "join_grain_integrity", "hard", "zh",
            "仅对 delivered 订单：先计算支付表 payment_value 的正确总和；再将订单明细表与支付表直接按 order_id 做原始多对多连接并计算 payment_value 总和。原始连接结果相对正确结果的膨胀比例是多少？返回 (错误总和/正确总和)-1。",
            answers["raw_join_payment_inflation_rate"], 0.0001,
            "naive joined payment sum / true payment sum - 1",
            "Failing to recognize the many-to-many fanout between item and payment rows.",
        ),
        _case(
            "raw_join_item_revenue_inflation_rate", all_transactions, "join_grain_integrity", "hard", "en",
            "For delivered orders, compare the true sum of item price with the sum of price after raw-joining order items to payments on order_id. What is the inflation rate, defined as joined sum / true sum - 1? Return one number.",
            answers["raw_join_item_revenue_inflation_rate"], 0.0001,
            "naive joined item-price sum / true item-price sum - 1",
            "Ignoring payment multiplicity when joining at raw row grain.",
        ),
        _case(
            "payment_vs_items_reconciliation_gap_rate", all_transactions, "join_grain_integrity", "hard", "zh",
            "仅对 delivered 订单，分别在原表粒度计算支付总额 sum(payment_value) 与商品加运费总额 sum(price)+sum(freight_value)，不要先直接连接两张事实表。两者绝对差额占支付总额的比例是多少？返回 0 到 1 之间的数字。",
            answers["payment_vs_items_reconciliation_gap_rate"], 0.0001,
            "abs(payment total - item price and freight total) / payment total",
            "Creating fanout by joining raw fact tables before aggregation.",
        ),
    ]


def prepare(
    source_dir: Path,
    output_dir: Path,
    cases_path: Path,
    target_orders: int = DEFAULT_TARGET_ORDERS,
) -> Dict[str, Any]:
    missing = [name for name in SOURCE_FILES.values() if not (source_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing Olist source files: {', '.join(missing)}")

    customers = pd.read_csv(source_dir / SOURCE_FILES["customers"], dtype={"customer_zip_code_prefix": str})
    orders = pd.read_csv(source_dir / SOURCE_FILES["orders"])
    items = pd.read_csv(source_dir / SOURCE_FILES["items"])
    payments = pd.read_csv(source_dir / SOURCE_FILES["payments"])
    reviews = pd.read_csv(source_dir / SOURCE_FILES["reviews"])
    products = pd.read_csv(source_dir / SOURCE_FILES["products"])
    translations = pd.read_csv(source_dir / SOURCE_FILES["translations"])

    purchase_time = pd.to_datetime(orders["order_purchase_timestamp"])
    orders = orders.loc[purchase_time.dt.year.eq(2017)].copy()
    orders = orders.merge(
        customers[["customer_id", "customer_unique_id", "customer_city", "customer_state"]],
        on="customer_id",
        how="left",
        validate="one_to_one",
    ).sort_values("order_purchase_timestamp")
    orders = orders[[
        "order_id", "customer_id", "customer_unique_id", "customer_city", "customer_state",
        "order_status", "order_purchase_timestamp", "order_approved_at",
        "order_delivered_customer_date", "order_estimated_delivery_date",
    ]]
    orders = _sample_customers_with_complete_order_history(orders, target_orders)
    order_ids = set(orders["order_id"])

    items = items.loc[items["order_id"].isin(order_ids)].copy().sort_values(["order_id", "order_item_id"])
    payments = payments.loc[payments["order_id"].isin(order_ids)].copy().sort_values(
        ["order_id", "payment_sequential"]
    )
    reviews = reviews.loc[reviews["order_id"].isin(order_ids)].copy()
    reviews["has_review_comment"] = reviews["review_comment_message"].notna()
    reviews = reviews[[
        "review_id", "order_id", "review_score", "has_review_comment",
        "review_creation_date", "review_answer_timestamp",
    ]].sort_values(["order_id", "review_creation_date"])

    products = products.merge(
        translations,
        on="product_category_name",
        how="left",
        validate="many_to_one",
    )
    used_product_ids = set(items["product_id"])
    products = products.loc[products["product_id"].isin(used_product_ids), [
        "product_id", "product_category_name", "product_category_name_english",
        "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm",
    ]].sort_values("product_id")

    output_dir.mkdir(parents=True, exist_ok=True)
    tables = {
        "olist_orders_2017.csv": orders,
        "olist_order_items_2017.csv": items,
        "olist_order_payments_2017.csv": payments,
        "olist_order_reviews_2017.csv": reviews,
        "olist_products_2017.csv": products,
    }
    for filename, dataframe in tables.items():
        dataframe.to_csv(output_dir / filename, index=False)

    answers = calculate_reference_answers(output_dir)
    config = {
        "benchmark_name": "datasays_olist_business_analytics_v1",
        "version": "1.1.0",
        "description": (
            "A 24-case bilingual business-analytics benchmark adapted from the public Olist "
            "Brazilian ecommerce dataset, with deterministic numeric answers and explicit grain rules."
        ),
        "description_zh": (
            "基于 Olist 巴西电商公开数据改编的 24 题中英双语经营分析 Benchmark，"
            "包含确定性数值答案和明确的数据粒度规则。"
        ),
        "source": {
            "name": "Brazilian E-Commerce Public Dataset by Olist",
            "url": "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce",
            "license": "CC BY-NC-SA 4.0",
            "prepared_scope": (
                f"Deterministic customer-level sample of {len(orders):,} orders "
                "purchased during calendar year 2017"
            ),
            "prepared_scope_zh": f"2017 自然年内下单的 {len(orders):,} 笔客户级确定性抽样订单及关联记录",
            "sampling": {
                "target_orders": target_orders,
                "actual_orders": len(orders),
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
        "defaults": {
            "prompt_style": "zero",
            "tolerance": 0.001,
            "allow_legacy_text_scoring": False,
        },
        "cases": _build_cases(answers),
    }
    cases_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "cases": len(config["cases"]),
        "tables": {name: len(frame) for name, frame in tables.items()},
        "output_dir": str(output_dir),
        "cases_path": str(cases_path),
    }


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    default_source = Path(os.getenv("OLIST_SOURCE_DIR", "~/Downloads/archive")).expanduser()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=default_source)
    parser.add_argument("--output-dir", type=Path, default=script_dir / "data" / "olist")
    parser.add_argument("--cases", type=Path, default=script_dir / "benchmark_cases.json")
    parser.add_argument(
        "--target-orders",
        type=int,
        default=DEFAULT_TARGET_ORDERS,
        help="Approximate order target; complete order history is retained for selected customers.",
    )
    args = parser.parse_args()
    summary = prepare(
        args.source_dir.expanduser(),
        args.output_dir,
        args.cases,
        target_orders=args.target_orders,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
