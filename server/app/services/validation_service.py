"""Deterministic validation for generated analysis artifacts."""

import math
import re
from typing import Any, Dict, Iterable, List, Optional

from app.schemas.analysis import AnalysisPlan, AnalysisResult, ValidationCheck, ValidationReport


NUMBER_PATTERN = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _flatten_numbers(value: Any) -> List[float]:
    numbers: List[float] = []
    if isinstance(value, bool) or value is None:
        return numbers
    if isinstance(value, (int, float)):
        if math.isfinite(float(value)):
            numbers.append(float(value))
    elif isinstance(value, dict):
        for nested in value.values():
            numbers.extend(_flatten_numbers(nested))
    elif isinstance(value, list):
        for nested in value:
            numbers.extend(_flatten_numbers(nested))
    return numbers


def _number_is_supported(candidate: float, allowed: Iterable[float]) -> bool:
    return any(math.isclose(candidate, value, rel_tol=1e-6, abs_tol=1e-6) for value in allowed)


def validate_execution_artifact(
    plan: AnalysisPlan,
    execution_result: Dict[str, Any],
    available_columns: List[str],
    metric_matches: List[Dict[str, Any]],
    visualization_required: bool = False,
) -> ValidationReport:
    checks: List[ValidationCheck] = []
    status = execution_result.get("status")
    checks.append(ValidationCheck(
        name="sandbox_execution",
        status="pass" if status == "success" else "fail",
        message="Sandbox execution succeeded." if status == "success" else "Sandbox execution failed.",
    ))

    available_lookup = {column.lower(): column for column in available_columns}
    missing_columns = [column for column in plan.required_columns if column.lower() not in available_lookup]
    checks.append(ValidationCheck(
        name="required_columns",
        status="pass" if not missing_columns else "fail",
        message=(
            "All planned columns are available."
            if not missing_columns
            else f"Planned columns are missing: {', '.join(missing_columns)}"
        ),
    ))

    structured = execution_result.get("structured_result")
    if structured:
        try:
            result = AnalysisResult.model_validate(structured)
            structured_status = "pass"
            structured_message = "Sandbox returned a valid AnalysisResult."
        except ValueError as error:
            result = None
            structured_status = "fail"
            structured_message = f"AnalysisResult validation failed: {error}"
    else:
        result = None
        structured_status = "fail"
        structured_message = "Sandbox did not return the required structured AnalysisResult."
    checks.append(ValidationCheck(
        name="structured_result",
        status=structured_status,
        message=structured_message,
    ))

    retrieved_ids = {match["id"] for match in metric_matches}
    invalid_metric_ids = [metric_id for metric_id in plan.metric_ids if metric_id not in retrieved_ids]
    checks.append(ValidationCheck(
        name="metric_grounding",
        status="pass" if not invalid_metric_ids else "fail",
        message=(
            "Planned metrics are grounded in retrieved definitions."
            if not invalid_metric_ids
            else f"Plan referenced metrics that were not retrieved: {', '.join(invalid_metric_ids)}"
        ),
    ))

    if result:
        result_metric_valid = not result.metric_id or result.metric_id in retrieved_ids
        checks.append(ValidationCheck(
            name="result_metric_grounding",
            status="pass" if result_metric_valid else "fail",
            message=(
                "The result metric is grounded in the retrieved definitions or correctly left empty."
                if result_metric_valid
                else f"Result referenced an unretrieved metric: {result.metric_id}"
            ),
        ))
        unknown_used = [column for column in result.columns_used if column.lower() not in available_lookup]
        checks.append(ValidationCheck(
            name="reported_columns",
            status="pass" if not unknown_used else "fail",
            message=(
                "Reported evidence columns exist in the uploaded data."
                if not unknown_used
                else f"Result reported unknown columns: {', '.join(unknown_used)}"
            ),
        ))
        if result.answer_type == "number" and result.primary_value is None:
            checks.append(ValidationCheck(
                name="primary_value",
                status="fail",
                message="Numeric answer is missing primary_value.",
            ))
        else:
            checks.append(ValidationCheck(
                name="primary_value",
                status="pass",
                message="Primary answer value matches the declared answer type.",
            ))
        visualization_valid = (
            not visualization_required
            or bool(result.datasets and result.visualizations)
        )
        checks.append(ValidationCheck(
            name="visualization_contract",
            status="pass" if visualization_valid else "fail",
            message=(
                "The requested dashboard is backed by structured datasets and approved visualization specifications."
                if visualization_valid
                else "The user requested visualization, but the result did not include structured datasets and visualization specifications."
            ),
        ))

    failed = sum(check.status == "fail" for check in checks)
    warnings = sum(check.status == "warning" for check in checks)
    confidence = "high" if failed == 0 and warnings == 0 else "medium" if failed == 0 else "low"
    return ValidationReport(passed=failed == 0, confidence=confidence, checks=checks)


def validate_final_answer(
    final_answer: str,
    analysis_result: Optional[Dict[str, Any]],
    raw_output: str,
    question: str,
) -> ValidationReport:
    checks: List[ValidationCheck] = []
    allowed = _flatten_numbers(analysis_result or {})
    allowed.extend(float(value) for value in NUMBER_PATTERN.findall(raw_output))
    allowed.extend(float(value) for value in NUMBER_PATTERN.findall(question))
    answer_numbers = [float(value) for value in NUMBER_PATTERN.findall(final_answer)]
    unsupported = sorted({value for value in answer_numbers if not _number_is_supported(value, allowed)})

    checks.append(ValidationCheck(
        name="numeric_faithfulness",
        status="pass" if not unsupported else "fail",
        message=(
            "Every number in the final answer is grounded in the question or sandbox artifact."
            if not unsupported
            else f"Final answer introduced unsupported numbers: {unsupported}"
        ),
    ))
    return ValidationReport(
        passed=not unsupported,
        confidence="high" if not unsupported else "low",
        checks=checks,
        unsupported_numbers=unsupported,
    )


