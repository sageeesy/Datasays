#!/usr/bin/env python3
"""Generate deterministic datasets and independent references for capability probes."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "capability_probe"
REFERENCE_PATH = ROOT / "capability_probe_references.json"
SEED = 20260827


def _write_csv(dataframe: pd.DataFrame, name: str) -> Path:
    path = DATA_DIR / name
    dataframe.to_csv(path, index=False)
    return path


def _core_data() -> pd.DataFrame:
    regions = ["North", "South", "East", "West"]
    categories = ["Office", "Home", "Tech"]
    rows = []
    for index in range(1, 241):
        region = regions[(index - 1) % len(regions)]
        category = categories[(index * 2) % len(categories)]
        product_id = f"P{((index - 1) % 12) + 1:02d}"
        member = "yes" if index % 3 != 0 else "no"
        quantity = 1 + index % 5
        discount = [0.0, 0.05, 0.10, 0.20][index % 4]
        region_effect = {"North": 16, "South": -4, "East": 28, "West": 8}[region]
        category_effect = {"Office": 5, "Home": 14, "Tech": 32}[category]
        sales = round(35 + region_effect + category_effect + (index % 17) * 3.4 + quantity * 4.2 - discount * 20, 2)
        rows.append({
            "transaction_id": f"T{index:04d}",
            "region": region,
            "category": category,
            "product_id": product_id,
            "member": member,
            "quantity": quantity,
            "discount": discount,
            "sales": sales,
        })
    return pd.DataFrame(rows)


def _statistical_data() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    size = 240
    group = np.where(np.arange(size) < size // 2, "control", "treatment")
    x = rng.normal(0, 1, size)
    noise = rng.normal(0, 7.5, size)
    outcome = 50 + 3.5 * x + (group == "treatment") * 3.2 + noise
    return pd.DataFrame({
        "subject_id": [f"S{index:04d}" for index in range(1, size + 1)],
        "group": group,
        "x": np.round(x, 6),
        "outcome": np.round(outcome, 6),
    })


def _classification_data() -> pd.DataFrame:
    rng = np.random.default_rng(SEED + 2)
    features = rng.normal(0, 1, (420, 6))
    logits = 1.45 * features[:, 0] - 1.1 * features[:, 1] + 0.85 * features[:, 2] + 0.5 * features[:, 3] - 0.2
    probabilities = 1 / (1 + np.exp(-logits))
    target = rng.binomial(1, probabilities)
    frame = pd.DataFrame(np.round(features, 6), columns=[f"feature_{index}" for index in range(1, 7)])
    frame.insert(0, "record_id", [f"C{index:04d}" for index in range(1, len(frame) + 1)])
    frame["target"] = target
    return frame


def _regression_data() -> pd.DataFrame:
    rng = np.random.default_rng(SEED + 1)
    size = 360
    x1 = rng.normal(10, 2.5, size)
    x2 = rng.uniform(-3, 5, size)
    x3 = rng.normal(0, 1.2, size)
    noise = rng.normal(0, 3.0, size)
    target = 12 + 2.8 * x1 - 1.6 * x2 + 4.2 * x3 + noise
    return pd.DataFrame({
        "record_id": [f"R{index:04d}" for index in range(1, size + 1)],
        "x1": np.round(x1, 6),
        "x2": np.round(x2, 6),
        "x3": np.round(x3, 6),
        "target": np.round(target, 6),
    })


def _behavior_data() -> pd.DataFrame:
    rows = []
    sequence = 0
    cohort_starts = [pd.Timestamp("2025-01-01"), pd.Timestamp("2025-02-01"), pd.Timestamp("2025-03-01")]
    for user_number in range(1, 121):
        cohort_index = (user_number - 1) // 40
        cohort_start = cohort_starts[cohort_index]
        signup_time = cohort_start + pd.Timedelta(days=(user_number - 1) % 20, hours=user_number % 7)
        events = [("signup", signup_time), ("view", signup_time + pd.Timedelta(hours=1))]
        if user_number % 5 != 0:
            events.append(("add_to_cart", signup_time + pd.Timedelta(hours=2)))
            if user_number % 3 != 0:
                events.append(("purchase", signup_time + pd.Timedelta(hours=3)))
        if user_number % (cohort_index + 2) == 0:
            events.append(("active", signup_time + pd.Timedelta(days=7, hours=2)))
        if user_number % 11 == 0:
            events.append(("active", signup_time + pd.Timedelta(days=10)))
        for event, event_time in events:
            sequence += 1
            rows.append({
                "event_id": f"E{sequence:05d}",
                "user_id": f"U{user_number:03d}",
                "event": event,
                "event_time": event_time.isoformat(),
            })
    return pd.DataFrame(rows)


def _core_references(frame: pd.DataFrame) -> dict:
    sales = frame["sales"]
    member_east = frame[(frame["member"] == "yes") & (frame["region"] == "East")]
    grouped = frame.groupby("region", as_index=False).agg(
        transaction_count=("transaction_id", "nunique"),
        total_sales=("sales", "sum"),
        average_sales=("sales", "mean"),
    )
    product = frame.groupby("product_id", as_index=False)["sales"].sum().rename(columns={"sales": "total_sales"})
    top = product.sort_values(["total_sales", "product_id"], ascending=[False, True]).head(3)
    bottom = product.sort_values(["total_sales", "product_id"], ascending=[True, True]).head(3)
    q1, median, q3 = sales.quantile([0.25, 0.5, 0.75])
    iqr = q3 - q1
    upper_fence = q3 + 1.5 * iqr
    return {
        "core_descriptive": {
            "count": int(sales.count()), "mean": float(sales.mean()), "median": float(sales.median()),
            "min": float(sales.min()), "max": float(sales.max()), "std": float(sales.std(ddof=1)),
            "q1": float(q1), "q3": float(q3),
        },
        "core_filter_metric": {
            "count": int(len(member_east)), "mean_sales": float(member_east["sales"].mean()),
            "row_share": float(len(member_east) / len(frame)),
        },
        "core_groupby": {
            "groups": grouped.to_dict(orient="records"),
            "highest_average_region": str(grouped.loc[grouped["average_sales"].idxmax(), "region"]),
            "lowest_average_region": str(grouped.loc[grouped["average_sales"].idxmin(), "region"]),
        },
        "core_ranking": {"top3": top.to_dict(orient="records"), "bottom3": bottom.to_dict(orient="records")},
        "core_distribution": {
            "q1": float(q1), "median": float(median), "q3": float(q3), "p90": float(sales.quantile(0.90)),
            "iqr": float(iqr), "upper_fence": float(upper_fence),
            "high_value_count": int((sales > upper_fence).sum()),
        },
    }


def _statistical_references(frame: pd.DataFrame) -> dict:
    control = frame.loc[frame["group"] == "control", "outcome"].to_numpy()
    treatment = frame.loc[frame["group"] == "treatment", "outcome"].to_numpy()
    test = stats.ttest_ind(treatment, control, equal_var=False)
    difference = treatment.mean() - control.mean()
    variance_term = treatment.var(ddof=1) / len(treatment) + control.var(ddof=1) / len(control)
    standard_error = np.sqrt(variance_term)
    df = variance_term ** 2 / (
        (treatment.var(ddof=1) / len(treatment)) ** 2 / (len(treatment) - 1)
        + (control.var(ddof=1) / len(control)) ** 2 / (len(control) - 1)
    )
    critical = stats.t.ppf(0.975, df)
    pooled_sd = np.sqrt(
        ((len(treatment) - 1) * treatment.var(ddof=1) + (len(control) - 1) * control.var(ddof=1))
        / (len(treatment) + len(control) - 2)
    )
    correlation = stats.pearsonr(frame["x"], frame["outcome"])
    return {
        "probe_mean_ci": {
            "control_mean": float(control.mean()), "treatment_mean": float(treatment.mean()),
            "mean_difference": float(difference), "ci_low": float(difference - critical * standard_error),
            "ci_high": float(difference + critical * standard_error), "method": "Welch confidence interval",
        },
        "probe_hypothesis_effect": {
            "welch_t": float(test.statistic), "p_value": float(test.pvalue),
            "cohens_d": float(difference / pooled_sd), "direction": "treatment_higher" if difference > 0 else "control_higher",
        },
        "probe_correlation": {
            "pearson_r": float(correlation.statistic), "p_value": float(correlation.pvalue),
            "direction": "positive" if correlation.statistic > 0 else "negative",
        },
    }


def _classification_metrics(frame: pd.DataFrame, model) -> dict:
    features = [f"feature_{index}" for index in range(1, 7)]
    train_x, test_x, train_y, test_y = train_test_split(
        frame[features], frame["target"], test_size=0.30, random_state=42, stratify=frame["target"]
    )
    model.fit(train_x, train_y)
    predictions = model.predict(test_x)
    probabilities = model.predict_proba(test_x)[:, 1]
    return {
        "accuracy": float(accuracy_score(test_y, predictions)),
        "precision": float(precision_score(test_y, predictions)),
        "recall": float(recall_score(test_y, predictions)),
        "f1": float(f1_score(test_y, predictions)),
        "roc_auc": float(roc_auc_score(test_y, probabilities)),
        "test_rows": int(len(test_y)),
    }


def _predictive_references(classification: pd.DataFrame, regression: pd.DataFrame) -> dict:
    logistic = Pipeline([
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(C=1.0, max_iter=1000, solver="lbfgs", random_state=42)),
    ])
    forest = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
    features = ["x1", "x2", "x3"]
    train_x, test_x, train_y, test_y = train_test_split(
        regression[features], regression["target"], test_size=0.25, random_state=42
    )
    linear = LinearRegression().fit(train_x, train_y)
    predictions = linear.predict(test_x)
    return {
        "probe_logistic": _classification_metrics(classification, logistic),
        "probe_random_forest": _classification_metrics(classification, forest),
        "probe_linear_regression": {
            "r2": float(r2_score(test_y, predictions)),
            "mae": float(mean_absolute_error(test_y, predictions)),
            "rmse": float(mean_squared_error(test_y, predictions) ** 0.5),
            "intercept": float(linear.intercept_),
            "coef_x1": float(linear.coef_[0]), "coef_x2": float(linear.coef_[1]),
            "coef_x3": float(linear.coef_[2]), "test_rows": int(len(test_y)),
        },
    }


def _behavior_references(frame: pd.DataFrame) -> dict:
    frame = frame.copy()
    frame["event_time"] = pd.to_datetime(frame["event_time"])
    stage_counts = {}
    reached_previous = set(frame.loc[frame["event"] == "view", "user_id"])
    stage_counts["view"] = len(reached_previous)
    for stage in ("add_to_cart", "purchase"):
        current = set()
        for user_id in reached_previous:
            user_events = frame[frame["user_id"] == user_id].sort_values("event_time")
            prior_time = user_events.loc[user_events["event"].isin(["view", "add_to_cart"]), "event_time"].min()
            if ((user_events["event"] == stage) & (user_events["event_time"] > prior_time)).any():
                current.add(user_id)
        stage_counts[stage] = len(current)
        reached_previous = current

    signups = frame[frame["event"] == "signup"][["user_id", "event_time"]].rename(columns={"event_time": "signup_time"})
    active = frame[frame["event"] == "active"][["user_id", "event_time"]]
    joined = signups.merge(active, on="user_id", how="left")
    joined["retained_d7"] = (
        (joined["event_time"] >= joined["signup_time"] + pd.Timedelta(days=7))
        & (joined["event_time"] < joined["signup_time"] + pd.Timedelta(days=8))
    )
    joined["cohort_month"] = joined["signup_time"].dt.to_period("M").astype(str)
    retention = joined.groupby("cohort_month").agg(
        eligible_users=("user_id", "nunique"),
        retained_users=("retained_d7", "sum"),
    ).reset_index()
    retention["retention_rate"] = retention["retained_users"] / retention["eligible_users"]
    return {
        "probe_funnel": {
            **stage_counts,
            "view_to_cart_rate": stage_counts["add_to_cart"] / stage_counts["view"],
            "cart_to_purchase_rate": stage_counts["purchase"] / stage_counts["add_to_cart"],
            "view_to_purchase_rate": stage_counts["purchase"] / stage_counts["view"],
        },
        "probe_cohort_retention": {"cohorts": retention.to_dict(orient="records")},
    }


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    core = _core_data()
    statistical = _statistical_data()
    classification = _classification_data()
    regression = _regression_data()
    behavior = _behavior_data()
    paths = {
        "core": _write_csv(core, "core_retail.csv"),
        "statistical": _write_csv(statistical, "statistical_groups.csv"),
        "classification": _write_csv(classification, "classification.csv"),
        "regression": _write_csv(regression, "regression.csv"),
        "behavior": _write_csv(behavior, "behavior_events.csv"),
    }

    references = {
        "metadata": {
            "seed": SEED,
            "datasets": {key: str(path.relative_to(ROOT)) for key, path in paths.items()},
        },
        **_core_references(pd.read_csv(paths["core"])),
        **_statistical_references(pd.read_csv(paths["statistical"])),
        **_predictive_references(pd.read_csv(paths["classification"]), pd.read_csv(paths["regression"])),
        **_behavior_references(pd.read_csv(paths["behavior"])),
    }
    REFERENCE_PATH.write_text(json.dumps(references, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"datasets": len(paths), "references": len(references) - 1, "path": str(REFERENCE_PATH)}, indent=2))


if __name__ == "__main__":
    main()
