"""Deterministic evidence for the Olist business-analysis benchmark."""

from pathlib import Path
from typing import Any, Dict

import pandas as pd


def calculate_business_reference(data_dir: Path) -> Dict[str, Any]:
    """Build reusable business facts from the committed Olist 2017 fixtures."""
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

    payment_by_order = delivered_payments.groupby("order_id", as_index=False).agg(
        payment_value=("payment_value", "sum"),
        payment_rows=("payment_sequential", "size"),
    )
    item_by_order = delivered_items.groupby("order_id", as_index=False).agg(
        item_value=("price", "sum"),
        freight_value=("freight_value", "sum"),
        item_rows=("order_item_id", "size"),
    )
    review_by_order = delivered_reviews.groupby("order_id", as_index=False).agg(
        review_score=("review_score", "mean"),
        review_rows=("review_id", "size"),
    )

    order_level = (
        delivered.merge(payment_by_order, on="order_id", how="left", validate="one_to_one")
        .merge(item_by_order, on="order_id", how="left", validate="one_to_one")
        .merge(review_by_order, on="order_id", how="left", validate="one_to_one")
    )
    order_level["purchase_month"] = order_level["order_purchase_timestamp"].dt.to_period("M").astype(str)
    order_level["is_late"] = (
        order_level["order_delivered_customer_date"].notna()
        & order_level["order_estimated_delivery_date"].notna()
        & (order_level["order_delivered_customer_date"] > order_level["order_estimated_delivery_date"])
    )

    monthly = order_level.groupby("purchase_month", as_index=False).agg(
        orders=("order_id", "nunique"),
        gmv=("payment_value", "sum"),
    )
    monthly["aov"] = monthly["gmv"] / monthly["orders"]
    monthly["gmv_mom"] = monthly["gmv"].pct_change()
    monthly["orders_mom"] = monthly["orders"].pct_change()
    monthly["aov_mom"] = monthly["aov"].pct_change()
    peak_month = monthly.sort_values(["gmv", "purchase_month"], ascending=[False, True]).iloc[0]
    decline_pool = monthly.loc[monthly["purchase_month"].between("2017-02", "2017-11")].dropna()
    decline_month = decline_pool.sort_values(["gmv_mom", "purchase_month"]).iloc[0]

    state_summary = order_level.groupby("customer_state", as_index=False).agg(
        orders=("order_id", "nunique"),
        gmv=("payment_value", "sum"),
        aov=("payment_value", "mean"),
        late_rate=("is_late", "mean"),
        review_score=("review_score", "mean"),
    )
    state_summary["gmv_share"] = state_summary["gmv"] / state_summary["gmv"].sum()
    state_rank = state_summary.sort_values(["gmv", "customer_state"], ascending=[False, True])
    top_state = state_rank.iloc[0]
    top3_state_share = float(state_rank.head(3)["gmv"].sum() / state_rank["gmv"].sum())
    state_delay = state_summary.loc[state_summary["orders"] >= 500].sort_values(
        ["late_rate", "orders"], ascending=[False, False]
    ).iloc[0]
    non_sp_growth = state_rank.loc[state_rank["customer_state"].ne("SP")].iloc[0]

    item_products = delivered_items.merge(
        products[["product_id", "product_category_name_english"]],
        on="product_id",
        how="left",
        validate="many_to_one",
    )
    category_order = item_products[["order_id", "product_category_name_english"]].drop_duplicates()
    category_order = category_order.merge(
        order_level[["order_id", "is_late", "review_score", "customer_state"]],
        on="order_id",
        how="left",
        validate="many_to_one",
    )
    category_finance = item_products.groupby("product_category_name_english", dropna=False).agg(
        item_revenue=("price", "sum"),
        freight=("freight_value", "sum"),
        item_rows=("order_item_id", "size"),
        orders=("order_id", "nunique"),
    )
    category_experience = category_order.groupby("product_category_name_english", dropna=False).agg(
        late_rate=("is_late", "mean"),
        review_score=("review_score", "mean"),
    )
    category_summary = category_finance.join(category_experience).reset_index()
    category_summary["revenue_share"] = category_summary["item_revenue"] / category_summary["item_revenue"].sum()
    category_rank = category_summary.sort_values(
        ["item_revenue", "product_category_name_english"], ascending=[False, True]
    )
    top_category = category_rank.iloc[0]
    top5_category_share = float(category_rank.head(5)["item_revenue"].sum() / category_rank["item_revenue"].sum())
    category_problem = category_summary.loc[category_summary["orders"] >= 500].sort_values(
        ["review_score", "item_revenue"], ascending=[True, False]
    ).iloc[0]

    sp_items = item_products.merge(
        order_level[["order_id", "customer_state"]], on="order_id", how="left", validate="many_to_one"
    )
    sp_category = (
        sp_items.loc[sp_items["customer_state"].eq(str(top_state["customer_state"]))]
        .groupby("product_category_name_english", as_index=False)["price"]
        .sum()
        .sort_values(["price", "product_category_name_english"], ascending=[False, True])
        .iloc[0]
    )

    seller_order = delivered_items[["order_id", "seller_id"]].drop_duplicates().merge(
        order_level[["order_id", "is_late", "review_score"]],
        on="order_id",
        how="left",
        validate="many_to_one",
    )
    seller_finance = delivered_items.groupby("seller_id", as_index=False).agg(
        revenue=("price", "sum"),
        orders=("order_id", "nunique"),
    )
    seller_experience = seller_order.groupby("seller_id", as_index=False).agg(
        late_rate=("is_late", "mean"),
        review_score=("review_score", "mean"),
    )
    seller_summary = seller_finance.merge(seller_experience, on="seller_id", how="left", validate="one_to_one")
    revenue_cutoff = seller_summary["revenue"].quantile(0.90)
    seller_risk = seller_summary.loc[
        seller_summary["revenue"].ge(revenue_cutoff) & seller_summary["orders"].ge(50)
    ].sort_values(["late_rate", "revenue"], ascending=[False, False]).iloc[0]

    customer_orders = order_level.groupby("customer_unique_id")["order_id"].nunique()
    repeat_customers = customer_orders.gt(1)
    customer_id_orders = order_level.groupby("customer_id")["order_id"].nunique()

    dated = order_level.dropna(
        subset=["order_delivered_customer_date", "order_estimated_delivery_date"]
    )
    review_lateness = dated.dropna(subset=["review_score"]).groupby("is_late")["review_score"].mean()
    late_count = int(dated["is_late"].sum())

    raw_review_mean = float(delivered_reviews["review_score"].mean())
    order_review_mean = float(review_by_order["review_score"].mean())
    duplicate_review_orders = int(review_by_order["review_rows"].gt(1).sum())
    reviewed_order_ids = set(review_by_order["order_id"])
    orders_without_review = int((~order_level["order_id"].isin(reviewed_order_ids)).sum())

    payment_mix = delivered_payments.groupby("payment_type")["payment_value"].sum().sort_values(ascending=False)
    naive_join = delivered_items.merge(delivered_payments, on="order_id", how="inner")
    true_payment = float(delivered_payments["payment_value"].sum())
    true_items = float(delivered_items["price"].sum())
    item_billed = float((delivered_items["price"] + delivered_items["freight_value"]).sum())

    return {
        "orders_total": int(orders["order_id"].nunique()),
        "delivered_orders": int(delivered["order_id"].nunique()),
        "delivered_rate": float(delivered["order_id"].nunique() / orders["order_id"].nunique()),
        "gmv": true_payment,
        "aov": float(true_payment / payment_by_order["order_id"].nunique()),
        "peak_month": str(peak_month["purchase_month"]),
        "peak_month_gmv": float(peak_month["gmv"]),
        "peak_month_orders": int(peak_month["orders"]),
        "largest_decline_month": str(decline_month["purchase_month"]),
        "largest_decline_gmv_mom": float(decline_month["gmv_mom"]),
        "largest_decline_orders_mom": float(decline_month["orders_mom"]),
        "largest_decline_aov_mom": float(decline_month["aov_mom"]),
        "top_state": str(top_state["customer_state"]),
        "top_state_gmv": float(top_state["gmv"]),
        "top_state_share": float(top_state["gmv_share"]),
        "top3_state_share": top3_state_share,
        "state_delay_hotspot": str(state_delay["customer_state"]),
        "state_delay_hotspot_rate": float(state_delay["late_rate"]),
        "state_delay_hotspot_orders": int(state_delay["orders"]),
        "state_delay_hotspot_review": float(state_delay["review_score"]),
        "non_sp_growth_state": str(non_sp_growth["customer_state"]),
        "non_sp_growth_gmv": float(non_sp_growth["gmv"]),
        "non_sp_growth_aov": float(non_sp_growth["aov"]),
        "top_category": str(top_category["product_category_name_english"]),
        "top_category_revenue": float(top_category["item_revenue"]),
        "top_category_share": float(top_category["revenue_share"]),
        "top5_category_share": top5_category_share,
        "category_problem": str(category_problem["product_category_name_english"]),
        "category_problem_revenue": float(category_problem["item_revenue"]),
        "category_problem_review": float(category_problem["review_score"]),
        "category_problem_late_rate": float(category_problem["late_rate"]),
        "top_state_category": str(sp_category["product_category_name_english"]),
        "top_state_category_revenue": float(sp_category["price"]),
        "seller_risk": str(seller_risk["seller_id"]),
        "seller_risk_revenue": float(seller_risk["revenue"]),
        "seller_risk_orders": int(seller_risk["orders"]),
        "seller_risk_late_rate": float(seller_risk["late_rate"]),
        "seller_risk_review": float(seller_risk["review_score"]),
        "repeat_buyer_rate": float(repeat_customers.mean()),
        "repeat_buyer_count": int(repeat_customers.sum()),
        "customer_id_repeat_rate": float(customer_id_orders.gt(1).mean()),
        "credit_card_share": float(payment_mix.get("credit_card", 0) / true_payment),
        "boleto_share": float(payment_mix.get("boleto", 0) / true_payment),
        "multi_payment_rate": float(payment_by_order["payment_rows"].gt(1).mean()),
        "late_delivery_rate": float(dated["is_late"].mean()),
        "late_delivery_count": late_count,
        "late_review_score": float(review_lateness.loc[True]),
        "on_time_review_score": float(review_lateness.loc[False]),
        "review_score_gap": float(review_lateness.loc[False] - review_lateness.loc[True]),
        "duplicate_review_orders": duplicate_review_orders,
        "raw_review_mean": raw_review_mean,
        "order_review_mean": order_review_mean,
        "review_grain_delta": float(raw_review_mean - order_review_mean),
        "orders_without_review": orders_without_review,
        "orders_without_review_rate": float(orders_without_review / len(order_level)),
        "missing_actual_delivery": int(order_level["order_delivered_customer_date"].isna().sum()),
        "missing_actual_delivery_rate": float(order_level["order_delivered_customer_date"].isna().mean()),
        "missing_review_comment_rate": float((~delivered_reviews["has_review_comment"].astype(bool)).mean()),
        "payment_join_inflation": float(naive_join["payment_value"].sum() / true_payment - 1),
        "item_join_inflation": float(naive_join["price"].sum() / true_items - 1),
        "reconciliation_gap_rate": float(abs(true_payment - item_billed) / true_payment),
    }
