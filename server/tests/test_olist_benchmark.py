"""Deterministic integrity checks for the Olist benchmark fixtures."""

import json
import unittest
from pathlib import Path

import pandas as pd

from evals.olist_reference import calculate_reference_answers
from app.services.metric_service import retrieve_metric_definitions


class OlistBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server_dir = Path(__file__).resolve().parents[1]
        cls.cases_path = cls.server_dir / "evals" / "benchmark_cases.json"
        cls.data_dir = cls.server_dir / "evals" / "data" / "olist"
        cls.config = json.loads(cls.cases_path.read_text(encoding="utf-8"))

    def test_contains_24_unique_bilingual_cases(self) -> None:
        cases = self.config["cases"]
        self.assertEqual(len(cases), 24)
        self.assertEqual(len({case["id"] for case in cases}), 24)
        self.assertEqual(sum(case["language"] == "zh" for case in cases), 12)
        self.assertEqual(sum(case["language"] == "en" for case in cases), 12)

    def test_all_dataset_paths_exist(self) -> None:
        for dataset in self.config["datasets"].values():
            self.assertTrue((self.cases_path.parent / dataset["path"]).is_file())

    def test_sample_size_and_foreign_keys_are_complete(self) -> None:
        orders = pd.read_csv(self.data_dir / "olist_orders_2017.csv", usecols=["order_id"])
        items = pd.read_csv(
            self.data_dir / "olist_order_items_2017.csv",
            usecols=["order_id", "product_id"],
        )
        payments = pd.read_csv(
            self.data_dir / "olist_order_payments_2017.csv",
            usecols=["order_id"],
        )
        reviews = pd.read_csv(
            self.data_dir / "olist_order_reviews_2017.csv",
            usecols=["order_id"],
        )
        products = pd.read_csv(
            self.data_dir / "olist_products_2017.csv",
            usecols=["product_id"],
        )

        order_ids = set(orders["order_id"])
        self.assertEqual(len(orders), 15_000)
        self.assertTrue(set(items["order_id"]).issubset(order_ids))
        self.assertTrue(set(payments["order_id"]).issubset(order_ids))
        self.assertTrue(set(reviews["order_id"]).issubset(order_ids))
        self.assertEqual(set(products["product_id"]), set(items["product_id"]))

    def test_expected_values_match_reference_calculations(self) -> None:
        expected = calculate_reference_answers(self.data_dir)
        cases = {case["id"]: case for case in self.config["cases"]}
        self.assertEqual(set(cases), set(expected))
        for case_id, reference_value in expected.items():
            tolerance = float(cases[case_id].get("tolerance", 0.001))
            self.assertAlmostEqual(
                float(cases[case_id]["expected_value"]),
                reference_value,
                delta=max(tolerance / 10, 1e-12),
                msg=case_id,
            )

    def test_olist_columns_bind_to_ecommerce_metric_concepts(self) -> None:
        profiles = [{
            "file_name": "olist_orders_2017.csv",
            "columns": [
                {"name": "order_id"},
                {"name": "customer_unique_id"},
                {"name": "order_purchase_timestamp"},
                {"name": "customer_state"},
            ],
        }, {
            "file_name": "olist_order_payments_2017.csv",
            "columns": [{"name": "payment_value"}],
        }]
        aov = retrieve_metric_definitions("What is the AOV?", profiles)[0]
        repeat = retrieve_metric_definitions("计算复购率", profiles)[0]

        self.assertEqual(aov.metric.id, "ecommerce.aov")
        self.assertFalse(aov.missing_concepts)
        self.assertEqual(repeat.metric.id, "ecommerce.repeat_purchase_rate")
        self.assertFalse(repeat.missing_concepts)


if __name__ == "__main__":
    unittest.main()
