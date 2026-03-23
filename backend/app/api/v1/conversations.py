"""Conversation and message endpoints."""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.api.deps import CurrentUser, DBSession
from app.models import Conversation, Message
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    ConversationWithMessages,
    MessageCreate,
    MessageResponse,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(user: CurrentUser, session: DBSession) -> list[ConversationResponse]:
    """List all conversations for the authenticated user, newest first."""
    result = await session.execute(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationCreate, user: CurrentUser, session: DBSession
) -> ConversationResponse:
    """Create a new conversation."""
    conversation = Conversation(user_id=user.id, title=body.title)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


@router.get("/{conversation_id}", response_model=ConversationWithMessages)
async def get_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, session: DBSession
) -> ConversationWithMessages:
    """Get a single conversation with all its messages."""
    conversation = await _get_owned_conversation(conversation_id, user.id, session)
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    messages = result.scalars().all()
    return ConversationWithMessages(
        id=conversation.id,
        user_id=conversation.user_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[MessageResponse.model_validate(m) for m in messages],
    )


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def rename_conversation(
    conversation_id: uuid.UUID, body: ConversationUpdate, user: CurrentUser, session: DBSession
) -> ConversationResponse:
    """Rename a conversation."""
    conversation = await _get_owned_conversation(conversation_id, user.id, session)
    conversation.title = body.title
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, session: DBSession
) -> None:
    """Delete a conversation and all its messages."""
    conversation = await _get_owned_conversation(conversation_id, user.id, session)
    await session.delete(conversation)
    await session.commit()


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_message(
    conversation_id: uuid.UUID, body: MessageCreate, user: CurrentUser, session: DBSession
) -> MessageResponse:
    """Append a message to a conversation."""
    await _get_owned_conversation(conversation_id, user.id, session)
    message = Message(conversation_id=conversation_id, role=body.role, content=body.content)
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return MessageResponse.model_validate(message)


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: uuid.UUID, user: CurrentUser, session: DBSession
) -> list[MessageResponse]:
    """List all messages in a conversation in chronological order."""
    await _get_owned_conversation(conversation_id, user.id, session)
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    return result.scalars().all()


# ── helpers ────────────────────────────────────────────────────────


async def _get_owned_conversation(
    conversation_id: uuid.UUID, user_id: uuid.UUID, session: DBSession
) -> Conversation:
    result = await session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation
