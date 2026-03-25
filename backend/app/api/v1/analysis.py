"""Analysis endpoints — trigger and retrieve fact-check / analysis results."""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.api.deps import CurrentUser, DBSession
from app.models import Conversation, Message
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.services.analysis import get_analysis_for_message, run_analysis

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("", response_model=AnalysisResponse, status_code=status.HTTP_201_CREATED)
async def create_analysis(body: AnalysisRequest, user: CurrentUser, session: DBSession) -> AnalysisResponse:
    """Run an analysis (e.g. fact-check) on a specific message.

    The message must belong to a conversation owned by the authenticated user.
    """
    # Fetch the message and verify ownership through the conversation
    message = await _get_owned_message(body.message_id, user.id, session)

    # Check if analysis already exists for this message
    existing = await get_analysis_for_message(body.message_id, session)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Analysis already exists for this message.",
        )

    result = await run_analysis(message, body.analysis_type, session)
    return AnalysisResponse.model_validate(result)


@router.get("/{message_id}", response_model=AnalysisResponse)
async def get_analysis(message_id: uuid.UUID, user: CurrentUser, session: DBSession) -> AnalysisResponse:
    """Retrieve the analysis result for a specific message."""
    await _get_owned_message(message_id, user.id, session)
    analysis = await get_analysis_for_message(message_id, session)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No analysis found for this message.")
    return AnalysisResponse.model_validate(analysis)


# ── helpers ────────────────────────────────────────────────────────


async def _get_owned_message(message_id: uuid.UUID, user_id: uuid.UUID, session: DBSession) -> Message:
    """Fetch a message and verify the owning conversation belongs to the user."""
    result = await session.execute(select(Message).where(Message.id == message_id))
    message = result.scalar_one_or_none()
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")

    conv_result = await session.execute(
        select(Conversation).where(
            Conversation.id == message.conversation_id,
            Conversation.user_id == user_id,
        )
    )
    if conv_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")

    return message
