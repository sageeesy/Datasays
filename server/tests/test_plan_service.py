import json
import unittest
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from app.schemas.analysis import (
    AnalysisPlan,
    JoinRequirement,
    MetricCandidateRejection,
    MetricOperand,
    PlanFilter,
    PlannedMetric,
)
from app.services.plan_service import (
    evaluate_plan_completeness,
    generate_analysis_plan,
    infer_plan_dataset_usage,
    normalize_plan_payload,
)


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
ITEMS_PROFILE = {
    "file_name": "items.csv",
    "columns": [
        {"name": "order_id"},
        {"name": "product_id"},
        {"name": "price"},
    ],
}
REVIEWS_PROFILE = {
    "file_name": "reviews.csv",
    "columns": [
        {"name": "order_id"},
        {"name": "review_score"},
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


class PlanNormalizationTest(unittest.TestCase):
    def test_gt_and_lt_are_valid_canonical_operators(self) -> None:
        for operator in ("gt", "lt"):
            payload = _ready_plan().model_dump(mode="json")
            payload["filters"] = [{
                "dataset": "orders.csv",
                "column": "value",
                "operator": operator,
                "value": 1,
            }]
            normalized = normalize_plan_payload(payload, [])
            plan = AnalysisPlan.model_validate(normalized.normalized_payload)
            self.assertEqual(plan.filters[0].operator, operator)

    def test_symbolic_filter_operators_are_canonicalized_without_changing_value(self) -> None:
        aliases = {"==": "eq", "!=": "ne", ">": "gt", ">=": "gte", "<": "lt", "<=": "lte"}
        for source, expected in aliases.items():
            payload = _ready_plan().model_dump(mode="json")
            payload["filters"] = [{
                "dataset": "orders.csv",
                "column": "value",
                "operator": source,
                "value": 1,
            }]
            normalized = normalize_plan_payload(payload, [])
            item = normalized.normalized_payload["filters"][0]
            self.assertEqual(item["operator"], expected)
            self.assertEqual(item["value"], 1)

    def test_rmc_operation_can_fill_null_operand_aggregation(self) -> None:
        payload = _ready_plan(metrics=[_metric(
            metric_id="ecommerce.aov",
            metric_type="ratio",
            numerator={"description": "Paid amount", "aggregation": "sum(payment_value)", "filters": []},
            denominator={"description": "Orders", "aggregation": "count_distinct(order_id)", "filters": []},
        )]).model_dump(mode="json")
        payload["metrics"][0]["numerator"]["aggregation"] = None
        normalized = normalize_plan_payload(payload, [{
            "metric_id": "ecommerce.aov",
            "resolved_numerator": {"calculation_semantics": "sum(payment_value)"},
        }])
        plan = AnalysisPlan.model_validate(normalized.normalized_payload)
        self.assertEqual(plan.metrics[0].numerator.aggregation, "sum(payment_value)")
        self.assertIn(
            "fill_operand_aggregation_from_resolved_metric",
            {item.code for item in normalized.actions},
        )

    def test_ad_hoc_null_operand_aggregation_is_not_guessed(self) -> None:
        payload = _ready_plan(metrics=[_metric(
            metric_type="ratio",
            numerator={"description": "Selected rows", "aggregation": "count_distinct(order_id)", "filters": []},
            denominator={"description": "All rows", "aggregation": "count_distinct(order_id)", "filters": []},
        )]).model_dump(mode="json")
        payload["metrics"][0]["numerator"]["aggregation"] = None
        normalized = normalize_plan_payload(payload, [])
        self.assertIsNone(normalized.normalized_payload["metrics"][0]["numerator"]["aggregation"])
        self.assertIn(
            "unresolved_operand_aggregation",
            {item.code for item in normalized.unresolved_issues},
        )
        with self.assertRaises(ValidationError):
            AnalysisPlan.model_validate(normalized.normalized_payload)

    def test_metric_ids_are_rebuilt_from_selected_metrics(self) -> None:
        payload = _ready_plan(metrics=[_metric(metric_id="ecommerce.aov")]).model_dump(mode="json")
        payload["metric_ids"] = ["ecommerce.gmv", "ecommerce.gmv"]
        normalized = normalize_plan_payload(payload, [])
        self.assertEqual(normalized.normalized_payload["metric_ids"], ["ecommerce.aov"])


class DatasetUsageInferenceTest(unittest.TestCase):
    @staticmethod
    def _plan(**overrides):
        payload = {
            "intent": "filtering",
            "analysis_scope": "Rows selected by structured evidence",
            "entity_grain": "One row per selected entity",
            "required_columns": ["order_id"],
            "steps": ["Use the structured references in the plan"],
        }
        payload.update(overrides)
        return AnalysisPlan(**payload)

    def test_ambiguous_bare_column_does_not_expand_dataset_usage(self) -> None:
        plan = self._plan()
        usage = infer_plan_dataset_usage(
            plan,
            [ORDERS_PROFILE, ITEMS_PROFILE, REVIEWS_PROFILE],
            [],
        )
        self.assertEqual(usage["used_datasets"], [])
        self.assertEqual(
            usage["unqualified_references"][0]["reason"],
            "ambiguous_no_dataset_expansion",
        )

    def test_join_endpoints_prevent_bare_key_from_adding_another_table(self) -> None:
        plan = self._plan(joins=[JoinRequirement(
            left_dataset="orders.csv",
            right_dataset="payments.csv",
            join_keys=["order_id"],
            how="left",
            left_grain="One row per order",
            right_grain="Payment rows per order",
            relationship="one_to_many",
        )])
        usage = infer_plan_dataset_usage(
            plan,
            [ORDERS_PROFILE, PAYMENTS_PROFILE, ITEMS_PROFILE],
            [],
        )
        self.assertEqual(usage["used_datasets"], ["orders", "payments"])

    def test_filter_dataset_is_authoritative(self) -> None:
        plan = self._plan(filters=[PlanFilter(
            dataset="reviews.csv",
            column="review_score",
            operator="lt",
            value=3,
        )])
        usage = infer_plan_dataset_usage(
            plan,
            [ORDERS_PROFILE, ITEMS_PROFILE, REVIEWS_PROFILE],
            [],
        )
        self.assertIn("reviews", usage["used_datasets"])

    def test_qualified_reference_identifies_its_dataset(self) -> None:
        plan = self._plan(required_columns=["items.csv.order_id"])
        usage = infer_plan_dataset_usage(plan, [ORDERS_PROFILE, ITEMS_PROFILE], [])
        self.assertEqual(usage["used_datasets"], ["items"])

    def test_unique_profile_match_can_bind_bare_column(self) -> None:
        plan = self._plan(required_columns=["review_score"])
        usage = infer_plan_dataset_usage(plan, [ORDERS_PROFILE, REVIEWS_PROFILE], [])
        self.assertEqual(usage["used_datasets"], ["reviews"])

    def test_explicit_unconnected_dataset_remains_blocked(self) -> None:
        plan = self._plan(
            required_columns=[
                "orders.csv.order_id",
                "payments.csv.payment_value",
                "reviews.csv.review_score",
            ],
            joins=[JoinRequirement(
                left_dataset="orders.csv",
                right_dataset="payments.csv",
                join_keys=["order_id"],
                how="left",
                left_grain="One row per order",
                right_grain="Payment rows per order",
                relationship="one_to_many",
            )],
        )
        report = evaluate_plan_completeness(
            plan,
            [ORDERS_PROFILE, PAYMENTS_PROFILE, REVIEWS_PROFILE],
            [],
        )
        self.assertIn("missing_join_requirement", {item.code for item in report.issues})

    def test_rmc_alternative_bindings_are_not_all_expanded(self) -> None:
        payload = _ready_plan(
            metric_ids=["ecommerce.payment_gmv"],
            metrics=[_metric(metric_id="ecommerce.payment_gmv")],
            joins=[JoinRequirement(
                left_dataset="orders.csv",
                right_dataset="payments.csv",
                join_keys=["order_id"],
                how="left",
                left_grain="One row per order",
                right_grain="Payment rows per order",
                relationship="one_to_many",
            )],
        ).model_dump(mode="json")
        candidate = {
            "metric_id": "ecommerce.payment_gmv",
            "required_bindings": {
                "order_id": [
                    {"dataset": "orders.csv", "column": "order_id"},
                    {"dataset": "payments.csv", "column": "order_id"},
                    {"dataset": "items.csv", "column": "order_id"},
                ],
                "paid_amount": [
                    {"dataset": "payments.csv", "column": "payment_value"},
                ],
            },
        }
        normalized = normalize_plan_payload(
            payload,
            [candidate],
            [ORDERS_PROFILE, PAYMENTS_PROFILE, ITEMS_PROFILE],
        )
        columns = normalized.normalized_payload["required_columns"]
        self.assertIn("payments.csv.payment_value", columns)
        self.assertNotIn("items.csv.order_id", columns)


class PlannerReplanTest(unittest.IsolatedAsyncioTestCase):
    async def test_replan_once_then_pass(self) -> None:
        incomplete = _ready_plan(metrics=[]).model_dump(mode="json")
        complete = _ready_plan().model_dump(mode="json")
        with patch(
            "app.services.plan_service._request_planner_payload",
            AsyncMock(side_effect=[_payload(incomplete), _payload(complete)]),
        ) as request:
            outcome = await generate_analysis_plan(
                "Calculate total value",
                [ORDERS_PROFILE],
                [],
                [],
                model="test-model",
            )

        plan = outcome.plan
        metadata = outcome.metadata
        self.assertEqual(request.await_count, 2)
        self.assertTrue(metadata["replanned"])
        self.assertEqual(metadata["attempt_count"], 2)
        self.assertTrue(metadata["completeness"]["ready_for_code_generation"])
        self.assertIsNotNone(plan)
        self.assertEqual(plan.metrics[0].key, "total_value")

    async def test_replan_once_then_still_fails(self) -> None:
        incomplete = _ready_plan(metrics=[]).model_dump(mode="json")
        with patch(
            "app.services.plan_service._request_planner_payload",
            AsyncMock(side_effect=[_payload(incomplete), _payload(incomplete)]),
        ) as request:
            outcome = await generate_analysis_plan(
                "Calculate total value",
                [ORDERS_PROFILE],
                [],
                [],
                model="test-model",
            )

        metadata = outcome.metadata
        self.assertEqual(request.await_count, 2)
        self.assertEqual(metadata["planner"], "llm_structured_output_incomplete")
        self.assertFalse(metadata["completeness"]["ready_for_code_generation"])
        self.assertIn(
            "missing_metrics",
            {item["code"] for item in metadata["completeness"]["issues"]},
        )

    async def test_schema_invalid_plan_preserves_partial_semantics_and_fails_closed(self) -> None:
        partial = _ready_plan().model_dump(mode="json")
        partial["analysis_scope"] = "Delivered orders in 2017"
        partial["filters"] = [{
            "dataset": "orders.csv",
            "column": "order_status",
            "operator": ">",
            "value": 1,
        }]
        partial["metrics"][0].update({
            "metric_type": "ratio",
            "numerator": {
                "description": "Selected orders",
                "aggregation": None,
                "filters": [],
            },
            "denominator": {
                "description": "All orders",
                "aggregation": "count_distinct(order_id)",
                "filters": [],
            },
        })
        with patch(
            "app.services.plan_service._request_planner_payload",
            AsyncMock(side_effect=[_payload(partial), _payload(partial)]),
        ) as request:
            outcome = await generate_analysis_plan(
                "Calculate a filtered ratio",
                [ORDERS_PROFILE],
                [],
                [],
                model="test-model",
            )

        self.assertEqual(request.await_count, 2)
        self.assertIsNone(outcome.plan)
        self.assertEqual(outcome.metadata["planner"], "llm_structured_output_invalid")
        self.assertFalse(outcome.metadata["completeness"]["schema_valid"])
        self.assertEqual(outcome.normalized_partial_payload["analysis_scope"], "Delivered orders in 2017")
        self.assertEqual(outcome.normalized_partial_payload["metrics"][0]["key"], "total_value")
        self.assertEqual(outcome.normalized_partial_payload["filters"][0]["operator"], "gt")
        self.assertIn(
            "unresolved_operand_aggregation",
            {item.code for item in outcome.unresolved_issues},
        )


if __name__ == "__main__":
    unittest.main()
