"""Conversation and message schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models import MessageRole


class ChatRequest(BaseModel):
    content: str
    tool: str = "general"


class ConversationCreate(BaseModel):
    title: str = "New Conversation"


class ConversationUpdate(BaseModel):
    title: str


class MessageCreate(BaseModel):
    role: MessageRole = MessageRole.USER
    content: str


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: MessageRole
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationWithMessages(ConversationResponse):
    messages: list[MessageResponse] = []
