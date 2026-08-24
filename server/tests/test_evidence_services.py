import json
import tempfile
import unittest
from pathlib import Path

from app.schemas.analysis import AnalysisPlan, AnalysisResult
from app.services.agent_service import _is_non_repairable_execution_error, _workflow_metadata
from app.services.plan_service import _apply_planning_guards
from app.services.code_service import _build_code_generation_prompt, _extract_code_and_reasoning, _message_text, contains_image_generation
from app.services.metric_service import compact_metric_match, retrieve_metric_definitions
from app.services.profile_service import build_dataset_profile
from app.services.sandbox_service import RESULT_MARKER, _extract_structured_result
from app.services.skill_service import select_analysis_skills
from app.services.validation_service import render_validation_failure, validate_execution_artifact, validate_final_answer


class EvidenceServicesTest(unittest.TestCase):
    def test_planning_guard_clarifies_missing_metric_evidence(self) -> None:
        plan, metadata = _apply_planning_guards(
            AnalysisPlan(intent="ranking", needs_clarification=False),
            "哪个品类利润最高？",
            [{"columns": [{"name": "payment_value"}, {"name": "product_category"}]}],
            [{
                "id": "ecommerce.gross_profit",
                "name": "Gross Profit",
                "matched_terms": ["利润"],
                "missing_concepts": ["cost_amount"],
            }],
        )

        self.assertTrue(plan.needs_clarification)
        self.assertIn("cost_amount", plan.clarification_question)
        self.assertTrue(metadata["applied"])

    def test_planning_guard_clarifies_an_absent_requested_dimension(self) -> None:
        plan, metadata = _apply_planning_guards(
            AnalysisPlan(intent="ranking"),
            "哪个获客渠道的新客质量最好？",
            [{"columns": [{"name": "customer_unique_id"}, {"name": "order_id"}]}],
            [],
        )

        self.assertTrue(plan.needs_clarification)
        self.assertIn("channel", plan.clarification_question)
        self.assertTrue(metadata["applied"])

    def test_planning_guard_does_not_block_an_available_dimension(self) -> None:
        plan, metadata = _apply_planning_guards(
            AnalysisPlan(intent="ranking"),
            "按 channel 比较订单量",
            [{"columns": [{"name": "channel"}, {"name": "order_id"}]}],
            [],
        )

        self.assertFalse(plan.needs_clarification)
        self.assertFalse(metadata["applied"])

    def test_code_extraction_handles_provider_response_shapes(self) -> None:
        fenced = _extract_code_and_reasoning(
            "Short summary.\r\n```Python\r\nimport json\nprint('ok')\r\n```"
        )
        structured = _extract_code_and_reasoning(json.dumps({
            "code": "import pandas as pd\nprint(1)",
            "reasoning_summary": "Read and aggregate the data.",
        }))
        content_blocks = _message_text({
            "content": [{"type": "text", "text": "```python\nprint(2)\n```"}],
        })

        self.assertEqual(fenced["code"], "import json\nprint('ok')")
        self.assertEqual(fenced["thinking_process"], "Short summary.")
        self.assertEqual(structured["code"], "import pandas as pd\nprint(1)")
        self.assertIn("print(2)", content_blocks)

    def test_code_extraction_rejects_reasoning_only_response(self) -> None:
        parsed = _extract_code_and_reasoning("I would first inspect the columns and then aggregate them.")
        self.assertEqual(parsed["code"], "")

    def test_visualization_policy_rejects_image_rendering_libraries(self) -> None:
        self.assertTrue(contains_image_generation("import matplotlib.pyplot as plt\nplt.show()"))
        self.assertTrue(contains_image_generation("import plotly.express as px\npx.bar(df, x='a', y='b')"))
        self.assertTrue(contains_image_generation("from graphviz import Digraph\nDigraph().render()"))
        self.assertFalse(contains_image_generation("result = {'datasets': [], 'visualizations': []}"))

        prompt = _build_code_generation_prompt(
            "生成交互式数据看板",
            [{
                "fileId": "file-1",
                "fileName": "sample.csv",
                "headers": ["group", "value"],
                "rows": 2,
                "columns": 2,
            }],
            "zero",
            {"plan": {"intent": "aggregation"}},
        )
        self.assertIn("NEVER create, display, or save plots/images", prompt)
        self.assertIn("result['datasets']", prompt)
        self.assertIn("heatmap", prompt)

    def test_analysis_result_accepts_valid_visualization_contract(self) -> None:
        result = AnalysisResult.model_validate({
            "answer_type": "table",
            "primary_value": None,
            "unit": None,
            "summary": "Grouped means.",
            "rows": [{"Outcome": 0, "Glucose": 109.9}],
            "columns_used": ["Outcome", "Glucose"],
            "metric_id": None,
            "assumptions": [],
            "insights": ["Outcome 1 has a higher mean glucose value."],
            "datasets": [{
                "id": "group_means",
                "name": "Group means",
                "rows": [
                    {"Outcome": 0, "feature": "Glucose", "mean": 109.9},
                    {"Outcome": 1, "feature": "Glucose", "mean": 140.2},
                ],
            }],
            "visualizations": [{
                "type": "bar",
                "title": "Mean glucose by outcome",
                "dataset_id": "group_means",
                "x": "Outcome",
                "y": "mean",
                "series": "feature",
            }],
        })
        self.assertEqual(result.visualizations[0].dataset_id, "group_means")
        self.assertEqual(len(result.datasets[0].rows), 2)

    def test_analysis_result_rejects_invalid_visualization_reference(self) -> None:
        payload = {
            "answer_type": "table",
            "primary_value": None,
            "unit": None,
            "summary": "Invalid chart reference.",
            "rows": [],
            "columns_used": ["Outcome"],
            "metric_id": None,
            "assumptions": [],
            "datasets": [{"id": "groups", "name": "Groups", "rows": [{"Outcome": 0}]}],
            "visualizations": [{
                "type": "bar",
                "title": "Missing field",
                "dataset_id": "groups",
                "x": "Outcome",
                "y": "mean",
            }],
        }
        with self.assertRaises(ValueError):
            AnalysisResult.model_validate(payload)

    def test_analysis_result_normalizes_common_visualization_fields_and_prunes_unused_datasets(self) -> None:
        datasets = [
            {"id": f"unused_{index}", "name": f"Unused {index}", "rows": [{"value": index}]}
            for index in range(12)
        ]
        datasets.extend([
            {
                "id": "corr",
                "name": "Correlation",
                "rows": [{"x": "A", "y": "B", "value": 0.75}],
            },
            {
                "id": "glucose_box",
                "name": "Glucose by outcome",
                "rows": [{"outcome": 0, "lower": 40, "q1": 90, "median": 105, "q3": 120, "upper": 160}],
            },
            {
                "id": "glucose_hist",
                "name": "Glucose distribution",
                "rows": [{"bin_start": 40, "bin_end": 50, "count": 3}],
            },
        ])
        result = AnalysisResult.model_validate({
            "answer_type": "table",
            "summary": "EDA complete.",
            "rows": [],
            "columns_used": ["Glucose", "Outcome"],
            "datasets": datasets,
            "visualizations": [
                {"type": "heatmap", "title": "Correlation", "dataset_id": "corr"},
                {"type": "box", "title": "Glucose", "dataset_id": "glucose_box"},
                {"type": "histogram", "title": "Distribution", "dataset_id": "glucose_hist"},
            ],
        })

        self.assertEqual({item.id for item in result.datasets}, {"corr", "glucose_box", "glucose_hist"})
        self.assertEqual(result.visualizations[0].value, "value")
        self.assertEqual(result.visualizations[1].x, "outcome")
        self.assertEqual(result.visualizations[2].y, "count")

    def test_visualization_request_requires_dashboard_contract(self) -> None:
        plan = AnalysisPlan(intent="data_quality", required_columns=["Outcome"])
        artifact = {
            "answer_type": "text",
            "primary_value": "Completed",
            "unit": None,
            "summary": "Quality analysis completed.",
            "rows": [],
            "columns_used": ["Outcome"],
            "metric_id": None,
            "assumptions": [],
            "datasets": [],
            "visualizations": [],
        }
        report = validate_execution_artifact(
            plan,
            {"status": "success", "structured_result": artifact},
            ["Outcome"],
            [],
            visualization_required=True,
        )

        check = next(item for item in report.checks if item.name == "visualization_contract")
        self.assertFalse(report.passed)
        self.assertEqual(check.status, "fail")

    def test_sandbox_configuration_error_is_not_sent_to_code_repair(self) -> None:
        self.assertTrue(_is_non_repairable_execution_error({
            "status": "error",
            "content": "Sandbox configuration error: Docker not found.",
        }))
        self.assertTrue(_is_non_repairable_execution_error({
            "status": "error",
            "content": "ModuleNotFoundError: No module named 'pandas'",
        }))
        self.assertFalse(_is_non_repairable_execution_error({
            "status": "error",
            "content": "Execution error: KeyError: Sales",
        }))

    def test_profile_identifies_roles_and_quality_signals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orders.csv"
            path.write_text(
                "order_id,paid_amount,channel,paid_at\n"
                "o1,10.5,search,2026-01-01\n"
                "o2,20.0,social,2026-01-02\n"
                "o2,,social,2026-01-02\n",
                encoding="utf-8",
            )
            profile = build_dataset_profile(path)

        columns = {item["name"]: item for item in profile["columns"]}
        self.assertEqual(profile["row_count"], 3)
        self.assertEqual(profile["duplicate_rows"], 0)
        self.assertEqual(columns["order_id"]["semantic_role"], "identifier")
        self.assertEqual(columns["paid_amount"]["semantic_role"], "measure")
        self.assertEqual(columns["paid_at"]["semantic_role"], "time")
        self.assertAlmostEqual(columns["paid_amount"]["null_rate"], 1 / 3, places=4)

    def test_metric_retrieval_binds_logical_fields(self) -> None:
        profiles = [{
            "file_name": "orders.csv",
            "columns": [
                {"name": "order_id", "semantic_role": "identifier"},
                {"name": "paid_amount", "semantic_role": "measure"},
            ],
        }]
        matches = retrieve_metric_definitions("What is our average order value?", profiles)
        compact = compact_metric_match(matches[0])

        self.assertEqual(compact["id"], "ecommerce.aov")
        self.assertFalse(compact["missing_concepts"])
        self.assertEqual(compact["field_bindings"]["order_id"][0]["column"], "order_id")
        self.assertEqual(compact["field_bindings"]["paid_amount"][0]["column"], "paid_amount")
        self.assertEqual(compact["time_concept"], "payment_time")
        self.assertEqual(compact["time_binding_status"], "unresolved")
        self.assertEqual(compact["time_field_candidates"], [])

    def test_olist_project_override_is_explicit_and_binds_business_time(self) -> None:
        profiles = [{
            "file_name": "orders.csv",
            "columns": [
                {"name": "order_id"},
                {"name": "order_status"},
                {"name": "order_purchase_timestamp"},
            ],
        }, {
            "file_name": "payments.csv",
            "columns": [{"name": "order_id"}, {"name": "payment_value"}],
        }]

        domain_match = compact_metric_match(
            retrieve_metric_definitions("What is the AOV?", profiles)[0]
        )
        olist_match = compact_metric_match(
            retrieve_metric_definitions("What is the AOV?", profiles, project_id="olist")[0]
        )

        self.assertIsNone(domain_match["knowledge_context"]["project_id"])
        self.assertEqual(domain_match["time_concept"], "payment_time")
        self.assertEqual(domain_match["default_population"], "Valid paid orders in the analysis period.")
        self.assertEqual(olist_match["knowledge_context"]["project_id"], "olist")
        self.assertEqual(olist_match["domain_time_concept"], "payment_time")
        self.assertEqual(olist_match["time_concept"], "order_time")
        self.assertEqual(olist_match["time_binding_status"], "resolved")
        self.assertEqual(
            olist_match["time_field_candidates"][0]["column"],
            "order_purchase_timestamp",
        )
        self.assertEqual(
            olist_match["field_bindings"]["paid_amount"][0]["binding_source"],
            "project_override",
        )
        self.assertIn("valid_completed_order", olist_match["default_population"])

    def test_payment_structure_retrieves_amount_and_order_grain_metrics(self) -> None:
        profiles = [{
            "file_name": "orders.csv",
            "columns": [
                {"name": "order_id"},
                {"name": "order_status"},
                {"name": "order_purchase_timestamp"},
            ],
        }, {
            "file_name": "payments.csv",
            "columns": [
                {"name": "order_id"},
                {"name": "payment_value"},
                {"name": "payment_type"},
                {"name": "payment_sequential"},
            ],
        }]
        matches = retrieve_metric_definitions(
            "比较支付方式金额占比，并计算多次支付订单占比",
            profiles,
            project_id="olist",
        )
        by_id = {match.metric.id: compact_metric_match(match) for match in matches}

        self.assertIn("ecommerce.payment_method_amount_share", by_id)
        self.assertIn("ecommerce.multi_payment_order_rate", by_id)
        self.assertEqual(by_id["ecommerce.payment_method_amount_share"]["entity"], "payment")
        self.assertEqual(by_id["ecommerce.multi_payment_order_rate"]["entity"], "order")
        self.assertEqual(
            by_id["ecommerce.multi_payment_order_rate"]["time_field_candidates"][0]["column"],
            "order_purchase_timestamp",
        )

    def test_more_specific_payment_gmv_shadows_nested_gmv_alias(self) -> None:
        profiles = [{
            "file_name": "orders.csv",
            "columns": [{"name": "order_id"}, {"name": "payment_value"}],
        }]
        matches = retrieve_metric_definitions("计算支付GMV", profiles)
        by_id = {match.metric.id: compact_metric_match(match) for match in matches}

        self.assertEqual(by_id["ecommerce.payment_gmv"]["match_type"], "exact")
        self.assertTrue(by_id["ecommerce.payment_gmv"]["decision_required"])
        self.assertIsNone(by_id["ecommerce.payment_gmv"]["shadowed_by"])
        self.assertEqual(by_id["ecommerce.gmv"]["match_type"], "exact")
        self.assertFalse(by_id["ecommerce.gmv"]["decision_required"])
        self.assertEqual(
            by_id["ecommerce.gmv"]["shadowed_by"],
            "ecommerce.payment_gmv",
        )

    def test_token_overlap_candidate_is_not_a_required_decision(self) -> None:
        profiles = [{
            "file_name": "orders.csv",
            "columns": [
                {"name": "order_id"},
                {"name": "payment_value"},
                {"name": "order_purchase_timestamp"},
            ],
        }]
        matches = retrieve_metric_definitions("Show monthly GMV and AOV", profiles)
        by_id = {match.metric.id: compact_metric_match(match) for match in matches}

        self.assertEqual(by_id["ecommerce.payment_gmv"]["match_type"], "token_overlap")
        self.assertFalse(by_id["ecommerce.payment_gmv"]["decision_required"])

    def test_skill_selection_is_question_driven(self) -> None:
        skills = select_analysis_skills("Which region has the highest sales and what is the top 3?")
        self.assertIn("aggregation_ranking", {skill["id"] for skill in skills})

    def test_workflow_metadata_exposes_skill_selection_reason(self) -> None:
        matched_skills = select_analysis_skills("按 Outcome 分组比较各数值特征的平均值")
        matched_metadata = _workflow_metadata({
            "graph_thread_id": "test-matched",
            "steps": [],
            "profiles": [],
            "selected_skills": matched_skills,
            "metric_matches": [],
            "plan": AnalysisPlan(intent="aggregation").model_dump(mode="json"),
            "planner_metadata": {},
            "execution_attempts": [],
            "max_repair_attempts": 1,
        })
        fallback_skills = select_analysis_skills("请帮我看看这个数据")
        fallback_metadata = _workflow_metadata({
            "graph_thread_id": "test-fallback",
            "steps": [],
            "profiles": [],
            "selected_skills": fallback_skills,
            "metric_matches": [],
            "plan": AnalysisPlan(intent="filtering").model_dump(mode="json"),
            "planner_metadata": {},
            "execution_attempts": [],
            "max_repair_attempts": 1,
        })

        selected = matched_metadata["selected_skills"][0]
        self.assertEqual(selected["name"], "Aggregation and Ranking")
        self.assertEqual(selected["selection_mode"], "keyword_match")
        self.assertTrue({"分组", "平均"}.intersection(selected["matched_terms"]))
        self.assertEqual(
            fallback_metadata["selected_skills"][0]["selection_mode"],
            "default_fallback",
        )

    def test_structured_result_marker_is_removed_from_display_output(self) -> None:
        payload = {
            "answer_type": "number",
            "primary_value": 15.25,
            "unit": "USD",
            "summary": "Average order value is 15.25 USD.",
            "rows": [],
            "columns_used": ["paid_amount", "order_id"],
            "metric_id": "ecommerce.aov",
            "assumptions": [],
        }
        stdout = f"diagnostic line\n{RESULT_MARKER}{json.dumps(payload)}\n"
        result, display = _extract_structured_result(stdout)

        self.assertEqual(result["primary_value"], 15.25)
        self.assertEqual(display, "diagnostic line")

    def test_table_result_normalizes_list_primary_value_and_never_leaks_marker(self) -> None:
        rows = [
            {"Outcome": 0, "Glucose": 109.9154929577},
            {"Outcome": 1, "Glucose": 140.1837708831},
        ]
        payload = {
            "answer_type": "table",
            "primary_value": rows,
            "unit": "numeric_mean",
            "summary": "Feature means grouped by outcome.",
            "rows": rows,
            "columns_used": ["Outcome", "Glucose"],
            "metric_id": None,
            "assumptions": [],
        }

        result, display = _extract_structured_result(
            f"<table><tr><td>diagnostic</td></tr></table>\n{RESULT_MARKER}{json.dumps(payload)}"
        )

        self.assertIsNone(result["primary_value"])
        self.assertEqual(result["rows"], rows)
        self.assertNotIn(RESULT_MARKER, display)

    def test_invalid_marker_payload_is_hidden_from_display_output(self) -> None:
        result, display = _extract_structured_result(
            f"readable diagnostic\n{RESULT_MARKER}{{not-json}}"
        )

        self.assertIsNone(result)
        self.assertIn("readable diagnostic", display)
        self.assertIn("Structured result JSON error", display)

    def test_schema_error_is_available_to_the_repair_loop(self) -> None:
        payload = {
            "answer_type": "table",
            "summary": "Bad visualization.",
            "rows": [],
            "columns_used": [],
            "datasets": [{"id": "values", "name": "Values", "rows": [{"label": "A"}]}],
            "visualizations": [{"type": "bar", "title": "Values", "dataset_id": "values"}],
        }

        result, display = _extract_structured_result(f"{RESULT_MARKER}{json.dumps(payload)}")

        self.assertIsNone(result)
        self.assertIn("Structured result validation error", display)
        self.assertIn("require x and y fields", display)

    def test_validation_accepts_grounded_typed_artifact(self) -> None:
        plan = AnalysisPlan(
            intent="aggregation",
            metric_ids=["ecommerce.aov"],
            required_columns=["paid_amount", "order_id"],
            aggregation="sum(paid_amount) / count_distinct(order_id)",
        )
        artifact = {
            "answer_type": "number",
            "primary_value": 15.25,
            "unit": "USD/order",
            "summary": "Average order value is 15.25 USD per order.",
            "rows": [],
            "columns_used": ["paid_amount", "order_id"],
            "metric_id": "ecommerce.aov",
            "assumptions": [],
        }
        report = validate_execution_artifact(
            plan,
            {"status": "success", "structured_result": artifact},
            ["paid_amount", "order_id"],
            [{"id": "ecommerce.aov"}],
        )
        final_report = validate_final_answer(
            "Average order value is 15.25 USD per order.",
            artifact,
            "15.25",
            "What is average order value?",
        )

        self.assertTrue(report.passed)
        self.assertEqual(report.confidence, "high")
        self.assertTrue(final_report.passed)

        artifact["metric_id"] = "ecommerce.gmv"
        ungrounded_report = validate_execution_artifact(
            AnalysisPlan(intent="aggregation", required_columns=["paid_amount", "order_id"]),
            {"status": "success", "structured_result": artifact},
            ["paid_amount", "order_id"],
            [],
        )
        self.assertFalse(ungrounded_report.passed)

    def test_validation_failure_explains_cause_and_next_step_in_chinese(self) -> None:
        plan = AnalysisPlan(intent="aggregation")
        report = validate_execution_artifact(
            plan,
            {"status": "success", "structured_result": None},
            ["Outcome", "Glucose"],
            [],
        )

        message = render_validation_failure(
            report,
            {"status": "success", "content": "raw protocol output"},
            repair_attempts=2,
            question="按 Outcome 分组比较均值",
        )

        self.assertIn("可能原因", message)
        self.assertIn("建议修改", message)
        self.assertIn("rows", message)
        self.assertIn("2 次", message)


if __name__ == "__main__":
    unittest.main()
