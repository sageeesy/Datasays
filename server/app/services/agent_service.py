"""Evidence-first data analysis agent built around typed workflow artifacts."""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.schemas.analysis import AnalysisPlan, ValidationReport
from app.services.code_service import contains_image_generation, generate_code, repair_code
from app.services.file_service import load_metadata, save_metadata
from app.services.llm_service import polish_sandbox_output
from app.services.metric_service import compact_metric_match, retrieve_metric_definitions
from app.services.plan_service import generate_analysis_plan
from app.services.profile_service import build_dataset_profile, compact_profile
from app.services.sandbox_service import execute_code
from app.services.skill_service import compact_skill, select_analysis_skills
from app.services.validation_service import (
    render_grounded_fallback,
    render_validation_failure,
    validate_execution_artifact,
    validate_final_answer,
)


AgentStep = Dict[str, Any]


def _is_non_repairable_execution_error(execution_result: Dict[str, Any]) -> bool:
    content = str(execution_result.get("content", "")).lower()
    return any(marker in content for marker in (
        "sandbox configuration error",
        "docker not found",
        "docker daemon",
        "docker image",
        "file not found error",
    ))


def _visualization_requested(question: str) -> bool:
    return any(term in question.lower() for term in (
        "chart", "dashboard", "visualization", "visualisation", "plot", "graph",
        "heatmap", "histogram", "box plot", "scatter", "看板", "图表", "可视化",
        "热力图", "直方图", "箱线图", "散点图", "趋势图",
    ))


def _preview(value: Any, limit: int = 1200) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, indent=2)
    else:
        text = str(value)
    return text if len(text) <= limit else text[:limit] + "... [truncated]"


def _record_step(
    steps: List[AgentStep],
    node: str,
    tool: str,
    rationale: str,
    status: str,
    observation: Any,
    args: Optional[Dict[str, Any]] = None,
    duration_ms: Optional[int] = None,
) -> None:
    steps.append({
        "step": len(steps) + 1,
        "node": node,
        "tool": tool,
        "thought": rationale,
        "args": args or {},
        "status": status,
        "observation": _preview(observation),
        "duration_ms": duration_ms,
    })


