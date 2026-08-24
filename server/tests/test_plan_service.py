import json
import unittest
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from app.schemas.analysis import (
    AnalysisPlan,
    JoinRequirement,
    MetricCandidateRejection,
    MetricOperand,
    PlannedMetric,
)
from app.services.plan_service import evaluate_plan_completeness, generate_analysis_plan


ORDERS_PROFILE = {
    "file_name": "orders.csv",
    "columns": [
        {"name": "order_id"},
        {"name": "order_status"},
        {"name": "order_purchase_timestamp"},
        {"name": "group"},
        {"name": "value"},
    ],
}
PAYMENTS_PROFILE = {
    "file_name": "payments.csv",
    "columns": [
        {"name": "order_id"},
        {"name": "payment_value"},
        {"name": "payment_type"},
    ],
}


def _metric(**overrides):
    payload = {
        "key": "total_value",
        "label": "Total value",
        "metric_type": "sum",
        "definition": "Total value in the selected population",
        "calculation": "Sum value",
    }
    payload.update(overrides)
    return PlannedMetric(**payload)


def _ready_plan(**overrides):
    payload = {
        "intent": "aggregation",
        "analysis_scope": "All rows in orders.csv",
        "entity_grain": "One row per order_id",
        "metrics": [_metric()],
        "required_columns": ["orders.csv.order_id", "orders.csv.value"],
        "steps": ["Read the selected rows", "Calculate the requested metric"],
    }
    payload.update(overrides)
    return AnalysisPlan(**payload)


