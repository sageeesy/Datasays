"""LangGraph workflow for evidence-first data analysis."""

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Literal, Optional

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.schemas.analysis import AnalysisPlan, PlanCompletenessReport, ValidationReport
from app.services.code_service import contains_image_generation, generate_code, repair_code
from app.services.file_service import load_metadata, save_metadata
from app.services.llm_service import polish_sandbox_output
from app.services.metric_service import (
    compact_metric_match,
    resolved_metric_candidate,
    retrieve_metric_definitions,
)
from app.services.memory_service import summarize_conversation_context
from app.services.plan_service import evaluate_plan_completeness, generate_analysis_plan
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
ProgressEvent = Dict[str, Any]


class AgentState(TypedDict, total=False):
    """Serializable state persisted after every LangGraph node."""

    question: str
    file_ids: List[str]
    prompt_style: str
    model: Optional[str]
    project_id: Optional[str]
    conversation_context: Optional[Dict[str, Any]]
    graph_thread_id: str
    steps: List[AgentStep]
    file_headers: List[Dict[str, Any]]
    profiles: List[Dict[str, Any]]
    memory_summary: Dict[str, Any]
    selected_skills: List[Dict[str, Any]]
    compact_skills: List[Dict[str, Any]]
    metric_matches: List[Dict[str, Any]]
    resolved_metric_candidates: List[Dict[str, Any]]
    plan: Dict[str, Any]
    planner_metadata: Dict[str, Any]
    analysis_context: Dict[str, Any]
    code: str
    reasoning_summary: str
    repair_notes: List[str]
    execution_result: Dict[str, Any]
    validation: Dict[str, Any]
    final_validation: Optional[Dict[str, Any]]
    execution_attempts: List[Dict[str, Any]]
    attempt: int
    max_repair_attempts: int
    terminal_reason: Optional[str]
    terminal_message: Optional[str]
    response: Dict[str, Any]


