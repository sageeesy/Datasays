"""Verified analysis query routes, including real-time Agent progress."""

import json
from typing import Any, AsyncIterator, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.agent_service import run_data_analysis_agent, stream_data_analysis_agent
from app.services.conversation_service import get_conversation, save_analysis_exchange, save_message
from app.services.file_service import load_metadata
from app.services.memory_service import build_conversation_context

router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    fileIds: List[str]
    model: Optional[str] = None
    prompt_style: Optional[str] = "zero"  # zero, zero_cot, sub_question
    mode: Literal["agent"] = "agent"
    conversationId: Optional[str] = None
    userMessageId: Optional[str] = None


class ResponseData(BaseModel):
    content: str
    code: Optional[str] = None
    thinking_process: Optional[str] = None
    status: str
    output: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class QueryResponse(BaseModel):
    success: bool
    llmResponse: ResponseData
    sandboxResponse: ResponseData


async def _prepare_query(request: QueryRequest) -> Dict[str, Any]:
    if not request.question or not request.fileIds:
        raise HTTPException(
            status_code=400,
            detail="Missing required fields: question and fileIds are required",
        )
    if request.conversationId and not get_conversation(request.conversationId):
        raise HTTPException(status_code=404, detail="Conversation not found")

    file_names: List[str] = []
    for file_id in request.fileIds:
        metadata = await load_metadata(file_id)
        if not metadata:
            raise HTTPException(status_code=404, detail=f"File {file_id} not found")
        file_names.append(metadata["originalName"])

    user_message_id = request.userMessageId
    if request.conversationId:
        user_message_id = save_message(
            conversation_id=request.conversationId,
            role="user",
            content=request.question,
            message_id=user_message_id,
            file_names=file_names,
        )

    conversation_context = None
    if request.conversationId:
        conversation_context = build_conversation_context(
            conversation_id=request.conversationId,
            current_file_names=file_names,
            exclude_message_id=user_message_id,
        )
    return {
        "file_names": file_names,
        "user_message_id": user_message_id,
        "conversation_context": conversation_context,
        "prompt_style": request.prompt_style or "zero",
        "model": request.model or None,
    }


def _response_envelope(sandbox_response: Dict[str, Any]) -> QueryResponse:
    return QueryResponse(
        success=True,
        llmResponse=ResponseData(
            content=sandbox_response["content"],
            status=sandbox_response["status"],
        ),
        sandboxResponse=ResponseData(
            content=sandbox_response["content"],
            code=sandbox_response.get("code"),
            thinking_process=sandbox_response.get("thinking_process"),
            status=sandbox_response["status"],
            output=sandbox_response.get("output"),
            metadata=sandbox_response.get("metadata"),
        ),
    )


def _persist_response(request: QueryRequest, prepared: Dict[str, Any], response: QueryResponse) -> None:
    if request.conversationId and prepared["user_message_id"]:
        save_analysis_exchange(
            conversation_id=request.conversationId,
            user_message_id=prepared["user_message_id"],
            question=request.question,
            file_names=prepared["file_names"],
            model=prepared["model"],
            prompt_style=prepared["prompt_style"],
            response=response.model_dump(mode="json"),
        )


def _sse(event: str, payload: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"


@router.post("", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """Run one evidence-first analysis and persist its artifacts."""
    try:
        prepared = await _prepare_query(request)
        sandbox_response = await run_data_analysis_agent(
            request.question,
            request.fileIds,
            prepared["prompt_style"],
            prepared["model"],
            conversation_context=prepared["conversation_context"],
        )
        response = _response_envelope(sandbox_response)
        _persist_response(request, prepared, response)
        return response
    except HTTPException:
        raise
    except Exception as e:
        if request.conversationId and get_conversation(request.conversationId):
            save_message(
                conversation_id=request.conversationId,
                role="assistant",
                content="",
                llm_response={"content": f"Error: {e}", "status": "error"},
                sandbox_response={"content": f"Error: {e}", "status": "error"},
            )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def stream_query(request: QueryRequest, http_request: Request):
    """Stream real LangGraph node events and finish with the stable response envelope."""
    prepared = await _prepare_query(request)

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in stream_data_analysis_agent(
                request.question,
                request.fileIds,
                prepared["prompt_style"],
                prepared["model"],
                conversation_context=prepared["conversation_context"],
            ):
                if await http_request.is_disconnected():
                    return
                if event.get("type") == "result":
                    response = _response_envelope(event["data"])
                    _persist_response(request, prepared, response)
                    yield _sse("result", response.model_dump(mode="json"))
                else:
                    yield _sse("progress", event)
        except Exception as exc:
            message = f"分析工作流执行失败：{exc}"
            if request.conversationId and get_conversation(request.conversationId):
                save_message(
                    conversation_id=request.conversationId,
                    role="assistant",
                    content="",
                    llm_response={"content": message, "status": "error"},
                    sandbox_response={"content": message, "status": "error"},
                )
            yield _sse("error", {"message": message, "status": "error"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
