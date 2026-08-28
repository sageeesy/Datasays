import json
import tempfile
import unittest
from pathlib import Path

from app.schemas.analysis import AnalysisPlan, AnalysisResult, MetricCandidateRejection, PlannedMetric
from app.services.agent_service import _is_non_repairable_execution_error, _workflow_metadata
from app.services.plan_service import _apply_planning_guards
from app.services.code_service import (
    _build_code_generation_prompt,
    _extract_code_and_reasoning,
    _message_text,
    _normalize_json_literals_in_python,
    contains_image_generation,
)
from app.services.metric_service import (
    compact_metric_match,
    resolved_metric_candidate,
    retrieve_metric_definitions,
)
from app.services.profile_service import build_dataset_profile
from app.services.sandbox_service import RESULT_MARKER, _extract_structured_result
from app.services.skill_service import select_analysis_skills
from app.services.validation_service import render_validation_failure, validate_execution_artifact, validate_final_answer


class EvidenceServicesTest(unittest.TestCase):
    def test_planning_guard_clarifies_missing_metric_evidence(self) -> None:
        plan, metadata = _apply_planning_guards(
            AnalysisPlan(
                intent="ranking",
                metric_ids=["ecommerce.gross_profit"],
                metrics=[PlannedMetric(
                    key="gross_profit",
                    label="Gross Profit",
                    metric_id="ecommerce.gross_profit",
                    metric_type="sum",
                    definition="Revenue less direct cost.",
                    calculation="sum(revenue - cost)",
                )],
                needs_clarification=False,
            ),
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

    def test_planning_guard_does_not_revive_rejected_metric(self) -> None:
        plan, metadata = _apply_planning_guards(
            AnalysisPlan(
                intent="aggregation",
                rejected_metrics=[MetricCandidateRejection(
                    metric_id="ecommerce.purchase_conversion_rate",
                    reason="The query defines an event funnel rather than this business KPI.",
                )],
            ),
            "Build a view to purchase funnel.",
            [{"columns": [{"name": "user_id"}, {"name": "event"}, {"name": "event_time"}]}],
            [{
                "id": "ecommerce.purchase_conversion_rate",
                "name": "Purchase Conversion Rate",
                "matched_terms": ["purchase conversion"],
                "decision_required": True,
                "missing_concepts": ["purchase_flag", "eligible_user_flag"],
            }],
        )

        self.assertFalse(plan.needs_clarification)
        self.assertFalse(metadata["applied"])

    def test_planning_guard_ignores_unselected_optional_missing_metric(self) -> None:
        plan, metadata = _apply_planning_guards(
            AnalysisPlan(intent="aggregation"),
            "Summarize sensor values.",
            [{"columns": [{"name": "sensor_value"}]}],
            [{
                "id": "saas.arr",
                "matched_terms": [],
                "decision_required": False,
                "missing_concepts": ["recurring_amount", "billing_interval"],
            }],
        )

        self.assertFalse(plan.needs_clarification)
        self.assertFalse(metadata["applied"])

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

    def test_generated_python_normalizes_bare_json_literals(self) -> None:
        code = '''result = {
    "primary_value": null,
    "is_valid": true,
    "has_error": false,
    "note": "null true false",
}
# null true false in a comment
'''

        normalized = _normalize_json_literals_in_python(code)

        self.assertIn('"primary_value": None', normalized)
        self.assertIn('"is_valid": True', normalized)
        self.assertIn('"has_error": False', normalized)
        self.assertIn('"note": "null true false"', normalized)
        self.assertIn('# null true false in a comment', normalized)
        compile(normalized, "<generated>", "exec")

    def test_code_extraction_returns_normalized_executable_python(self) -> None:
        parsed = _extract_code_and_reasoning(
            "```python\nresult = {'primary_value': null, 'ok': true, 'failed': false}\n```"
        )

        self.assertIn("'primary_value': None", parsed["code"])
        self.assertIn("'ok': True", parsed["code"])
        self.assertIn("'failed': False", parsed["code"])
        compile(parsed["code"], "<generated>", "exec")

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
        self.assertIn("character-for-character", prompt)
        self.assertIn("MUST be a subset", prompt)

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

    def test_analysis_result_accepts_scalar_and_dataset_evidence(self) -> None:
        result = AnalysisResult.model_validate({
            "answer_type": "table",
            "summary": "Monthly rate.",
            "rows": [],
            "datasets": [{
                "id": "monthly_rates",
                "name": "Monthly rates",
                "rows": [{"month": "2026-01", "rate": 0.25}],
            }],
            "visualizations": [],
            "evidence": [
                {
                    "plan_metric_key": "conversion_rate",
                    "kind": "scalar",
                    "value": 0.25,
                    "value_scale": "fraction",
                    "unit": "ratio",
                    "dataset_id": None,
                    "value_field": None,
                    "dimension_fields": [],
                    "coordinates": {"year": 2026},
                    "label": "Overall conversion rate",
                },
                {
                    "plan_metric_key": "conversion_rate",
                    "kind": "dataset",
                    "value": None,
                    "value_scale": "fraction",
                    "unit": "ratio",
                    "dataset_id": "monthly_rates",
                    "value_field": "rate",
                    "dimension_fields": ["month"],
                    "coordinates": {},
                    "label": "Monthly conversion rate",
                },
            ],
        })

        self.assertEqual(len(result.evidence), 2)

    def test_analysis_result_normalizes_scalar_evidence_transport_fields(self) -> None:
        result = AnalysisResult.model_validate({
            "answer_type": "number",
            "primary_value": 10,
            "summary": "Value.",
            "datasets": [],
            "visualizations": [],
            "evidence": [{
                "plan_metric_key": "value",
                "kind": "scalar",
                "value": 10,
                "value_scale": "raw",
                "unit": "",
                "dataset_id": "",
                "value_field": "",
                "dimension_fields": ["month"],
                "coordinates": {"month": "2026-01"},
                "label": "Value",
            }],
        })

        evidence = result.evidence[0]
        self.assertIsNone(evidence.dataset_id)
        self.assertIsNone(evidence.value_field)
        self.assertIsNone(evidence.unit)
        self.assertEqual(evidence.dimension_fields, [])
        self.assertEqual(evidence.coordinates, {"month": "2026-01"})

    def test_analysis_result_rejects_invalid_evidence_shapes_and_references(self) -> None:
        base = {
            "answer_type": "table",
            "summary": "Evidence.",
            "rows": [],
            "datasets": [{"id": "values", "name": "Values", "rows": [{"group": "A", "value": 1}]}],
            "visualizations": [],
        }
        invalid_evidence = [
            {"kind": "scalar", "value": None},
            {"kind": "dataset", "value": 1, "dataset_id": "values", "value_field": "value"},
            {"kind": "dataset", "value": None, "dataset_id": "missing", "value_field": "value"},
            {
                "kind": "dataset",
                "value": None,
                "dataset_id": "values",
                "value_field": "missing_value",
                "dimension_fields": ["missing_dimension"],
            },
        ]

        for evidence in invalid_evidence:
            with self.subTest(evidence=evidence), self.assertRaises(ValueError):
                AnalysisResult.model_validate({**base, "evidence": [evidence]})

    def test_result_evidence_coverage_warns_without_breaking_legacy_results(self) -> None:
        plan = AnalysisPlan.model_validate({
            "intent": "aggregation",
            "analysis_scope": "All rows.",
            "entity_grain": "period",
            "metrics": [
                {
                    "key": "revenue",
                    "label": "Revenue",
                    "metric_id": None,
                    "metric_type": "sum",
                    "definition": "Total revenue.",
                    "calculation": "sum(revenue)",
                },
                {
                    "key": "conversion_rate",
                    "label": "Conversion rate",
                    "metric_id": None,
                    "metric_type": "rate",
                    "definition": "Conversions divided by visitors.",
                    "calculation": "conversions / visitors",
                    "value_scale": "fraction",
                },
            ],
        })
        artifact = {
            "answer_type": "number",
            "primary_value": 100,
            "summary": "Revenue is 100.",
            "rows": [],
            "columns_used": [],
            "datasets": [],
            "visualizations": [],
            "evidence": [{
                "plan_metric_key": "revenue",
                "kind": "scalar",
                "value": 100,
                "value_scale": "raw",
            }],
        }

        report = validate_execution_artifact(plan, {"status": "success", "structured_result": artifact}, [], [])
        check = next(item for item in report.checks if item.name == "result_evidence_coverage")

        self.assertTrue(report.passed)
        self.assertEqual(report.confidence, "medium")
        self.assertEqual(check.status, "warning")
        self.assertIn("conversion_rate", check.message)

    def test_result_evidence_coverage_accepts_all_planned_metrics_and_scales(self) -> None:
        plan = AnalysisPlan.model_validate({
            "intent": "aggregation",
            "analysis_scope": "All rows.",
            "entity_grain": "period",
            "metrics": [{
                "key": "conversion_rate",
                "label": "Conversion rate",
                "metric_id": None,
                "metric_type": "rate",
                "definition": "Conversions divided by visitors.",
                "calculation": "conversions / visitors",
                "value_scale": "fraction",
            }],
        })
        artifact = {
            "answer_type": "number",
            "primary_value": 0.25,
            "summary": "Conversion rate is 25%.",
            "rows": [],
            "columns_used": [],
            "datasets": [],
            "visualizations": [],
            "evidence": [{
                "plan_metric_key": "conversion_rate",
                "kind": "scalar",
                "value": 0.25,
                "value_scale": "fraction",
            }],
        }

        report = validate_execution_artifact(plan, {"status": "success", "structured_result": artifact}, [], [])
        check = next(item for item in report.checks if item.name == "result_evidence_coverage")

        self.assertTrue(report.passed)
        self.assertEqual(check.status, "pass")

    def test_required_columns_validate_qualified_dataset_references(self) -> None:
        dataset_columns = {
            "orders": ["order_id", "order_status"],
            "payments": ["order_id", "payment_value"],
        }
        artifact = {
            "answer_type": "text",
            "primary_value": "ok",
            "summary": "Validated.",
            "columns_used": [],
            "datasets": [],
            "visualizations": [],
        }

        for required_column in ("orders.order_id", "payments.payment_value"):
            with self.subTest(required_column=required_column):
                report = validate_execution_artifact(
                    AnalysisPlan(intent="lookup", required_columns=[required_column]),
                    {"status": "success", "structured_result": artifact},
                    ["order_id", "order_status", "payment_value"],
                    [],
                    dataset_columns=dataset_columns,
                )
                check = next(item for item in report.checks if item.name == "required_columns")
                self.assertEqual(check.status, "pass")

        missing_report = validate_execution_artifact(
            AnalysisPlan(intent="lookup", required_columns=["orders.nonexistent"]),
            {"status": "success", "structured_result": artifact},
            ["order_id", "order_status", "payment_value"],
            [],
            dataset_columns=dataset_columns,
        )
        missing_check = next(item for item in missing_report.checks if item.name == "required_columns")
        self.assertEqual(missing_check.status, "fail")

        wrong_dataset_report = validate_execution_artifact(
            AnalysisPlan(intent="lookup", required_columns=["payments.order_status"]),
            {"status": "success", "structured_result": artifact},
            ["order_id", "order_status", "payment_value"],
            [],
            dataset_columns=dataset_columns,
        )
        wrong_dataset_check = next(
            item for item in wrong_dataset_report.checks if item.name == "required_columns"
        )
        self.assertEqual(wrong_dataset_check.status, "fail")

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

    def test_analysis_result_pruning_preserves_evidence_only_dataset(self) -> None:
        datasets = [
            {"id": f"unused_{index}", "name": f"Unused {index}", "rows": [{"value": index}]}
            for index in range(12)
        ]
        datasets.extend([
            {"id": "chart_data", "name": "Chart", "rows": [{"group": "A", "value": 1}]},
            {"id": "evidence_data", "name": "Evidence", "rows": [{"month": "2026-01", "rate": 0.25}]},
        ])

        result = AnalysisResult.model_validate({
            "answer_type": "table",
            "summary": "Evidence preserved.",
            "rows": [],
            "datasets": datasets,
            "visualizations": [{
                "type": "bar",
                "title": "Chart",
                "dataset_id": "chart_data",
                "x": "group",
                "y": "value",
            }],
            "evidence": [{
                "plan_metric_key": "monthly_rate",
                "kind": "dataset",
                "value": None,
                "value_scale": "fraction",
                "dataset_id": "evidence_data",
                "value_field": "rate",
                "dimension_fields": ["month"],
            }],
        })

        self.assertEqual({item.id for item in result.datasets}, {"chart_data", "evidence_data"})

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

    def test_short_english_metric_aliases_respect_word_boundaries(self) -> None:
        profiles = [{"file_name": "data.csv", "columns": [{"name": "value"}]}]

        for question in ("ARR", "ARR growth"):
            matches = retrieve_metric_definitions(question, profiles)
            arr = next(item for item in matches if item.metric.id == "saas.arr")
            self.assertIn("ARR", arr.matched_terms)
            self.assertTrue(arr.decision_required)

        for question, forbidden_id in (
            ("Fit Linear Regression", "saas.arr"),
            ("Build a Random Forest", "saas.nrr"),
            ("Calculate a fraction and return it", "saas.nrr"),
        ):
            self.assertNotIn(
                forbidden_id,
                {item.metric.id for item in retrieve_metric_definitions(question, profiles)},
            )

    def test_complete_english_and_chinese_metric_aliases_still_match(self) -> None:
        profiles = [{"file_name": "subscriptions.csv", "columns": [{"name": "value"}]}]

        english = retrieve_metric_definitions("Show net revenue retention by month", profiles)
        chinese = retrieve_metric_definitions("计算净收入留存率", profiles)

        self.assertTrue(next(item for item in english if item.metric.id == "saas.nrr").decision_required)
        self.assertTrue(next(item for item in chinese if item.metric.id == "saas.nrr").decision_required)

    def test_generic_analysis_can_retrieve_zero_business_metrics(self) -> None:
        profiles = [{"file_name": "sensors.csv", "columns": [{"name": "sensor_z"}]}]
        self.assertEqual(
            retrieve_metric_definitions("Compute the median of sensor_z.", profiles),
            [],
        )

    def test_explicit_olist_metrics_remain_required_grounding_candidates(self) -> None:
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
        matches = retrieve_metric_definitions(
            "Show GMV, Payment GMV, AOV, and Delivery Rate.",
            profiles,
            limit=6,
            project_id="olist",
        )
        by_id = {item.metric.id: item for item in matches}

        self.assertEqual(by_id["ecommerce.gmv"].shadowed_by, "ecommerce.payment_gmv")
        self.assertFalse(by_id["ecommerce.gmv"].decision_required)
        for metric_id in (
            "ecommerce.payment_gmv",
            "ecommerce.aov",
            "ecommerce.delivery_rate",
        ):
            self.assertTrue(by_id[metric_id].decision_required)

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

    def test_resolved_payment_gmv_contract_materializes_olist_semantics(self) -> None:
        profiles = [{
            "file_name": "olist_orders_2017.csv",
            "columns": [
                {"name": "order_id"},
                {"name": "order_status"},
                {"name": "order_purchase_timestamp"},
            ],
        }, {
            "file_name": "olist_order_payments_2017.csv",
            "columns": [{"name": "order_id"}, {"name": "payment_value"}],
        }]
        matches = retrieve_metric_definitions("Calculate payment GMV", profiles, project_id="olist")
        match = next(item for item in matches if item.metric.id == "ecommerce.payment_gmv")
        candidate = resolved_metric_candidate(match)

        self.assertEqual(candidate["resolution_status"], "resolved")
        self.assertEqual(candidate["resolved_time_field"]["column"], "order_purchase_timestamp")
        self.assertEqual(candidate["resolved_population"]["filters"], [{
            "dataset": "olist_orders_2017.csv",
            "column": "order_status",
            "operator": "eq",
            "value": "delivered",
        }])
        self.assertIn("aggregate payment rows by order_id", candidate["pre_aggregation_requirements"][0])
        self.assertNotIn("knowledge_context", candidate)

    def test_resolved_aov_contract_preserves_completed_order_denominator(self) -> None:
        profiles = [{
            "file_name": "olist_orders_2017.csv",
            "columns": [
                {"name": "order_id"},
                {"name": "order_status"},
                {"name": "order_purchase_timestamp"},
            ],
        }, {
            "file_name": "olist_order_payments_2017.csv",
            "columns": [{"name": "order_id"}, {"name": "payment_value"}],
        }]
        matches = retrieve_metric_definitions("What is the AOV?", profiles, project_id="olist")
        match = next(item for item in matches if item.metric.id == "ecommerce.aov")
        contract = resolved_metric_candidate(match)

        self.assertEqual(contract["resolved_denominator"]["calculation_semantics"], "count_distinct(order_id)")
        self.assertIn("completed order_id", contract["resolved_denominator"]["policy"])
        self.assertEqual(
            contract["resolved_denominator"]["filters"],
            contract["resolved_population"]["filters"],
        )
        self.assertEqual(contract["resolved_time_field"]["column"], "order_purchase_timestamp")
        self.assertTrue(contract["pre_aggregation_requirements"])

    def test_resolved_delivery_rate_contract_preserves_all_order_denominator(self) -> None:
        profiles = [{
            "file_name": "olist_orders_2017.csv",
            "columns": [
                {"name": "order_id"},
                {"name": "order_status"},
                {"name": "order_purchase_timestamp"},
            ],
        }]
        matches = retrieve_metric_definitions("Calculate delivery rate", profiles, project_id="olist")
        match = next(item for item in matches if item.metric.id == "ecommerce.delivery_rate")
        contract = resolved_metric_candidate(match)

        self.assertEqual(contract["resolution_status"], "resolved")
        self.assertEqual(contract["resolved_population"]["filters"], [])
        self.assertEqual(contract["resolved_numerator"]["filters"][0]["value"], "delivered")
        self.assertEqual(contract["resolved_denominator"]["filters"], [])
        self.assertIn("all distinct orders", contract["resolved_denominator"]["policy"])
        self.assertEqual(contract["resolved_time_field"]["column"], "order_purchase_timestamp")

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

    def test_olist_payment_structure_contracts_materialize_completed_population(self) -> None:
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
        by_id = {
            match.metric.id: resolved_metric_candidate(match)
            for match in matches
        }
        expected_filter = [{
            "dataset": "orders.csv",
            "column": "order_status",
            "operator": "eq",
            "value": "delivered",
        }]

        for metric_id in (
            "ecommerce.payment_method_amount_share",
            "ecommerce.multi_payment_order_rate",
        ):
            candidate = by_id[metric_id]
            self.assertEqual(candidate["resolution_status"], "resolved")
            self.assertEqual(candidate["resolved_population"]["filters"], expected_filter)
            self.assertEqual(candidate["resolved_numerator"]["filters"], expected_filter)
            self.assertEqual(candidate["resolved_denominator"]["filters"], expected_filter)
            self.assertEqual(
                candidate["provenance"]["population_policy_ids"],
                ["valid_completed_order"],
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

    def test_olist_canonical_gmv_mapping_requires_payment_gmv(self) -> None:
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
        matches = retrieve_metric_definitions(
            "Show monthly GMV and AOV",
            profiles,
            project_id="olist",
        )
        by_id = {match.metric.id: match for match in matches}

        generic = by_id["ecommerce.gmv"]
        payment = by_id["ecommerce.payment_gmv"]
        self.assertFalse(generic.decision_required)
        self.assertEqual(generic.shadowed_by, "ecommerce.payment_gmv")
        self.assertTrue(payment.decision_required)
        self.assertIsNone(payment.shadowed_by)
        self.assertEqual(
            payment.knowledge_context["canonical_metric_mapping"],
            {
                "role": "canonical_target",
                "source_metric_id": "ecommerce.gmv",
                "target_metric_id": "ecommerce.payment_gmv",
                "source": "project_override",
            },
        )
        self.assertEqual(
            resolved_metric_candidate(payment)["provenance"]["canonical_metric_mapping"]["source"],
            "project_override",
        )

    def test_generic_gmv_remains_distinct_without_project_override(self) -> None:
        profiles = [{
            "file_name": "orders.csv",
            "columns": [
                {"name": "order_id"},
                {"name": "payment_value"},
                {"name": "order_purchase_timestamp"},
            ],
        }]
        matches = retrieve_metric_definitions("Show monthly GMV and AOV", profiles)
        by_id = {match.metric.id: match for match in matches}

        self.assertTrue(by_id["ecommerce.gmv"].decision_required)
        self.assertIsNone(by_id["ecommerce.gmv"].shadowed_by)
        self.assertFalse(by_id["ecommerce.payment_gmv"].decision_required)
        self.assertIsNone(
            by_id["ecommerce.payment_gmv"].knowledge_context["canonical_metric_mapping"]
        )

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