def _is_non_repairable_execution_error(execution_result: Dict[str, Any]) -> bool:
    content = str(execution_result.get("content", "")).lower()
    return any(marker in content for marker in (
        "sandbox configuration error",
        "docker not found",
        "docker daemon",
        "docker image",
        "file not found error",
        "no module named 'pandas'",
        "no module named 'numpy'",
        "no module named 'scipy'",
        "no module named 'sklearn'",
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


def _checkpoint_path() -> Path:
    path = Path(os.getenv("DATASAYS_CHECKPOINT_PATH", "./data/agent-checkpoints.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _workflow_metadata(state: AgentState) -> Dict[str, Any]:
    validation = state.get("validation")
    final_validation = state.get("final_validation")
    execution_attempts = state.get("execution_attempts", [])
    selected_skills = state.get("selected_skills", [])
    return {
        "agent_mode": True,
        "agent_framework": "langgraph_stategraph",
        "graph_thread_id": state["graph_thread_id"],
        "checkpoint_backend": "sqlite",
        "checkpoint_scope": "one_thread_per_analysis_run",
        "project_id": state.get("project_id"),
        "agent_steps": state.get("steps", []),
        "dataset_profiles": state.get("profiles", []),
        "selected_skills": [
            {
                "id": skill["id"],
                "name": skill["name"],
                "guidance": skill["description"],
                "matched_terms": skill.get("matched_terms", []),
                "selection_mode": "keyword_match" if skill.get("matched_terms") else "default_fallback",
            }
            for skill in selected_skills
        ],
        "retrieved_metrics": state.get("metric_matches", []),
        "resolved_metric_candidates": state.get("resolved_metric_candidates", []),
        "retrieval_method": "alias_keyword_with_schema_binding",
        "plan": state.get("plan", {}),
        "planner": state.get("planner_metadata", {}),
        "validation_report": validation,
        "final_answer_validation": final_validation,
        "analysis_result": (state.get("execution_result") or {}).get("structured_result"),
        "repair_attempts": len([item for item in execution_attempts if item["stage"] == "repair"]),
        "max_repair_attempts": state.get("max_repair_attempts", 0),
        "execution_attempts": execution_attempts,
        "memory": state.get("memory_summary") or summarize_conversation_context(None),
    }


async def _profile_data(state: AgentState) -> Dict[str, Any]:
    steps = list(state.get("steps", []))
    started = time.perf_counter()
    file_headers, profiles = await _load_profiled_files(state["file_ids"])
    _record_step(
        steps, "profile_data", "profile_dataset",
        "Build a typed schema and quality profile before selecting an analysis path.",
        "success", profiles, {"file_ids": state["file_ids"]},
        round((time.perf_counter() - started) * 1000),
    )
    return {"steps": steps, "file_headers": file_headers, "profiles": profiles}


async def _load_memory(state: AgentState) -> Dict[str, Any]:
    steps = list(state["steps"])
    summary = summarize_conversation_context(state.get("conversation_context"))
    _record_step(
        steps, "load_memory", "build_conversation_context",
        "Load bounded recent dialogue and verified findings scoped to the current datasets.",
        "success" if summary["used"] else "skipped", summary,
        {"trusted_runs_only": True, "dataset_scoped": True},
    )
    return {"steps": steps, "memory_summary": summary}


async def _select_skills(state: AgentState) -> Dict[str, Any]:
    steps = list(state["steps"])
    started = time.perf_counter()
    selected = select_analysis_skills(state["question"])
    compact = [compact_skill(skill) for skill in selected]
    _record_step(
        steps, "select_skills", "select_analysis_playbooks",
        "Select a small set of analysis and validation playbooks that match the question.",
        "success", compact, {"question": state["question"]},
        round((time.perf_counter() - started) * 1000),
    )
    return {"steps": steps, "selected_skills": selected, "compact_skills": compact}


async def _retrieve_metrics(state: AgentState) -> Dict[str, Any]:
    steps = list(state["steps"])
    started = time.perf_counter()
    retrieved = retrieve_metric_definitions(
        state["question"],
        state["profiles"],
        project_id=state.get("project_id"),
    )
    matches = [compact_metric_match(match) for match in retrieved]
    resolved_candidates = [resolved_metric_candidate(match) for match in retrieved]
    _record_step(
        steps, "retrieve_metrics", "retrieve_metric_definition",
        "Retrieve business definitions and bind their logical fields to the uploaded schema.",
        "success" if matches else "skipped",
        matches or "No domain metric was required; continue with schema-grounded analysis.",
        {
            "method": "alias_keyword_with_schema_binding",
            "limit": 4,
            "project_id": state.get("project_id"),
        },
        round((time.perf_counter() - started) * 1000),
    )
    return {
        "steps": steps,
        "metric_matches": matches,
        "resolved_metric_candidates": resolved_candidates,
    }


async def _plan_analysis(state: AgentState) -> Dict[str, Any]:
    steps = list(state["steps"])
    started = time.perf_counter()
    outcome = await generate_analysis_plan(
        question=state["question"],
        profiles=state["profiles"],
        metric_matches=state["resolved_metric_candidates"],
        skills=state["compact_skills"],
        model=state.get("model"),
        conversation_context=state.get("conversation_context"),
    )
    plan = outcome.plan
    planner_metadata = outcome.metadata
    plan_data = (
        plan.model_dump(mode="json")
        if plan is not None
        else outcome.normalized_partial_payload
    )
    if plan is not None:
        completeness = evaluate_plan_completeness(
            plan,
            state["profiles"],
            state["resolved_metric_candidates"],
        )
    else:
        completeness = PlanCompletenessReport.model_validate(
            planner_metadata.get("completeness") or {
                "schema_valid": False,
                "ready_for_code_generation": False,
                "valid_clarification": False,
                "issues": [],
            }
        )
    planner_metadata = {
        **planner_metadata,
        "completeness": completeness.model_dump(mode="json"),
        "canonical_plan_present": plan is not None,
        "normalized_partial_payload": outcome.normalized_partial_payload,
        "normalization_actions": [
            item.model_dump(mode="json") for item in outcome.normalization_actions
        ],
        "validation_errors": outcome.validation_errors,
        "unresolved_issues": [
            item.model_dump(mode="json") for item in outcome.unresolved_issues
        ],
    }
    incomplete = not completeness.ready_for_code_generation and not completeness.valid_clarification
    _record_step(
        steps, "plan_analysis", "generate_structured_plan",
        "Create a typed plan grounded in the dataset profile and retrieved metric definitions.",
        "error" if incomplete else "success",
        {
            "plan": plan_data,
            "completeness": completeness.model_dump(mode="json"),
        },
        {"planner": planner_metadata.get("planner")},
        round((time.perf_counter() - started) * 1000),
    )
    update: Dict[str, Any] = {
        "steps": steps,
        "plan": plan_data,
        "planner_metadata": planner_metadata,
    }
    if incomplete:
        missing = "；".join(item.message for item in completeness.issues[:4])
        update.update({
            "terminal_reason": "plan_incomplete",
            "terminal_message": (
                "分析计划在一次自动重试后仍不完整，因此没有生成或执行代码。"
                f"缺失或冲突项：{missing or '计划未满足可执行条件'}"
            ),
        })
    return update


def _route_after_plan(state: AgentState) -> Literal["request_clarification", "generate_code", "finalize_response"]:
    if state.get("terminal_reason") == "plan_incomplete":
        return "finalize_response"
    return "request_clarification" if state["plan"].get("needs_clarification") else "generate_code"


async def _request_clarification(state: AgentState) -> Dict[str, Any]:
    steps = list(state["steps"])
    message = state["plan"].get("clarification_question") or "继续分析前，需要先澄清一个会影响计算口径的问题。"
    _record_step(
        steps, "request_clarification", "clarify_metric_or_schema",
        "Stop before calculation because the ambiguity would materially change the answer.",
        "success", message,
    )
    return {"steps": steps, "terminal_reason": "clarification", "terminal_message": message}


def _analysis_context(state: AgentState) -> Dict[str, Any]:
    context: Dict[str, Any] = {
        "plan": state["plan"],
        "metrics": state["metric_matches"],
        "skills": state["compact_skills"],
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
    if state["memory_summary"]["used"]:
        context["conversation_memory"] = state.get("conversation_context")
    return context


async def _generate_code(state: AgentState) -> Dict[str, Any]:
    steps = list(state["steps"])
    started = time.perf_counter()
    context = _analysis_context(state)
    result = await generate_code(
        state["question"], state["file_headers"], state["prompt_style"],
        state.get("model"), analysis_context=context,
    )
    code = result["code"]
    _record_step(
        steps, "generate_code", "write_analysis_code",
        "Generate executable pandas code that follows the typed plan and result contract.",
        "success", code, {"prompt_style": state["prompt_style"]},
        round((time.perf_counter() - started) * 1000),
    )
    return {
        "steps": steps,
        "analysis_context": context,
        "code": code,
        "reasoning_summary": result.get("thinking_process", ""),
    }


def _route_after_generation(state: AgentState) -> Literal["repair_visualization_policy", "execute_code"]:
    return "repair_visualization_policy" if contains_image_generation(state["code"]) else "execute_code"


async def _repair_visualization_policy(state: AgentState) -> Dict[str, Any]:
    steps = list(state["steps"])
    notes = list(state.get("repair_notes", []))
    started = time.perf_counter()
    result = await repair_code(
        question=state["question"],
        file_headers=state["file_headers"],
        previous_code=state["code"],
        execution_error=(
            "Pre-execution visualization policy violation: the sandbox must calculate structured datasets only. "
            "Remove plotting and image-generation libraries. Return chart-ready datasets and approved "
            "visualization specifications instead."
        ),
        prompt_style=state["prompt_style"],
        attempt_number=1,
        model=state.get("model"),
        analysis_context=state["analysis_context"],
    )
    code = result["code"]
    if result.get("thinking_process"):
        notes.append(f"Visualization policy rewrite: {result['thinking_process']}")
    still_invalid = contains_image_generation(code)
    _record_step(
        steps, "repair_visualization_policy", "enforce_structured_visualization_policy",
        "Replace image-rendering code with chart-ready structured calculations before sandbox execution.",
        "error" if still_invalid else "success", code,
        {"attempt": 1, "reason": "visualization_policy"},
        round((time.perf_counter() - started) * 1000),
    )
    result_update: Dict[str, Any] = {"steps": steps, "code": code, "repair_notes": notes}
    if still_invalid:
        result_update.update({
            "terminal_reason": "visualization_policy",
            "terminal_message": (
                "未能生成符合可信分析要求的计算代码：代码仍包含图片或绘图库。"
                "系统没有执行这段代码，也没有将它标记为已验证。请重试，或明确要求返回结构化统计结果。"
            ),
        })
    return result_update


def _route_after_policy_repair(state: AgentState) -> Literal["finalize_response", "execute_code"]:
    return "finalize_response" if state.get("terminal_reason") else "execute_code"


async def _execute_code(state: AgentState) -> Dict[str, Any]:
    steps = list(state["steps"])
    attempt = state.get("attempt", 0)
    started = time.perf_counter()
    if contains_image_generation(state["code"]):
        result = {
            "status": "error",
            "content": "Generated repair still contained prohibited image-rendering code and was not executed.",
            "structured_result": None,
        }
    else:
        result = await execute_code(state["code"], state["file_ids"], load_metadata)
    _record_step(
        steps, "execute_code", "run_python_code",
        "Run the generated code in the isolated sandbox and capture a typed artifact.",
        result.get("status", "error"), result.get("content", ""),
        {"attempt": attempt, "file_ids": state["file_ids"]},
        round((time.perf_counter() - started) * 1000),
    )
    return {"steps": steps, "execution_result": result}


async def _validate_result(state: AgentState) -> Dict[str, Any]:
    steps = list(state["steps"])
    attempts = list(state.get("execution_attempts", []))
    attempt = state.get("attempt", 0)
    plan = AnalysisPlan.model_validate(state["plan"])
    available_columns = [column for item in state["file_headers"] for column in item["headers"]]
    validation = validate_execution_artifact(
        plan,
        state["execution_result"],
        available_columns,
        state["metric_matches"],
        visualization_required=_visualization_requested(state["question"]),
        dataset_columns={item["fileName"]: item["headers"] for item in state["file_headers"]},
    )
    attempts.append({
        "attempt": attempt,
        "stage": "initial_generation" if attempt == 0 else "repair",
        "status": state["execution_result"].get("status", "error"),
        "validation_passed": validation.passed,
        "validation_confidence": validation.confidence,
        "error_preview": (
            state["execution_result"].get("content", "")[:500]
            if state["execution_result"].get("status") == "error" or not validation.passed
            else None
        ),
    })
    _record_step(
        steps, "validate_result", "validate_result",
        "Check execution, planned columns, metric grounding, and the structured result contract.",
        "success" if validation.passed else "error",
        validation.model_dump(mode="json"), {"attempt": attempt},
    )
    return {
        "steps": steps,
        "validation": validation.model_dump(mode="json"),
        "execution_attempts": attempts,
    }


def _route_after_validation(state: AgentState) -> Literal["repair_code", "finalize_response"]:
    validation = ValidationReport.model_validate(state["validation"])
    if validation.passed:
        return "finalize_response"
    if _is_non_repairable_execution_error(state["execution_result"]):
        return "finalize_response"
    if state.get("attempt", 0) >= state["max_repair_attempts"]:
        return "finalize_response"
    return "repair_code"


async def _repair_code(state: AgentState) -> Dict[str, Any]:
    steps = list(state["steps"])
    notes = list(state.get("repair_notes", []))
    next_attempt = state.get("attempt", 0) + 1
    feedback = json.dumps(state["validation"], ensure_ascii=False, indent=2)
    started = time.perf_counter()
    result = await repair_code(
        question=state["question"],
        file_headers=state["file_headers"],
        previous_code=state["code"],
        execution_error=f"{state['execution_result'].get('content', '')}\n\nVALIDATION REPORT\n{feedback}",
        prompt_style=state["prompt_style"],
        attempt_number=next_attempt,
        model=state.get("model"),
        analysis_context=state["analysis_context"],
    )
    code = result["code"]
    if result.get("thinking_process"):
        notes.append(f"Repair {next_attempt}: {result['thinking_process']}")
    _record_step(
        steps, "repair_code", "repair_code",
        "Repair the code using sandbox and deterministic validation feedback.",
        "success", code, {"attempt": next_attempt},
        round((time.perf_counter() - started) * 1000),
    )
    return {"steps": steps, "code": code, "repair_notes": notes, "attempt": next_attempt}


async def _finalize_response(state: AgentState) -> Dict[str, Any]:
    steps = list(state["steps"])
    terminal_reason = state.get("terminal_reason")
    final_validation: Optional[ValidationReport] = None

    if terminal_reason:
        content = state.get("terminal_message") or "分析已停止。"
        status = "success" if terminal_reason == "clarification" else "error"
        code = state.get("code")
        output = None
    else:
        validation = ValidationReport.model_validate(state["validation"])
        execution_result = state["execution_result"]
        raw_output = execution_result.get("content", "")
        structured_result = execution_result.get("structured_result")
        status = "success" if validation.passed else "error"
        code = state.get("code")
        output = execution_result.get("output")

        if validation.passed:
            content = await polish_sandbox_output(
                question=state["question"],
                sandbox_output=raw_output,
                execution_status="success",
                model=state.get("model"),
                structured_result=structured_result,
                evidence_context={
                    "metric_ids": state["plan"].get("metric_ids", []),
                    "assumptions": state["plan"].get("assumptions", []),
                    "validation_confidence": validation.confidence,
                },
            )
            final_validation = validate_final_answer(content, structured_result, raw_output, state["question"])
            if not final_validation.passed:
                content = render_grounded_fallback(structured_result, raw_output)
        else:
            content = render_validation_failure(
                validation,
                execution_result,
                len([item for item in state.get("execution_attempts", []) if item["stage"] == "repair"]),
                state["question"],
            )

        _record_step(
            steps, "finalize_response", "render_evidence_first_answer",
            "Render the answer and reject any unsupported number introduced during wording polish.",
            status,
            {
                "answer": content,
                "numeric_faithfulness": final_validation.model_dump(mode="json") if final_validation else None,
            },
            {"format": "markdown"},
        )

    next_state: AgentState = dict(state)
    next_state["steps"] = steps
    next_state["final_validation"] = final_validation.model_dump(mode="json") if final_validation else None
    response = {
        "content": content,
        "code": code,
        "thinking_process": "\n\n".join(
            part for part in [state.get("reasoning_summary", ""), *state.get("repair_notes", [])] if part
        ),
        "status": status,
        "output": output,
    }
    next_state["response"] = response
    response["metadata"] = _workflow_metadata(next_state)
    return {"steps": steps, "final_validation": next_state["final_validation"], "response": response}


def build_agent_graph() -> StateGraph:
    """Build the inspectable graph definition without binding storage."""
    graph = StateGraph(AgentState)
    graph.add_node("profile_data", _profile_data)
    graph.add_node("load_memory", _load_memory)
    graph.add_node("select_skills", _select_skills)
    graph.add_node("retrieve_metrics", _retrieve_metrics)
    graph.add_node("plan_analysis", _plan_analysis)
    graph.add_node("request_clarification", _request_clarification)
    graph.add_node("generate_code", _generate_code)
    graph.add_node("repair_visualization_policy", _repair_visualization_policy)
    graph.add_node("execute_code", _execute_code)
    graph.add_node("validate_result", _validate_result)
    graph.add_node("repair_code", _repair_code)
    graph.add_node("finalize_response", _finalize_response)

    graph.add_edge(START, "profile_data")
    graph.add_edge("profile_data", "load_memory")
    graph.add_edge("load_memory", "select_skills")
    graph.add_edge("select_skills", "retrieve_metrics")
    graph.add_edge("retrieve_metrics", "plan_analysis")
    graph.add_conditional_edges("plan_analysis", _route_after_plan)
    graph.add_edge("request_clarification", "finalize_response")
    graph.add_conditional_edges("generate_code", _route_after_generation)
    graph.add_conditional_edges("repair_visualization_policy", _route_after_policy_repair)
    graph.add_edge("execute_code", "validate_result")
    graph.add_conditional_edges("validate_result", _route_after_validation)
    graph.add_edge("repair_code", "execute_code")
    graph.add_edge("finalize_response", END)
    return graph


NODE_TITLES: Dict[str, tuple[str, str]] = {
    "profile_data": ("读取数据画像", "Profile datasets"),
    "load_memory": ("加载可信记忆", "Load trusted memory"),
    "select_skills": ("选择分析技能", "Select analysis skills"),
    "retrieve_metrics": ("检索指标定义", "Retrieve metric definitions"),
    "plan_analysis": ("制定分析计划", "Build analysis plan"),
    "request_clarification": ("请求口径澄清", "Request clarification"),
    "generate_code": ("生成分析代码", "Generate analysis code"),
    "repair_visualization_policy": ("修正可视化协议", "Repair visualization policy"),
    "execute_code": ("运行 Python 沙箱", "Execute Python sandbox"),
    "validate_result": ("验证执行结果", "Validate execution result"),
    "repair_code": ("自动修复代码", "Repair analysis code"),
    "finalize_response": ("整理可信答案", "Prepare verified answer"),
}


def _progress_detail(node: str, payload: Dict[str, Any], completed: bool) -> tuple[str, str]:
    if not completed:
        attempt = payload.get("attempt", 0)
        suffix_zh = f"（第 {attempt + 1} 次尝试）" if node in {"execute_code", "validate_result"} else ""
        suffix_en = f" (attempt {attempt + 1})" if suffix_zh else ""
        return f"正在执行该步骤{suffix_zh}", f"Running this step{suffix_en}"

    if node == "profile_data":
        profiles = payload.get("profiles", [])
        names = [item.get("file_name") or item.get("name") for item in profiles]
        return f"已读取 {len(profiles)} 个数据集：{', '.join(filter(None, names))}", f"Profiled {len(profiles)} dataset(s): {', '.join(filter(None, names))}"
    if node == "load_memory":
        memory = payload.get("memory_summary", {})
        if not memory.get("used"):
            return "当前问题未使用历史结论，将独立完成分析。", "No prior findings were used for this analysis."
        return (
            f"已加载 {memory.get('recent_message_count', 0)} 条近期消息和 {memory.get('verified_finding_count', 0)} 条已验证结论。",
            f"Loaded {memory.get('recent_message_count', 0)} recent messages and {memory.get('verified_finding_count', 0)} verified findings.",
        )
    if node == "select_skills":
        skills = payload.get("compact_skills", [])
        names = [item.get("name") for item in skills if item.get("name")]
        reasons = sorted({term for item in skills for term in item.get("matched_terms", [])})
        reason_zh = f"，匹配依据：{', '.join(reasons)}" if reasons else "，作为通用分析与校验基线"
        reason_en = f"; matched: {', '.join(reasons)}" if reasons else "; selected as the general analysis baseline"
        return f"选择了 {', '.join(names) or '通用分析 skill'}{reason_zh}。", f"Selected {', '.join(names) or 'general analysis skills'}{reason_en}."
    if node == "retrieve_metrics":
        metrics = payload.get("metric_matches", [])
        names = [((item.get("metric") or {}).get("name")) for item in metrics]
        if not any(names):
            return "未命中特定业务指标，按数据字段与问题语义继续。", "No domain metric matched; continuing with schema-grounded analysis."
        return f"命中指标定义：{', '.join(filter(None, names))}。", f"Retrieved metric definitions: {', '.join(filter(None, names))}."
    if node == "plan_analysis":
        plan = payload.get("plan", {})
        steps = plan.get("steps", [])
        columns = plan.get("required_columns", [])
        zh = f"分析类型：{plan.get('intent', 'other')}；字段：{', '.join(columns) or '由代码确定'}；计划：{'；'.join(steps[:3]) or '生成可验证计算'}。"
        en = f"Intent: {plan.get('intent', 'other')}; columns: {', '.join(columns) or 'resolved in code'}; plan: {'; '.join(steps[:3]) or 'produce a verifiable calculation'}."
        return zh, en
    if node == "generate_code":
        return "已根据结构化计划生成 Python 计算代码，下一步进入隔离沙箱。", "Generated Python from the structured plan; next it runs in the isolated sandbox."
    if node in {"repair_visualization_policy", "repair_code"}:
        attempt = payload.get("attempt")
        return f"已根据验证反馈生成修复版本{f'（第 {attempt} 次）' if attempt else ''}。", f"Generated a repaired version from validation feedback{f' (repair {attempt})' if attempt else ''}."
    if node == "execute_code":
        result = payload.get("execution_result", {})
        ok = result.get("status") == "success"
        return ("沙箱执行成功，正在检查结构化结果。" if ok else "沙箱执行失败，正在判断是否可以自动修复。", "Sandbox execution succeeded; validating the structured result." if ok else "Sandbox execution failed; checking whether an automatic repair is possible.")
    if node == "validate_result":
        validation = payload.get("validation", {})
        if validation.get("passed"):
            return f"验证通过，置信度为 {validation.get('confidence', 'unknown')}。", f"Validation passed with {validation.get('confidence', 'unknown')} confidence."
        failed = [item.get("message") for item in validation.get("checks", []) if item.get("status") == "fail"]
        return f"验证未通过：{failed[0] if failed else '结果未满足可信输出协议'}", f"Validation failed: {failed[0] if failed else 'the result did not satisfy the verified-output contract'}"
    if node == "request_clarification":
        return payload.get("terminal_message", "需要补充业务口径。"), payload.get("terminal_message", "A business-definition clarification is required.")
    if node == "finalize_response":
        response = payload.get("response", {})
        return ("可信答案与证据已整理完成。" if response.get("status") == "success" else "分析已结束，并保留了失败原因与修复建议。", "Verified answer and evidence are ready." if response.get("status") == "success" else "Analysis finished with the failure reason and repair guidance preserved.")
    return "该步骤已完成。", "Step completed."


def _public_progress_event(node: str, status: str, payload: Dict[str, Any], event_id: str) -> ProgressEvent:
    title_zh, title_en = NODE_TITLES.get(node, (node, node))
    detail_zh, detail_en = _progress_detail(node, payload, status != "running")
    return {
        "id": event_id,
        "node": node,
        "status": status,
        "title_zh": title_zh,
        "title_en": title_en,
        "detail_zh": detail_zh,
        "detail_en": detail_en,
        "timestamp": time.time(),
    }


async def stream_data_analysis_agent(
    question: str,
    file_ids: List[str],
    prompt_style: str = "zero",
    model: str | None = None,
    conversation_context: Optional[Dict[str, Any]] = None,
    graph_thread_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> AsyncIterator[ProgressEvent]:
    """Run the graph and yield bounded public progress events plus one result."""
    thread_id = graph_thread_id or str(uuid.uuid4())
    initial_state: AgentState = {
        "question": question,
        "file_ids": file_ids,
        "prompt_style": prompt_style,
        "model": model,
        "project_id": project_id,
        "conversation_context": conversation_context,
        "graph_thread_id": thread_id,
        "steps": [],
        "repair_notes": [],
        "execution_attempts": [],
        "attempt": 0,
        "max_repair_attempts": int(os.getenv("CODE_REPAIR_ATTEMPTS", "2")),
        "terminal_reason": None,
        "terminal_message": None,
    }
    config = {"configurable": {"thread_id": thread_id}}
    yield {
        "type": "run_started",
        "graph_thread_id": thread_id,
        "status": "running",
        "timestamp": time.time(),
    }

    checkpoint_path = _checkpoint_path()
    async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        graph = build_agent_graph().compile(checkpointer=checkpointer)
        async for chunk in graph.astream(
            initial_state,
            config=config,
            stream_mode=["tasks"],
            version="v2",
        ):
            if chunk.get("type") != "tasks":
                continue
            data = chunk.get("data", {})
            node = data.get("name")
            if not node or node not in NODE_TITLES:
                continue
            event_id = data.get("id") or str(uuid.uuid4())
            if "result" not in data and "error" not in data:
                yield _public_progress_event(node, "running", data.get("input") or {}, event_id)
                continue
            status = "error" if data.get("error") else "completed"
            yield _public_progress_event(node, status, data.get("result") or {}, event_id)

        snapshot = await graph.aget_state(config)
        response = snapshot.values.get("response")
        if not response:
            raise RuntimeError("LangGraph run completed without a final response")
        checkpoint_count = 0
        async for _ in checkpointer.alist(config):
            checkpoint_count += 1
        response.setdefault("metadata", {})["checkpoint_count"] = checkpoint_count
        response["metadata"]["checkpoint_path"] = checkpoint_path.name
        yield {
            "type": "result",
            "graph_thread_id": thread_id,
            "status": response.get("status", "error"),
            "data": response,
            "timestamp": time.time(),
        }


async def run_data_analysis_agent(
    question: str,
    file_ids: List[str],
    prompt_style: str = "zero",
    model: str | None = None,
    conversation_context: Optional[Dict[str, Any]] = None,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Compatibility wrapper for non-streaming callers."""
    result: Optional[Dict[str, Any]] = None
    async for event in stream_data_analysis_agent(
        question,
        file_ids,
        prompt_style,
        model,
        conversation_context=conversation_context,
        project_id=project_id,
    ):
        if event.get("type") == "result":
            result = event["data"]
    if result is None:
        raise RuntimeError("Agent run did not return a result")
    return result
