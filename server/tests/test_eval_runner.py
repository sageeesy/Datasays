"""Unit tests for structured benchmark scoring."""

import inspect
import tempfile
import unittest
from pathlib import Path

from evals.run_business_eval import run_business_eval
from evals.run_eval import (
    _delete_local_file,
    _expectation_passed,
    _numeric_candidates,
    _score_case,
    _stage_file_locally,
    run_eval,
)


class EvalRunnerTests(unittest.TestCase):
    def test_public_runners_and_local_helpers_are_async(self) -> None:
        self.assertTrue(inspect.iscoroutinefunction(_stage_file_locally))
        self.assertTrue(inspect.iscoroutinefunction(_delete_local_file))
        self.assertTrue(inspect.iscoroutinefunction(run_eval))
        self.assertTrue(inspect.iscoroutinefunction(run_business_eval))

    def test_structured_primary_value_is_scored(self) -> None:
        response = {
            "sandboxResponse": {
                "output": {"analysis_result": {"primary_value": 159.41}},
                "metadata": {},
            }
        }
        score = _score_case(
            response,
            {"expected_value": 159.4, "tolerance": 0.02},
            default_tolerance=0.001,
            allow_legacy_text=False,
        )
        self.assertTrue(score["passed"])
        self.assertAlmostEqual(score["absolute_error"], 0.01)

    def test_prose_numbers_do_not_score_when_legacy_mode_is_disabled(self) -> None:
        response = {
            "sandboxResponse": {
                "content": "The question mentions 2017 and the result is unavailable.",
                "output": {},
                "metadata": {},
            }
        }
        self.assertEqual(_numeric_candidates(response, allow_legacy_text=False), [])
        self.assertEqual(_numeric_candidates(response, allow_legacy_text=True), [2017.0])

    def test_optional_expectations_use_subset_matching(self) -> None:
        self.assertIsNone(_expectation_passed([], ["bar"]))
        self.assertTrue(_expectation_passed(["bar"], ["table", "bar"]))
        self.assertFalse(_expectation_passed(["line"], ["bar"]))


class AsyncEvalHelperTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_stage_and_delete_work_inside_active_event_loop(self) -> None:
        from app.services.file_service import load_metadata

        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "active-loop.csv"
            fixture.write_text("group,value\nA,1\nB,2\n", encoding="utf-8")
            file_id = await _stage_file_locally(fixture)
            try:
                metadata = await load_metadata(file_id)
                self.assertIsNotNone(metadata)
                self.assertEqual(metadata["rows"], 2)
                self.assertEqual(metadata["originalName"], fixture.name)
            finally:
                await _delete_local_file(file_id)

            self.assertIsNone(await load_metadata(file_id))


if __name__ == "__main__":
    unittest.main()
