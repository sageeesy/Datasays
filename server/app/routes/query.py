"""Verified analysis query route."""

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.agent_service import run_data_analysis_agent
from app.services.conversation_service import get_conversation, save_analysis_exchange, save_message
from app.services.file_service import load_metadata

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


@router.post("", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """Run one evidence-first analysis and persist its artifacts."""
    try:
        # Validate input
        if not request.question or not request.fileIds or len(request.fileIds) == 0:
            raise HTTPException(
                status_code=400,
                detail="Missing required fields: question and fileIds are required"
            )
        
        if request.conversationId and not get_conversation(request.conversationId):
            raise HTTPException(status_code=404, detail="Conversation not found")

        file_names = []
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

        prompt_style = request.prompt_style or "zero"
        model = request.model or None
        sandbox_response = await run_data_analysis_agent(
            request.question, request.fileIds, prompt_style, model
        )
        # Keep the response envelope stable for the current frontend. Both fields
        # intentionally point to the same verified answer in Agent mode.
        llm_response = {
            "content": sandbox_response["content"],
            "status": sandbox_response["status"],
        }
        
        response = QueryResponse(
            success=True,
            llmResponse=ResponseData(
                content=llm_response["content"],
                status=llm_response["status"]
            ),
            sandboxResponse=ResponseData(
                content=sandbox_response["content"],
                code=sandbox_response.get("code"),
                thinking_process=sandbox_response.get("thinking_process"),
                status=sandbox_response["status"],
                output=sandbox_response.get("output"),
                metadata=sandbox_response.get("metadata")
            )
        )
        if request.conversationId and user_message_id:
            save_analysis_exchange(
                conversation_id=request.conversationId,
                user_message_id=user_message_id,
                question=request.question,
                file_names=file_names,
                model=model,
                prompt_style=prompt_style,
                response=response.model_dump(mode="json"),
            )
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
