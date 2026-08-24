"""Deterministic reference calculations for the Olist 2017 benchmark."""

from pathlib import Path
from typing import Dict

import pandas as pd


def calculate_reference_answers(data_dir: Path) -> Dict[str, float]:
    """Recompute every numeric answer from the prepared benchmark fixtures."""
    orders = pd.read_csv(
        data_dir / "olist_orders_2017.csv",
        parse_dates=[
            "order_purchase_timestamp",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
    )
    items = pd.read_csv(data_dir / "olist_order_items_2017.csv")
    payments = pd.read_csv(data_dir / "olist_order_payments_2017.csv")
    reviews = pd.read_csv(data_dir / "olist_order_reviews_2017.csv")
    products = pd.read_csv(data_dir / "olist_products_2017.csv")

    delivered = orders.loc[orders["order_status"].eq("delivered")].copy()
    delivered_ids = set(delivered["order_id"])
    delivered_items = items.loc[items["order_id"].isin(delivered_ids)].copy()
    delivered_payments = payments.loc[payments["order_id"].isin(delivered_ids)].copy()
    delivered_reviews = reviews.loc[reviews["order_id"].isin(delivered_ids)].copy()

    delivered["purchase_month"] = delivered["order_purchase_timestamp"].dt.to_period("M").astype(str)
    monthly_orders = delivered.groupby("purchase_month")["order_id"].nunique()

    dated_deliveries = delivered.dropna(
        subset=["order_delivered_customer_date", "order_estimated_delivery_date"]
    ).copy()
    dated_deliveries["is_late"] = (
        dated_deliveries["order_delivered_customer_date"]
        > dated_deliveries["order_estimated_delivery_date"]
    )
    dated_deliveries["delivery_days"] = (
        dated_deliveries["order_delivered_customer_date"]
        - dated_deliveries["order_purchase_timestamp"]
    ).dt.total_seconds() / 86400

    payment_by_order = delivered_payments.groupby("order_id", as_index=False).agg(
        paid_amount=("payment_value", "sum"),
        payment_rows=("payment_sequential", "size"),
    )
    paid_delivered_orders = delivered.merge(payment_by_order, on="order_id", how="inner")

    item_by_order = delivered_items.groupby("order_id", as_index=False).agg(
        item_revenue=("price", "sum"),
        freight_value=("freight_value", "sum"),
        item_rows=("order_item_id", "size"),
    )

    item_products = delivered_items.merge(
        products[["product_id", "product_category_name_english"]],
        on="product_id",
        how="left",
        validate="many_to_one",
    )
    category_summary = item_products.groupby(
        "product_category_name_english", dropna=False
    ).agg(item_revenue=("price", "sum"), item_count=("order_item_id", "size"))
    seller_revenue = delivered_items.groupby("seller_id")["price"].sum()

    customer_frequency = delivered.groupby("customer_unique_id")["order_id"].nunique()

    review_by_order = delivered_reviews.groupby("order_id", as_index=False).agg(
        review_score=("review_score", "mean")
    )
    delivery_reviews = dated_deliveries[["order_id", "is_late"]].merge(
        review_by_order,
        on="order_id",
        how="inner",
        validate="one_to_one",
    )
    review_by_lateness = delivery_reviews.groupby("is_late")["review_score"].mean()

    naive_join = delivered_items.merge(delivered_payments, on="order_id", how="inner")
    true_payment_total = delivered_payments["payment_value"].sum()
    true_item_total = delivered_items["price"].sum()
    item_plus_freight = delivered_items["price"].sum() + delivered_items["freight_value"].sum()

    answers = {
        "orders_total_2017": float(len(orders)),
        "delivered_order_rate": float(orders["order_status"].eq("delivered").mean()),
        "peak_delivered_month_order_count": float(monthly_orders.max()),
        "late_delivery_rate": float(dated_deliveries["is_late"].mean()),
        "median_delivery_days": float(dated_deliveries["delivery_days"].median()),
        "delivered_payment_gmv": float(true_payment_total),
        "delivered_aov": float(true_payment_total / paid_delivered_orders["order_id"].nunique()),
        "credit_card_payment_value_share": float(
            delivered_payments.loc[
                delivered_payments["payment_type"].eq("credit_card"), "payment_value"
            ].sum()
            / true_payment_total
        ),
        "multi_payment_order_rate": float(
            payment_by_order["payment_rows"].gt(1).mean()
        ),
        "sp_delivered_payment_gmv": float(
            paid_delivered_orders.loc[
                paid_delivered_orders["customer_state"].eq("SP"), "paid_amount"
            ].sum()
        ),
        "delivered_item_revenue": float(true_item_total),
        "freight_share_of_item_billed_value": float(
            delivered_items["freight_value"].sum() / item_plus_freight
        ),
        "top_category_item_revenue": float(category_summary["item_revenue"].max()),
        "top_category_item_count": float(category_summary["item_count"].max()),
        "top_seller_item_revenue": float(seller_revenue.max()),
        "multi_item_order_rate": float(item_by_order["item_rows"].gt(1).mean()),
        "repeat_buyer_rate": float(customer_frequency.gt(1).mean()),
        "delivered_average_review_score": float(review_by_order["review_score"].mean()),
        "late_delivery_average_review_score": float(review_by_lateness.loc[True]),
        "on_time_minus_late_review_gap": float(
            review_by_lateness.loc[False] - review_by_lateness.loc[True]
        ),
        "missing_review_comment_rate": float(
            1 - delivered_reviews["has_review_comment"].mean()
        ),
        "raw_join_payment_inflation_rate": float(
            naive_join["payment_value"].sum() / true_payment_total - 1
        ),
        "raw_join_item_revenue_inflation_rate": float(
            naive_join["price"].sum() / true_item_total - 1
        ),
        "payment_vs_items_reconciliation_gap_rate": float(
            abs(true_payment_total - item_plus_freight) / true_payment_total
        ),
    }
    return answers
