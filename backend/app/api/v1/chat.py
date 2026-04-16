"""Chat endpoint — sends a user message and returns an assistant reply."""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.agents.fact_checker import FactChecker
from app.agents.text_detector import TextDetector
from app.api.deps import CurrentUser, DBSession
from app.core.config import get_settings
from app.models import Conversation, Message, MessageRole
from app.schemas.conversation import ChatRequest, MessageResponse
from app.services.openai_service import generate_reply
from app.services.url_extractor import extract_urls, fetch_url_text

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

    # Pre-process: if input contains URLs, extract page content for analysis tools
    agent_input = body.content
    if body.tool in ("fact-check", "text-detection"):
        urls = extract_urls(body.content)
        if urls:
            extracted = await fetch_url_text(urls[0], tavily_api_key=settings.tavily_api_key)
            if extracted:
                agent_input = extracted

    if body.tool == "fact-check":
        analysis_result = await FactChecker(settings).check(agent_input)
        reply_text = _format_fact_check(analysis_result)
    elif body.tool == "text-detection":
        analysis_result = await TextDetector(settings).detect(agent_input)
        reply_text = _format_text_detection(analysis_result)
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

    analysis_type = result.get("analysis_type")
    at_value = analysis_type.value if hasattr(analysis_type, "value") else str(analysis_type or "")

    base = {
        "verdict": verdict.value if hasattr(verdict, "value") else str(verdict),
        "confidence_score": result.get("confidence_score"),
        "summary": result.get("summary", ""),
        "analysis_type": at_value,
        "sources": result.get("sources") or [],
    }

    breakdown = result.get("detailed_breakdown") or {}

    if at_value == "TEXT_DETECTION":
        base["ai_score"] = breakdown.get("ai_score")
        base["classification"] = breakdown.get("classification", "")
        base["sentence_analysis"] = breakdown.get("sentence_analysis", [])
        base["explanation"] = breakdown.get("explanation", "")
        base["signals"] = breakdown.get("signals", [])
    else:
        base["claims"] = breakdown.get("claims", [])

    return base


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


def _format_text_detection(result: dict) -> str:
    """Format text detection result as a readable markdown message."""
    breakdown = result.get("detailed_breakdown") or {}
    ai_score = breakdown.get("ai_score")
    classification = breakdown.get("classification", "unknown")
    explanation = breakdown.get("explanation", "")
    signals = breakdown.get("signals", [])
    sentence_analysis = breakdown.get("sentence_analysis", [])

    if classification == "insufficient":
        return result.get("summary") or "Insufficient text for analysis."

    score_pct = f"{ai_score:.0%}" if ai_score is not None else "N/A"
    label_map = {"ai-generated": "AI-Generated", "human-written": "Human-Written", "mixed": "Mixed"}
    label = label_map.get(classification, classification.title())

    lines = [f"**Text analysis complete.**\n\nVerdict: **{label}** ({score_pct} AI probability)\n"]

    if explanation:
        lines.append(f"{explanation}\n")

    if signals:
        lines.append("**Signals:**")
        for s in signals:
            icon = "⚠️" if s.get("flag") == "warn" else "✅"
            lines.append(f"- {icon} {s.get('label', '')}: {s.get('value', '')}")

    ai_sentences = [s for s in sentence_analysis if s.get("flag") == "ai"]
    if ai_sentences:
        lines.append(f"\n**Flagged sentences** ({len(ai_sentences)}):")
        for s in ai_sentences[:5]:
            prob = s.get("ai_probability", 0)
            lines.append(f'- "{s.get("sentence", "")[:120]}" — {prob:.0%} AI probability')

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
