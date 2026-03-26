"""Chat endpoint — sends a user message and returns an assistant reply."""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.agents.fact_checker import FactChecker
from app.api.deps import CurrentUser, DBSession
from app.core.config import get_settings
from app.models import Conversation, Message, MessageRole
from app.schemas.conversation import ChatRequest, MessageResponse
from app.services.openai_service import generate_reply

router = APIRouter(prefix="/conversations", tags=["chat"])


@router.post(
    "/{conversation_id}/chat",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def chat(
    conversation_id: uuid.UUID,
    body: ChatRequest,
    user: CurrentUser,
    session: DBSession,
) -> MessageResponse:
    """Send a user message and get an assistant reply, both persisted to the conversation."""
    await _get_owned_conversation(conversation_id, user.id, session)

    # Fetch existing messages for context
    history_result = await session.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
    )
    history = [
        {"role": "user" if m.role == MessageRole.USER else "assistant", "content": m.content}
        for m in history_result.scalars().all()
    ]

    # Persist user message
    user_msg = Message(
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content=body.content,
    )
    session.add(user_msg)
    await session.commit()

    settings = get_settings()
    if body.tool == "fact-check":
        result = await FactChecker(settings).check(body.content)
        reply_text = _format_fact_check(result)
    else:
        reply_text = await generate_reply(body.tool, history, body.content, settings)

    # Persist assistant message
    assistant_msg = Message(
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content=reply_text,
    )
    session.add(assistant_msg)
    await session.commit()
    await session.refresh(assistant_msg)

    return MessageResponse.model_validate(assistant_msg)


def _format_fact_check(result: dict) -> str:
    verdict = result.get("verdict")
    confidence = result.get("confidence_score")
    claims = (result.get("detailed_breakdown") or {}).get("claims", [])
    sources = result.get("sources") or []

    if not claims:
        return result.get("summary") or "No verifiable factual claims found in the provided text."

    verdict_str = verdict.value if hasattr(verdict, "value") else str(verdict)
    conf_pct = f"{round(confidence * 100)}%" if confidence is not None else "N/A"

    lines = [f"**Fact-check complete.**\n\nOverall verdict: **{verdict_str}** ({conf_pct} confidence)\n"]
    for i, c in enumerate(claims, 1):
        v = c.get("verdict", "UNVERIFIABLE")
        conf = round(c.get("confidence", 0.0) * 100)
        explanation = c.get("explanation", "")
        lines.append(f"{i}. **{c.get('claim', '')}**\n   *{v}* ({conf}% confidence) — {explanation}")

    if sources:
        lines.append("\n**Sources:**")
        lines.extend(f"- {s}" for s in sources[:5])

    return "\n".join(lines)


async def _get_owned_conversation(conversation_id: uuid.UUID, user_id: uuid.UUID, session: DBSession) -> Conversation:
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