async def _load_profiled_files(file_ids: List[str]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    file_headers: List[Dict[str, Any]] = []
    profiles: List[Dict[str, Any]] = []

    for file_id in file_ids:
        metadata = await load_metadata(file_id)
        if not metadata:
            raise ValueError(f"File {file_id} not found")

        profile = metadata.get("profile")
        if not profile:
            file_path = metadata.get("filePath")
            if not file_path or not Path(file_path).exists():
                raise ValueError(f"File path for {file_id} is unavailable")
            profile = build_dataset_profile(file_path, metadata.get("originalName"))
            metadata["profile"] = profile
            await save_metadata(metadata)

        compact = compact_profile(profile)
        profiles.append(compact)
        file_headers.append({
            "fileId": metadata["id"],
            "fileName": metadata["originalName"],
            "headers": metadata["headers"],
            "rows": metadata["rows"],
            "columns": metadata["columns"],
            "profile": compact,
        })

    return file_headers, profiles


def _workflow_metadata(
    steps: List[AgentStep],
    profiles: List[Dict[str, Any]],
    skills: List[Dict[str, Any]],
    metric_matches: List[Dict[str, Any]],
    plan: AnalysisPlan,
    planner_metadata: Dict[str, Any],
    execution_attempts: List[Dict[str, Any]],
    max_repair_attempts: int,
    validation: Optional[ValidationReport] = None,
    final_validation: Optional[ValidationReport] = None,
    analysis_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "agent_mode": True,
        "agent_framework": "bounded_typed_workflow",
        "agent_steps": steps,
        "dataset_profiles": profiles,
        "selected_skills": [
            {
                "id": skill["id"],
                "name": skill["name"],
                "guidance": skill["description"],
                "matched_terms": skill.get("matched_terms", []),
                "selection_mode": "keyword_match" if skill.get("matched_terms") else "default_fallback",
            }
            for skill in skills
        ],
        "retrieved_metrics": metric_matches,
        "retrieval_method": "alias_keyword_with_schema_binding",
        "plan": plan.model_dump(mode="json"),
        "planner": planner_metadata,
        "validation_report": validation.model_dump(mode="json") if validation else None,
        "final_answer_validation": final_validation.model_dump(mode="json") if final_validation else None,
        "analysis_result": analysis_result,
        "repair_attempts": len([item for item in execution_attempts if item["stage"] == "repair"]),
        "max_repair_attempts": max_repair_attempts,
        "execution_attempts": execution_attempts,
    }


async def run_data_analysis_agent(
    question: str,
    file_ids: List[str],
    prompt_style: str = "zero",
    model: str | None = None,
) -> Dict[str, Any]:
    steps: List[AgentStep] = []

    started = time.perf_counter()
    file_headers, profiles = await _load_profiled_files(file_ids)
    _record_step(
        steps,
        node="profile_data",
        tool="profile_dataset",
        rationale="Build a typed schema and quality profile before selecting an analysis path.",
        status="success",
        observation=profiles,
        args={"file_ids": file_ids},
        duration_ms=round((time.perf_counter() - started) * 1000),
    )

    started = time.perf_counter()
    selected_skills = select_analysis_skills(question)
    compact_skills = [compact_skill(skill) for skill in selected_skills]
    _record_step(
        steps,
        node="select_skills",
        tool="select_analysis_playbooks",
        rationale="Select a small set of analysis and validation playbooks that match the question.",
        status="success",
        observation=compact_skills,
        args={"question": question},
        duration_ms=round((time.perf_counter() - started) * 1000),
    )

    started = time.perf_counter()
    retrieved = retrieve_metric_definitions(question, profiles)
    metric_matches = [compact_metric_match(match) for match in retrieved]
    _record_step(
        steps,
        node="retrieve_metrics",
        tool="retrieve_metric_definition",
        rationale="Retrieve business definitions and bind their logical fields to the uploaded schema.",
        status="success" if metric_matches else "skipped",
        observation=metric_matches or "No domain metric was required; continue with schema-grounded analysis.",
        args={"method": "alias_keyword_with_schema_binding", "limit": 4},
        duration_ms=round((time.perf_counter() - started) * 1000),
    )

    started = time.perf_counter()
    plan, planner_metadata = await generate_analysis_plan(
        question=question,
        profiles=profiles,
        metric_matches=metric_matches,
        skills=compact_skills,
        model=model,
    )
    _record_step(
        steps,
        node="plan_analysis",
        tool="generate_structured_plan",
        rationale="Create a typed plan grounded in the dataset profile and retrieved metric definitions.",
        status="success",
        observation=plan.model_dump(mode="json"),
        args={"planner": planner_metadata.get("planner")},
        duration_ms=round((time.perf_counter() - started) * 1000),
    )

    max_repair_attempts = int(os.getenv("CODE_REPAIR_ATTEMPTS", "2"))
    execution_attempts: List[Dict[str, Any]] = []
    if plan.needs_clarification:
        message = plan.clarification_question or "The analysis needs one business-definition clarification before it can run."
        _record_step(
            steps,
            node="request_clarification",
            tool="clarify_metric_or_schema",
            rationale="Stop before calculation because the ambiguity would materially change the answer.",
            status="success",
            observation=message,
        )
        return {
            "content": message,
            "code": None,
            "thinking_process": "A clarification is required before calculation.",
            "status": "success",
            "output": None,
            "metadata": _workflow_metadata(
                steps, profiles, selected_skills, metric_matches, plan, planner_metadata,
                execution_attempts, max_repair_attempts,
            ),
        }

    analysis_context = {
        "plan": plan.model_dump(mode="json"),
        "metrics": metric_matches,
        "skills": compact_skills,
        "result_contract": {
            "marker": "__DATASAYS_RESULT__",
            "required_fields": [
                "answer_type", "primary_value", "unit", "summary", "rows",
                "columns_used", "metric_id", "assumptions", "insights",
                "datasets", "visualizations",
            ],
            "visualization_policy": (
                "Compute chart-ready structured data only. Never generate images or use plotting libraries. "
                "The frontend renders approved visualization specs."
            ),
        },
    }

    started = time.perf_counter()
    code_result = await generate_code(
        question,
        file_headers,
        prompt_style,
        model,
        analysis_context=analysis_context,
    )
    code = code_result["code"]
    reasoning_summary = code_result.get("thinking_process", "")
    repair_notes: List[str] = []
    _record_step(
        steps,
        node="generate_code",
        tool="write_analysis_code",
        rationale="Generate executable pandas code that follows the typed plan and result contract.",
        status="success",
        observation=code,
        args={"prompt_style": prompt_style},
        duration_ms=round((time.perf_counter() - started) * 1000),
    )

    if contains_image_generation(code):
        started = time.perf_counter()
        repair_result = await repair_code(
            question=question,
            file_headers=file_headers,
            previous_code=code,
            execution_error=(
                "Pre-execution visualization policy violation: the sandbox must calculate structured datasets only. "
                "Remove matplotlib, seaborn, plotly, PIL, graphviz, show(), savefig(), and all image generation. "
                "Return chart-ready datasets and approved visualization specifications instead."
            ),
            prompt_style=prompt_style,
            attempt_number=1,
            model=model,
            analysis_context=analysis_context,
        )
        code = repair_result["code"]
        repair_summary = repair_result.get("thinking_process", "")
        if repair_summary:
            repair_notes.append(f"Visualization policy rewrite: {repair_summary}")
        _record_step(
            steps,
            node="repair_code",
            tool="enforce_structured_visualization_policy",
            rationale="Replace image-rendering code with chart-ready structured calculations before sandbox execution.",
            status="success" if not contains_image_generation(code) else "error",
            observation=code,
            args={"attempt": 1, "reason": "visualization_policy"},
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        if contains_image_generation(code):
            message = (
                "未能生成符合可信分析要求的计算代码：代码仍包含图片或绘图库。"
                "系统没有执行这段代码，也没有将它标记为已验证。请重试，或明确要求返回结构化统计结果。"
            )
            return {
                "content": message,
                "code": code,
                "thinking_process": "\n\n".join(part for part in [reasoning_summary, *repair_notes] if part),
                "status": "error",
                "output": None,
                "metadata": _workflow_metadata(
                    steps, profiles, selected_skills, metric_matches, plan, planner_metadata,
                    execution_attempts, max_repair_attempts,
                ),
            }

    available_columns = [column for file in file_headers for column in file["headers"]]
    execution_result: Optional[Dict[str, Any]] = None
    validation: Optional[ValidationReport] = None

    for attempt in range(max_repair_attempts + 1):
        if contains_image_generation(code):
            execution_result = {
                "status": "error",
                "content": "Generated repair still contained prohibited image-rendering code and was not executed.",
                "structured_result": None,
            }
            validation = validate_execution_artifact(
                plan, execution_result, available_columns, metric_matches,
                visualization_required=_visualization_requested(question),
            )
            execution_attempts.append({
                "attempt": attempt,
                "stage": "repair",
                "status": "error",
                "validation_passed": False,
                "validation_confidence": validation.confidence,
                "error_preview": execution_result["content"],
            })
            _record_step(
                steps,
                node="execute_code",
                tool="run_python_code",
                rationale="Reject image-rendering code before sandbox execution.",
                status="error",
                observation=execution_result["content"],
                args={"attempt": attempt, "file_ids": file_ids},
            )
            break
        started = time.perf_counter()
        execution_result = await execute_code(code, file_ids, load_metadata)
        validation = validate_execution_artifact(
            plan, execution_result, available_columns, metric_matches,
            visualization_required=_visualization_requested(question),
        )
        execution_attempts.append({
            "attempt": attempt,
            "stage": "initial_generation" if attempt == 0 else "repair",
            "status": execution_result.get("status", "error"),
            "validation_passed": validation.passed,
            "validation_confidence": validation.confidence,
            "error_preview": (
                execution_result.get("content", "")[:500]
                if execution_result.get("status") == "error" or not validation.passed
                else None
            ),
        })
        _record_step(
            steps,
            node="execute_code",
            tool="run_python_code",
            rationale="Run the generated code in the isolated sandbox and capture a typed artifact.",
            status=execution_result.get("status", "error"),
            observation=execution_result.get("content", ""),
            args={"attempt": attempt, "file_ids": file_ids},
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        _record_step(
            steps,
            node="validate_result",
            tool="validate_result",
            rationale="Check execution, planned columns, metric grounding, and the structured result contract.",
            status="success" if validation.passed else "error",
            observation=validation.model_dump(mode="json"),
            args={"attempt": attempt},
        )

        if validation.passed:
            break
        if _is_non_repairable_execution_error(execution_result):
            break
        if attempt >= max_repair_attempts:
            break

        validation_feedback = json.dumps(validation.model_dump(mode="json"), ensure_ascii=False, indent=2)
        started = time.perf_counter()
        repair_result = await repair_code(
            question=question,
            file_headers=file_headers,
            previous_code=code,
            execution_error=f"{execution_result.get('content', '')}\n\nVALIDATION REPORT\n{validation_feedback}",
            prompt_style=prompt_style,
            attempt_number=attempt + 1,
            model=model,
            analysis_context=analysis_context,
        )
        code = repair_result["code"]
        repair_summary = repair_result.get("thinking_process", "")
        if repair_summary:
            repair_notes.append(f"Repair {attempt + 1}: {repair_summary}")
        _record_step(
            steps,
            node="repair_code",
            tool="repair_code",
            rationale="Repair the code using sandbox and deterministic validation feedback.",
            status="success",
            observation=code,
            args={"attempt": attempt + 1},
            duration_ms=round((time.perf_counter() - started) * 1000),
        )

    if execution_result is None or validation is None:
        raise ValueError("Agent execution did not produce an execution artifact")

    raw_output = execution_result.get("content", "")
    structured_result = execution_result.get("structured_result")
    final_content = raw_output
    final_validation: Optional[ValidationReport] = None
    final_status = "success" if validation.passed else "error"

    if validation.passed:
        evidence_context = {
            "metric_ids": plan.metric_ids,
            "assumptions": plan.assumptions,
            "validation_confidence": validation.confidence,
        }
        final_content = await polish_sandbox_output(
            question=question,
            sandbox_output=raw_output,
            execution_status="success",
            model=model,
            structured_result=structured_result,
            evidence_context=evidence_context,
        )
        final_validation = validate_final_answer(final_content, structured_result, raw_output, question)
        if not final_validation.passed:
            final_content = render_grounded_fallback(structured_result, raw_output)
    else:
        final_content = render_validation_failure(
            validation,
            execution_result,
            len([item for item in execution_attempts if item["stage"] == "repair"]),
            question,
        )

    _record_step(
        steps,
        node="final_report",
        tool="render_evidence_first_answer",
        rationale="Render the answer and reject any unsupported number introduced during wording polish.",
        status=final_status,
        observation={
            "answer": final_content,
            "numeric_faithfulness": final_validation.model_dump(mode="json") if final_validation else None,
        },
        args={"format": "markdown"},
    )

    metadata = _workflow_metadata(
        steps=steps,
        profiles=profiles,
        skills=selected_skills,
        metric_matches=metric_matches,
        plan=plan,
        planner_metadata=planner_metadata,
        execution_attempts=execution_attempts,
        max_repair_attempts=max_repair_attempts,
        validation=validation,
        final_validation=final_validation,
        analysis_result=structured_result,
    )

    return {
        "content": final_content,
        "code": code,
        "thinking_process": "\n\n".join(part for part in [reasoning_summary, *repair_notes] if part),
        "status": final_status,
        "output": execution_result.get("output"),
        "metadata": metadata,
    }
