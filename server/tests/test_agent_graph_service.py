import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from app.schemas.analysis import AnalysisPlan, PlanGenerationOutcome, PlannedMetric, ValidationReport
from app.services import agent_service


class AgentGraphServiceTest(unittest.IsolatedAsyncioTestCase):
    def test_graph_exposes_planning_execution_validation_and_repair_nodes(self) -> None:
        nodes = set(agent_service.build_agent_graph().nodes)
        self.assertTrue({
            "profile_data",
            "load_memory",
            "select_skills",
            "retrieve_metrics",
            "plan_analysis",
            "generate_code",
            "execute_code",
            "validate_result",
            "repair_code",
            "finalize_response",
        }.issubset(nodes))

    def test_validation_router_retries_only_repairable_failures_within_budget(self) -> None:
        base_state = {
            "validation": ValidationReport(passed=False, confidence="low", checks=[]).model_dump(mode="json"),
            "execution_result": {"status": "error", "content": "NameError: value is not defined"},
            "attempt": 0,
            "max_repair_attempts": 2,
        }
        self.assertEqual(agent_service._route_after_validation(base_state), "repair_code")
        self.assertEqual(
            agent_service._route_after_validation({**base_state, "attempt": 2}),
            "finalize_response",
        )
        self.assertEqual(
            agent_service._route_after_validation({
                **base_state,
                "execution_result": {"status": "error", "content": "Docker daemon unavailable"},
            }),
            "finalize_response",
        )

    async def test_stream_emits_real_node_events_and_persists_checkpoints(self) -> None:
        profile_headers = [{
            "fileId": "file-1",
            "fileName": "demo.csv",
            "headers": ["group", "value"],
            "rows": 2,
            "columns": 2,
            "profile": {},
        }]
        profiles = [{
            "file_name": "demo.csv",
            "row_count": 2,
            "column_count": 2,
            "columns": [{"name": "group"}, {"name": "value"}],
        }]
        skills = [{
            "id": "descriptive",
            "name": "Descriptive Analysis",
            "description": "Summarize grouped values",
            "matched_terms": ["group"],
        }]
        structured_result = {
            "answer_type": "number",
            "primary_value": 2.0,
            "unit": None,
            "summary": "Mean is 2.00",
            "rows": [],
            "columns_used": ["group", "value"],
            "metric_id": None,
            "assumptions": [],
            "insights": [],
            "datasets": [],
            "visualizations": [],
        }
        passed = ValidationReport(passed=True, confidence="high", checks=[])

        retrieve_metrics = Mock(return_value=[])

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"DATASAYS_CHECKPOINT_PATH": str(Path(directory) / "checkpoints.db")},
        ), patch.object(
            agent_service, "_load_profiled_files", AsyncMock(return_value=(profile_headers, profiles))
        ), patch.object(
            agent_service, "select_analysis_skills", return_value=skills
        ), patch.object(
            agent_service, "compact_skill", side_effect=lambda skill: skill
        ), patch.object(
            agent_service, "retrieve_metric_definitions", retrieve_metrics
        ), patch.object(
            agent_service,
            "generate_analysis_plan",
            AsyncMock(return_value=PlanGenerationOutcome(
                plan=AnalysisPlan(
                    intent="aggregation",
                    analysis_scope="All rows in demo.csv",
                    entity_grain="One row per group value",
                    required_columns=["group", "value"],
                    metrics=[PlannedMetric(
                        key="mean_value",
                        label="Mean value",
                        metric_type="average",
                        definition="Average value across rows",
                        calculation="Calculate mean(value)",
                    )],
                    steps=["Group rows", "Calculate the mean"],
                ),
                metadata={"planner": "test"},
            )),
        ), patch.object(
            agent_service,
            "generate_code",
            AsyncMock(return_value={"code": "print(2)", "thinking_process": "Calculate the grouped mean."}),
        ), patch.object(
            agent_service,
            "execute_code",
            AsyncMock(return_value={
                "status": "success",
                "content": "2.00",
                "structured_result": structured_result,
                "output": {"type": "number", "data": 2.0},
            }),
        ), patch.object(
            agent_service, "validate_execution_artifact", return_value=passed
        ), patch.object(
            agent_service, "polish_sandbox_output", AsyncMock(return_value="Mean is 2.00.")
        ), patch.object(
            agent_service, "validate_final_answer", return_value=passed
        ):
            events = [
                event
                async for event in agent_service.stream_data_analysis_agent(
                    "What is the mean by group?",
                    ["file-1"],
                    graph_thread_id="test-run",
                    project_id="olist",
                )
            ]

            completed_nodes = [
                event["node"] for event in events
                if event.get("status") == "completed" and event.get("node")
            ]
            self.assertEqual(completed_nodes[:5], [
                "profile_data", "load_memory", "select_skills", "retrieve_metrics", "plan_analysis",
            ])
            self.assertIn("execute_code", completed_nodes)
            self.assertIn("validate_result", completed_nodes)
            self.assertEqual(events[-1]["type"], "result")
            self.assertEqual(events[-1]["data"]["metadata"]["agent_framework"], "langgraph_stategraph")
            self.assertEqual(events[-1]["data"]["metadata"]["project_id"], "olist")
            self.assertGreater(events[-1]["data"]["metadata"]["checkpoint_count"], 1)
            self.assertTrue((Path(directory) / "checkpoints.db").exists())
            retrieve_metrics.assert_called_once_with(
                "What is the mean by group?",
                profiles,
                project_id="olist",
            )

    async def test_incomplete_plan_stops_before_code_generation(self) -> None:
        profile_headers = [{
            "fileId": "file-1",
            "fileName": "demo.csv",
            "headers": ["group", "value"],
            "rows": 2,
            "columns": 2,
            "profile": {},
        }]
        profiles = [{
            "file_name": "demo.csv",
            "row_count": 2,
            "column_count": 2,
            "columns": [{"name": "group"}, {"name": "value"}],
        }]
        generate_code = AsyncMock()

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"DATASAYS_CHECKPOINT_PATH": str(Path(directory) / "checkpoints.db")},
        ), patch.object(
            agent_service, "_load_profiled_files", AsyncMock(return_value=(profile_headers, profiles))
        ), patch.object(
            agent_service, "select_analysis_skills", return_value=[]
        ), patch.object(
            agent_service, "retrieve_metric_definitions", return_value=[]
        ), patch.object(
            agent_service,
            "generate_analysis_plan",
            AsyncMock(return_value=PlanGenerationOutcome(
                plan=AnalysisPlan(intent="aggregation"),
                metadata={
                    "planner": "llm_structured_output_incomplete",
                    "attempt_count": 2,
                },
            )),
        ), patch.object(
            agent_service, "generate_code", generate_code
        ):
            events = [
                event
                async for event in agent_service.stream_data_analysis_agent(
                    "What is the mean by group?",
                    ["file-1"],
                    graph_thread_id="incomplete-plan-run",
                )
            ]

        generate_code.assert_not_awaited()
        self.assertEqual(events[-1]["data"]["status"], "error")
        self.assertIn("没有生成或执行代码", events[-1]["data"]["content"])


if __name__ == "__main__":
    unittest.main()