def _payload(plan):
    return {
        "choices": [{"message": {"content": json.dumps(plan, ensure_ascii=False)}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }


class PlanCompletenessTest(unittest.TestCase):
    def test_empty_plan_is_not_schema_valid(self) -> None:
        with self.assertRaises(ValidationError):
            AnalysisPlan.model_validate({})

    def test_aggregation_without_metric_is_not_ready(self) -> None:
        plan = _ready_plan(metrics=[])
        report = evaluate_plan_completeness(plan, [ORDERS_PROFILE], [])
        self.assertFalse(report.ready_for_code_generation)
        self.assertIn("missing_metrics", {item.code for item in report.issues})

    def test_ratio_without_denominator_is_not_ready(self) -> None:
        metric = _metric(
            key="share",
            metric_type="ratio",
            numerator=MetricOperand(description="Selected orders", aggregation="count distinct order_id"),
        )
        report = evaluate_plan_completeness(_ready_plan(metrics=[metric]), [ORDERS_PROFILE], [])
        self.assertIn("missing_denominator", {item.code for item in report.issues})

    def test_trend_requires_time_field_and_grain(self) -> None:
        report = evaluate_plan_completeness(
            _ready_plan(intent="trend"),
            [ORDERS_PROFILE],
            [],
        )
        codes = {item.code for item in report.issues}
        self.assertIn("missing_time_field", codes)
        self.assertIn("missing_time_grain", codes)

    def test_multi_table_plan_requires_join(self) -> None:
        plan = _ready_plan(required_columns=[
            "orders.csv.order_id",
            "payments.csv.payment_value",
        ])
        report = evaluate_plan_completeness(plan, [ORDERS_PROFILE, PAYMENTS_PROFILE], [])
        self.assertIn("missing_join_requirement", {item.code for item in report.issues})

    def test_many_to_many_requires_pre_join_aggregation(self) -> None:
        join = JoinRequirement(
            left_dataset="orders.csv",
            right_dataset="payments.csv",
            join_keys=["order_id"],
            how="inner",
            left_grain="Multiple order rows",
            right_grain="Multiple payment rows",
            relationship="many_to_many",
        )
        plan = _ready_plan(
            required_columns=["orders.csv.order_id", "payments.csv.payment_value"],
            joins=[join],
        )
        report = evaluate_plan_completeness(plan, [ORDERS_PROFILE, PAYMENTS_PROFILE], [])
        self.assertIn("missing_pre_join_aggregation", {item.code for item in report.issues})

    def test_decision_required_metric_cannot_be_silently_omitted(self) -> None:
        metric_matches = [{
            "id": "ecommerce.gmv",
            "matched_terms": ["GMV"],
            "missing_concepts": [],
            "decision_required": True,
        }]
        report = evaluate_plan_completeness(_ready_plan(), [ORDERS_PROFILE], metric_matches)
        self.assertIn("unresolved_metric_candidate", {item.code for item in report.issues})

    def test_token_overlap_candidate_is_not_mandatory(self) -> None:
        metric_matches = [{
            "id": "ecommerce.payment_gmv",
            "match_type": "token_overlap",
            "decision_required": False,
        }]
        report = evaluate_plan_completeness(_ready_plan(), [ORDERS_PROFILE], metric_matches)
        self.assertTrue(report.ready_for_code_generation)

    def test_reasonable_metric_rejection_satisfies_candidate_decision(self) -> None:
        plan = _ready_plan(rejected_metrics=[MetricCandidateRejection(
            metric_id="ecommerce.order_count",
            reason="The question audits review grain rather than valid-order volume.",
        )])
        report = evaluate_plan_completeness(plan, [ORDERS_PROFILE], [{
            "id": "ecommerce.order_count",
            "decision_required": True,
        }])
        self.assertTrue(report.ready_for_code_generation)

    def test_metric_cannot_be_selected_and_rejected(self) -> None:
        selected = _metric(metric_id="ecommerce.gmv")
        plan = _ready_plan(
            metric_ids=["ecommerce.gmv"],
            metrics=[selected],
            rejected_metrics=[MetricCandidateRejection(
                metric_id="ecommerce.gmv",
                reason="Not applicable.",
            )],
        )
        report = evaluate_plan_completeness(plan, [ORDERS_PROFILE], [{
            "id": "ecommerce.gmv",
            "decision_required": True,
        }])
        self.assertIn("selected_rejected_metric_conflict", {item.code for item in report.issues})

    def test_rejected_metric_must_be_a_candidate(self) -> None:
        plan = _ready_plan(rejected_metrics=[MetricCandidateRejection(
            metric_id="ecommerce.unknown",
            reason="Not applicable.",
        )])
        report = evaluate_plan_completeness(plan, [ORDERS_PROFILE], [])
        self.assertIn("unretrieved_rejected_metric", {item.code for item in report.issues})

    def test_superseded_by_must_reference_selected_metric(self) -> None:
        plan = _ready_plan(rejected_metrics=[MetricCandidateRejection(
            metric_id="ecommerce.gmv",
            reason="A more specific payment metric applies.",
            superseded_by="ecommerce.payment_gmv",
        )])
        report = evaluate_plan_completeness(plan, [ORDERS_PROFILE], [{
            "id": "ecommerce.gmv",
            "decision_required": True,
        }, {
            "id": "ecommerce.payment_gmv",
            "decision_required": False,
        }])
        self.assertIn("invalid_metric_supersession", {item.code for item in report.issues})

    def test_valid_clarification_stops_without_computation_fields(self) -> None:
        plan = AnalysisPlan(
            intent="metric_diagnostic",
            needs_clarification=True,
            clarification_question="Which revenue definition should be used?",
        )
        report = evaluate_plan_completeness(plan, [ORDERS_PROFILE], [{
            "id": "ecommerce.gmv",
            "decision_required": True,
        }])
        self.assertTrue(report.valid_clarification)
        self.assertFalse(report.ready_for_code_generation)
        self.assertEqual(report.issues, [])


class PlannerReplanTest(unittest.IsolatedAsyncioTestCase):
    async def test_replan_once_then_pass(self) -> None:
        incomplete = _ready_plan(metrics=[]).model_dump(mode="json")
        complete = _ready_plan().model_dump(mode="json")
        with patch(
            "app.services.plan_service._request_planner_payload",
            AsyncMock(side_effect=[_payload(incomplete), _payload(complete)]),
        ) as request:
            plan, metadata = await generate_analysis_plan(
                "Calculate total value",
                [ORDERS_PROFILE],
                [],
                [],
                model="test-model",
            )

        self.assertEqual(request.await_count, 2)
        self.assertTrue(metadata["replanned"])
        self.assertEqual(metadata["attempt_count"], 2)
        self.assertTrue(metadata["completeness"]["ready_for_code_generation"])
        self.assertEqual(plan.metrics[0].key, "total_value")

    async def test_replan_once_then_still_fails(self) -> None:
        incomplete = _ready_plan(metrics=[]).model_dump(mode="json")
        with patch(
            "app.services.plan_service._request_planner_payload",
            AsyncMock(side_effect=[_payload(incomplete), _payload(incomplete)]),
        ) as request:
            _, metadata = await generate_analysis_plan(
                "Calculate total value",
                [ORDERS_PROFILE],
                [],
                [],
                model="test-model",
            )

        self.assertEqual(request.await_count, 2)
        self.assertEqual(metadata["planner"], "llm_structured_output_incomplete")
        self.assertFalse(metadata["completeness"]["ready_for_code_generation"])
        self.assertIn(
            "missing_metrics",
            {item["code"] for item in metadata["completeness"]["issues"]},
        )


if __name__ == "__main__":
    unittest.main()
