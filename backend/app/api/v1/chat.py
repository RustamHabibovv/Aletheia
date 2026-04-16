"""Chat endpoint — sends a user message and returns an assistant reply."""

import logging
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.agents.fact_checker import FactChecker
from app.api.deps import CurrentUser, DBSession
from app.core.config import get_settings
from app.models import Conversation, Message, MessageRole
from app.schemas.conversation import ChatRequest, MessageResponse
from app.services.openai_service import generate_reply
from app.services.url_extractor import extract_url_content
from app.utils.url_detect import extract_urls

logger = logging.getLogger(__name__)

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
    analysis_result = None
    source_url: str | None = None
    if body.tool == "fact-check":
        # If the user pasted a URL, fetch its content and analyse that instead
        urls = extract_urls(body.content)
        fact_check_text = body.content
        if urls:
            source_url = urls[0]  # analyse the first URL
            extracted = await extract_url_content(source_url, tavily_api_key=settings.tavily_api_key)
            if extracted.error is None and extracted.text:
                # Prepend URL context so the LLM/pipeline knows the source
                fact_check_text = (
                    f"[Source: {extracted.source_domain} — {extracted.url}]\n"
                    f"Title: {extracted.title}\n\n"
                    f"{extracted.text}"
                )
            else:
                logger.warning("URL extraction failed for %s: %s", source_url, extracted.error)
                source_url = None  # treat as plain-text input

        try:
            analysis_result = await FactChecker(settings).check(fact_check_text)
        except Exception as exc:
            logger.error("Fact-check pipeline error: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Fact-check service is temporarily unavailable. Please try again in a moment.",
            ) from exc
        if source_url:
            analysis_result["source_url"] = source_url
        reply_text = _format_fact_check(analysis_result)
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

    response = MessageResponse.model_validate(assistant_msg)
    if analysis_result is not None:
        response.analysis = _serialize_analysis(analysis_result)
    return response


def _serialize_analysis(result: dict) -> dict | None:
    """Convert agent result dict into a JSON-safe analysis payload."""
    verdict = result.get("verdict")
    if verdict is None:
        return None
    return {
        "verdict": verdict.value if hasattr(verdict, "value") else str(verdict),
        "confidence_score": result.get("confidence_score"),
        "summary": result.get("summary", ""),
        "claims": (result.get("detailed_breakdown") or {}).get("claims", []),
        "sources": result.get("sources") or [],
        "source_url": result.get("source_url"),
    }


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
        for s in sources[:5]:
            if isinstance(s, dict):
                lines.append(f"- [{s.get('title', 'Source')}]({s.get('url', '')})")
            else:
                lines.append(f"- {s}")

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
