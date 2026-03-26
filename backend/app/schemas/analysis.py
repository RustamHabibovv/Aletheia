"""Analysis-related schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models import AnalysisType, Verdict


class AnalysisRequest(BaseModel):
    """Body for triggering analysis on a message."""

    message_id: uuid.UUID
    analysis_type: AnalysisType = AnalysisType.FACT_CHECK


class AnalysisResponse(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    analysis_type: AnalysisType
    verdict: Verdict | None
    confidence_score: float | None
    summary: str
    detailed_breakdown: dict | None
    sources: list | None
    created_at: datetime

    model_config = {"from_attributes": True}
