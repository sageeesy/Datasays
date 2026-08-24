"""Integrity checks for the Olist Business Analysis Suite v2."""

import json
import unittest
from collections import Counter
from pathlib import Path

from evals.prepare_olist_business_benchmark import build_config


class OlistBusinessBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server_dir = Path(__file__).resolve().parents[1]
        cls.cases_path = cls.server_dir / "evals" / "business_benchmark_cases.json"
        cls.config = json.loads(cls.cases_path.read_text(encoding="utf-8"))

    def test_contains_24_unique_capability_cases(self) -> None:
        cases = self.config["cases"]
        self.assertEqual(len(cases), 24)
        self.assertEqual(len({case["id"] for case in cases}), 24)
        self.assertEqual(
            Counter(case["category"] for case in cases),
            {
                "metric_execution": 6,
                "data_quality_grain": 4,
                "business_diagnosis": 5,
                "decision_support": 4,
                "clarification_boundary": 3,
                "multi_turn_memory": 2,
            },
        )

    def test_all_dataset_paths_exist(self) -> None:
        for dataset in self.config["datasets"].values():
            self.assertTrue((self.cases_path.parent / dataset["path"]).is_file())

    def test_committed_cases_match_deterministic_generator(self) -> None:
        self.assertEqual(self.config, build_config())

    def test_clarification_and_memory_cases_are_explicit(self) -> None:
        single_turn = [case for case in self.config["cases"] if "turns" not in case]
        clarification_cases = [
            case for case in single_turn if case["expected"].get("clarification")
        ]
        multi_turn = [case for case in self.config["cases"] if "turns" in case]

        self.assertEqual(len(clarification_cases), 2)
        self.assertEqual(len(multi_turn), 2)
        for case in multi_turn:
            self.assertEqual(len(case["turns"]), 2)
            self.assertTrue(case["turns"][1]["expected"]["memory_used"])


if __name__ == "__main__":
    unittest.main()