def render_grounded_fallback(result: Optional[Dict[str, Any]], raw_output: str) -> str:
    if not result:
        return raw_output
    parsed = AnalysisResult.model_validate(result)
    lines = [parsed.summary]
    if parsed.answer_type == "number" and parsed.primary_value is not None:
        suffix = f" {parsed.unit}" if parsed.unit else ""
        lines.append(f"\n**Result:** {parsed.primary_value}{suffix}")
    if parsed.assumptions:
        lines.append("\n**Assumptions and limitations**")
        lines.extend(f"- {item}" for item in parsed.assumptions)
    return "\n".join(lines)


def render_validation_failure(
    report: ValidationReport,
    execution_result: Dict[str, Any],
    repair_attempts: int,
    question: str,
) -> str:
    """Render a user-facing explanation instead of exposing raw sandbox protocol."""
    is_chinese = bool(re.search(r"[\u4e00-\u9fff]", question))
    failed_names = {check.name for check in report.checks if check.status == "fail"}

    issue_copy = {
        "sandbox_execution": (
            "沙箱代码没有成功执行。",
            "检查生成代码中的字段名、类型转换和依赖，并根据错误信息重新生成。",
            "The sandbox code did not execute successfully.",
            "Check generated column names, type conversions, and dependencies, then regenerate from the execution error.",
        ),
        "required_columns": (
            "分析计划引用了数据中不存在的字段。",
            "重新匹配上传文件的真实字段名，或补充问题中缺失的字段定义。",
            "The analysis plan referenced columns that are not present in the data.",
            "Remap the plan to actual uploaded columns or clarify the missing field definition.",
        ),
        "structured_result": (
            "沙箱完成了计算，但没有返回符合约定的结构化结果。",
            "让生成代码按 AnalysisResult 格式返回结果；表格数据放入 rows，primary_value 仅保留标量。",
            "The sandbox completed computation but did not return a valid structured result.",
            "Return the AnalysisResult contract; put table records in rows and keep primary_value scalar.",
        ),
        "metric_grounding": (
            "分析计划使用了未检索到定义的业务指标。",
            "先确认指标口径，或改用数据字段可以直接支持的计算。",
            "The plan used a business metric without a retrieved definition.",
            "Confirm the metric definition first or use a calculation directly supported by the dataset.",
        ),
        "result_metric_grounding": (
            "计算结果引用的指标与已检索指标不一致。",
            "将结果中的 metric_id 改为已检索指标；非业务指标计算应设为空。",
            "The result referenced a metric that was not retrieved.",
            "Use a retrieved metric_id, or leave it empty for an ad hoc calculation.",
        ),
        "reported_columns": (
            "执行结果报告了上传数据中不存在的字段。",
            "只在 columns_used 中填写实际参与计算的 CSV 字段。",
            "The result reported columns that are not in the uploaded data.",
            "Only include real CSV columns used by the computation in columns_used.",
        ),
        "primary_value": (
            "主结果的类型与声明的答案类型不匹配。",
            "数值答案返回标量；表格答案将记录放入 rows。",
            "The primary result does not match the declared answer type.",
            "Return a scalar for numeric answers and records in rows for table answers.",
        ),
        "visualization_contract": (
            "问题要求数据看板或图表，但沙箱结果没有返回完整的结构化可视化数据。",
            "在 result.datasets 中返回图表数据，并在 result.visualizations 中使用受支持的图表类型和真实字段名。",
            "The question requested a dashboard or chart, but the sandbox did not return a complete structured visualization artifact.",
            "Return chart data in result.datasets and use supported chart types with real field names in result.visualizations.",
        ),
    }

    issues = [issue_copy[name] for name in failed_names if name in issue_copy]
    if not issues:
        issues = [(
            "结果没有通过完整性验证。",
            "检查执行日志和生成代码后重新运行。",
            "The result did not pass integrity validation.",
            "Review the execution log and generated code, then run again.",
        )]

    if is_chinese:
        lines = ["本次分析未通过可信验证，因此没有把计算结果作为最终结论发布。", "", "**可能原因**"]
        lines.extend(f"- {item[0]}" for item in issues)
        if execution_result.get("status") == "error":
            preview = str(execution_result.get("content", "")).strip().splitlines()[0][:240]
            if preview:
                lines.append(f"- 沙箱错误摘要：{preview}")
        lines.extend(["", "**建议修改**"])
        lines.extend(f"- {item[1]}" for item in issues)
        if repair_attempts:
            lines.append(f"- 系统已自动修复并重试 {repair_attempts} 次，仍未通过验证；建议展开执行轨迹定位具体步骤。")
        return "\n".join(lines)

    lines = ["This analysis did not pass trusted validation, so its computed output was not published as a final conclusion.", "", "**Possible causes**"]
    lines.extend(f"- {item[2]}" for item in issues)
    if execution_result.get("status") == "error":
        preview = str(execution_result.get("content", "")).strip().splitlines()[0][:240]
        if preview:
            lines.append(f"- Sandbox error: {preview}")
    lines.extend(["", "**Suggested changes**"])
    lines.extend(f"- {item[3]}" for item in issues)
    if repair_attempts:
        lines.append(f"- Automatic repair was attempted {repair_attempts} time(s) without passing validation; inspect the workflow trace for the failing step.")
    return "\n".join(lines)
