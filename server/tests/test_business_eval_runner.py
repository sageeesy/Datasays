"""Unit tests for capability-oriented benchmark scoring."""

import unittest
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from evals.run_business_eval import _contains_term, _score_response, run_business_eval


def response(
    content: str = "",
    result=None,
    *,
    status: str = "success",
    clarification: bool = False,
    memory: bool = False,
):
    return {
        "sandboxResponse": {
            "status": status,
            "content": content,
            "output": {"analysis_result": result} if result else None,
            "metadata": {
                "analysis_result": result,
                "plan": {
                    "intent": "metric_diagnostic",
                    "metric_ids": ["ecommerce.gmv"],
                    "needs_clarification": clarification,
                },
                "memory": {"used": memory},
                "validation_report": {"passed": bool(result)},
            },
        }
    }


class BusinessEvalRunnerTests(unittest.TestCase):
    def test_notebook_uses_top_level_await_for_case_execution(self) -> None:
        notebook_path = Path(__file__).resolve().parents[1] / "evals" / "olist_business_v2_baseline.ipynb"
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        source = "\n".join(
            "".join(cell.get("source", []))
            for cell in notebook["cells"]
            if cell.get("cell_type") == "code"
        )
        self.assertIn("async def run_case", source)
        self.assertIn("await run_business_eval", source)
        self.assertIn("async def run_next_case", source)
        self.assertIn("current_report = await run_next_case()", source)

    def test_numeric_facts_only_score_from_structured_evidence(self) -> None:
        expectation = {
            "facts": [{"id": "gmv", "value": 100.0, "tolerance": 0.01}],
            "required_term_groups": [],
            "min_fact_recall": 1.0,
        }
        prose_only = _score_response(response("GMV 是 100。"), expectation)
        structured = _score_response(
            response(
                "GMV 是 100。",
                {"answer_type": "number", "primary_value": 100.0, "summary": "GMV", "rows": []},
            ),
            expectation,
        )
        self.assertEqual(prose_only["fact_recall"], 0)
        self.assertFalse(prose_only["passed"])
        self.assertTrue(structured["passed"])

    def test_business_term_groups_accept_synonyms(self) -> None:
        score = _score_response(
            response(
                "该差异只能说明关联，不能证明因果。",
                {"answer_type": "text", "summary": "观察性结论", "rows": []},
            ),
            {
                "facts": [],
                "required_term_groups": [["相关", "关联"], ["无法证明", "不能证明"]],
                "min_term_coverage": 1.0,
            },
        )
        self.assertEqual(score["term_coverage"], 1.0)
        self.assertTrue(score["passed"])

    def test_clarification_requires_plan_and_no_analysis_result(self) -> None:
        expectation = {
            "facts": [],
            "required_term_groups": [["成本"], ["缺少", "没有"]],
            "clarification": True,
            "clarification_terms": ["成本", "利润", "字段"],
            "min_term_coverage": 1.0,
        }
        score = _score_response(
            response("数据中缺少成本字段，无法计算利润。", clarification=True),
            expectation,
        )
        self.assertTrue(score["clarification_passed"])
        self.assertTrue(score["passed"])

    def test_memory_expectation_is_a_hard_gate(self) -> None:
        expectation = {
            "facts": [],
            "required_term_groups": [],
            "memory_used": True,
        }
        result = {"answer_type": "text", "summary": "follow-up", "rows": []}
        self.assertFalse(_score_response(response(result=result, memory=False), expectation)["passed"])
        self.assertTrue(_score_response(response(result=result, memory=True), expectation)["passed"])

    def test_short_ascii_terms_use_token_boundaries(self) -> None:
        self.assertTrue(_contains_term("Top state: SP", "SP"))
        self.assertFalse(_contains_term("The response is complete", "SP"))


class AsyncBusinessEvalRunnerTests(unittest.IsolatedAsyncioTestCase):
    @patch("evals.run_business_eval._in_process_query", new_callable=AsyncMock)
    async def test_runner_completes_inside_active_event_loop(self, query: AsyncMock) -> None:
        query.return_value = response(
            "当前数据缺少成本字段，无法计算利润或毛利。",
            clarification=True,
        )
        cases_path = Path(__file__).resolve().parents[1] / "evals" / "business_benchmark_cases.json"

        report = await run_business_eval(
            api_base="http://datasays.local",
            cases_path=cases_path,
            case_ids=["profit_metric_clarification"],
            model_override="test/model",
            local_files=True,
            in_process_api=True,
        )

        self.assertEqual(report["total_cases"], 1)
        self.assertEqual(report["passed"], 1)
        query.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
