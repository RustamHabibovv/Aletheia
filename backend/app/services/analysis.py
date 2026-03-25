"""Analysis orchestration — routes to the correct agent and persists results."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.agents.fact_checker import FactChecker
from app.core.config import get_settings
from app.models import AnalysisResult, AnalysisType, Message

logger = logging.getLogger(__name__)


async def run_analysis(
    message: Message,
    analysis_type: AnalysisType,
    session: AsyncSession,
) -> AnalysisResult:
    """Run the appropriate agent on a message and persist the AnalysisResult."""
    settings = get_settings()

    if analysis_type == AnalysisType.FACT_CHECK:
        agent = FactChecker(settings)
        result_data = await agent.check(message.content)
    else:
        result_data = {
            "analysis_type": analysis_type,
            "verdict": None,
            "confidence_score": None,
            "summary": f"{analysis_type.value} agent is not yet implemented.",
            "detailed_breakdown": None,
            "sources": None,
        }

    analysis = AnalysisResult(id=uuid.uuid4(), message_id=message.id, **result_data)
    session.add(analysis)
    await session.commit()
    await session.refresh(analysis)
    logger.info("Analysis %s completed for message %s — verdict=%s", analysis.id, message.id, analysis.verdict)
    return analysis


async def get_analysis_for_message(
    message_id: uuid.UUID,
    session: AsyncSession,
) -> AnalysisResult | None:
    """Fetch the analysis result linked to a specific message."""
    stmt = select(AnalysisResult).where(AnalysisResult.message_id == message_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
