"""Build bounded, evidence-aware context for follow-up analysis turns."""

import json
from typing import Any, Dict, List, Optional

from app.services.conversation_service import get_conversation, list_analysis_runs


MAX_RECENT_MESSAGES = 8
MAX_VERIFIED_FINDINGS = 5
MAX_CONTEXT_CHARS = 12000
MAX_MESSAGE_CHARS = 1200
MAX_SUMMARY_CHARS = 1000
MAX_ROWS_PREVIEW = 5


def _clip(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[:limit] + "..."


def _normalized_names(names: List[str]) -> set[str]:
    return {name.strip().lower() for name in names if name and name.strip()}


def _assistant_content(message: Dict[str, Any]) -> Optional[str]:
    response = message.get("sandboxResponse") or message.get("llmResponse") or {}
    if response.get("status") != "success":
        return None
    return _clip(response.get("content"), MAX_MESSAGE_CHARS) or None


def _dataset_names(metadata: Dict[str, Any]) -> List[str]:
    return [
        str(profile.get("file_name"))
        for profile in metadata.get("dataset_profiles", [])
        if isinstance(profile, dict) and profile.get("file_name")
    ]


def _verified_finding(
    run: Dict[str, Any],
    current_file_names: set[str],
) -> Optional[Dict[str, Any]]:
    response = run.get("response", {}).get("sandboxResponse") or {}
    if response.get("status") != "success":
        return None

    metadata = response.get("metadata") or {}
    result = metadata.get("analysis_result")
    validation = metadata.get("validation_report") or {}
    if not isinstance(result, dict) or validation.get("passed") is not True:
        return None

    dataset_names = _dataset_names(metadata)
    prior_files = _normalized_names(dataset_names)
    if current_file_names and (not prior_files or current_file_names.isdisjoint(prior_files)):
        return None

    plan = metadata.get("plan") or {}
    rows = result.get("rows") if isinstance(result.get("rows"), list) else []
    return {
        "run_id": run.get("id"),
        "question": _clip(run.get("question"), MAX_MESSAGE_CHARS),
        "dataset_names": dataset_names,
        "summary": _clip(result.get("summary"), MAX_SUMMARY_CHARS),
        "answer_type": result.get("answer_type"),
        "primary_value": result.get("primary_value"),
        "unit": result.get("unit"),
        "metric_id": result.get("metric_id"),
        "columns_used": result.get("columns_used", []),
        "assumptions": result.get("assumptions", [])[:6],
        "insights": result.get("insights", [])[:5],
        "rows_preview": rows[:MAX_ROWS_PREVIEW],
        "plan": {
            "intent": plan.get("intent"),
            "dimensions": plan.get("dimensions", []),
            "filters": plan.get("filters", []),
            "aggregation": plan.get("aggregation"),
            "time_grain": plan.get("time_grain"),
        },
    }


def _context_size(context: Dict[str, Any]) -> int:
    return len(json.dumps(context, ensure_ascii=False, default=str))


def build_conversation_context(
    conversation_id: str,
    current_file_names: Optional[List[str]] = None,
    exclude_message_id: Optional[str] = None,
    max_recent_messages: int = MAX_RECENT_MESSAGES,
    max_verified_findings: int = MAX_VERIFIED_FINDINGS,
) -> Dict[str, Any]:
    """Return recent dialogue plus verified findings scoped to the current files."""
    conversation = get_conversation(conversation_id)
    if not conversation:
        return {"recent_messages": [], "verified_findings": [], "source_run_ids": []}

    current_files = _normalized_names(current_file_names or [])
    recent_messages: List[Dict[str, Any]] = []
    include_following_assistant = True
    for message in conversation.get("messages", []):
        if message.get("id") == exclude_message_id:
            continue
        if message.get("type") == "user":
            message_files = _normalized_names(message.get("filesUsed", []))
            include_following_assistant = not (
                current_files and message_files and current_files.isdisjoint(message_files)
            )
            if not include_following_assistant:
                continue
            content = _clip(message.get("content"), MAX_MESSAGE_CHARS)
            role = "user"
        else:
            if not include_following_assistant:
                continue
            content = _assistant_content(message)
            role = "assistant"
        if content:
            recent_messages.append({"role": role, "content": content})
    recent_messages = recent_messages[-max_recent_messages:]

    verified_findings: List[Dict[str, Any]] = []
    for run in reversed(list_analysis_runs(conversation_id, verified_only=True)):
        finding = _verified_finding(run, current_files)
        if finding:
            verified_findings.append(finding)
        if len(verified_findings) >= max_verified_findings:
            break

    context = {
        "recent_messages": recent_messages,
        "verified_findings": verified_findings,
        "source_run_ids": [item["run_id"] for item in verified_findings if item.get("run_id")],
        "usage_rules": [
            "Use prior context only to resolve follow-up references and preserve explicitly stated scope.",
            "Current user instructions and current dataset profiles override prior context.",
            "Recompute requested values from the current files; prior findings are context, not substitute evidence.",
            "Do not carry filters or assumptions forward unless the current question clearly depends on them.",
        ],
    }

    while _context_size(context) > MAX_CONTEXT_CHARS and context["recent_messages"]:
        context["recent_messages"].pop(0)
    while _context_size(context) > MAX_CONTEXT_CHARS and context["verified_findings"]:
        context["verified_findings"].pop()
        context["source_run_ids"] = [
            item["run_id"] for item in context["verified_findings"] if item.get("run_id")
        ]
    return context


def summarize_conversation_context(context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    context = context or {}
    return {
        "used": bool(context.get("recent_messages") or context.get("verified_findings")),
        "recent_message_count": len(context.get("recent_messages", [])),
        "verified_finding_count": len(context.get("verified_findings", [])),
        "source_run_ids": context.get("source_run_ids", []),
    }
