"""Conversation persistence API."""

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.conversation_service import (
    create_conversation,
    delete_conversation,
    get_conversation,
    list_analysis_runs,
    list_conversations,
    save_message,
    update_conversation,
)


router = APIRouter()


class ConversationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    activeFileIds: List[str] = Field(default_factory=list)


class ConversationUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=160)
    activeFileIds: Optional[List[str]] = None


class MessageCreate(BaseModel):
    id: Optional[str] = None
    role: Literal["user", "assistant"]
    content: str = ""
    filesUsed: List[str] = Field(default_factory=list)
    llmResponse: Optional[Dict[str, Any]] = None
    sandboxResponse: Optional[Dict[str, Any]] = None


@router.get("")
async def get_conversations():
    return {"success": True, "conversations": list_conversations()}


@router.post("")
async def create_conversation_route(payload: ConversationCreate):
    conversation = create_conversation(payload.title, payload.activeFileIds)
    return {"success": True, "conversation": conversation}


@router.get("/{conversation_id}")
async def get_conversation_route(conversation_id: str):
    conversation = get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True, "conversation": conversation}


@router.patch("/{conversation_id}")
async def update_conversation_route(conversation_id: str, payload: ConversationUpdate):
    conversation = update_conversation(conversation_id, payload.title, payload.activeFileIds)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True, "conversation": conversation}


@router.delete("/{conversation_id}")
async def delete_conversation_route(conversation_id: str):
    if not delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True}


@router.post("/{conversation_id}/messages")
async def create_message_route(conversation_id: str, payload: MessageCreate):
    if not get_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    message_id = save_message(
        conversation_id=conversation_id,
        role=payload.role,
        content=payload.content,
        message_id=payload.id,
        file_names=payload.filesUsed,
        llm_response=payload.llmResponse,
        sandbox_response=payload.sandboxResponse,
    )
    return {"success": True, "messageId": message_id}


@router.get("/{conversation_id}/runs")
async def get_analysis_runs(conversation_id: str, verified_only: bool = False):
    if not get_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "success": True,
        "runs": list_analysis_runs(conversation_id, verified_only=verified_only),
    }
