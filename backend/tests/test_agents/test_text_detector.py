"""Tests for the TextDetector agent."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.agents.text_detector import TextDetector
from app.models import AnalysisType, Verdict


@pytest.fixture
def settings():
    """Create a mock settings object."""
    s = MagicMock()
    s.sapling_api_key = "test-sapling-key"
    s.openrouter_api_key = "test-openrouter-key"
    s.openrouter_base_url = "https://openrouter.ai/api/v1"
    s.openrouter_model = "openai/gpt-4o-mini"
    return s


@pytest.fixture
def settings_no_sapling():
    """Settings without Sapling API key — triggers LLM fallback."""
    s = MagicMock()
    s.sapling_api_key = ""
    s.openrouter_api_key = "test-openrouter-key"
    s.openrouter_base_url = "https://openrouter.ai/api/v1"
    s.openrouter_model = "openai/gpt-4o-mini"
    return s


def _make_sapling_response(score: float, sentences: list[dict] | None = None) -> dict:
    """Build a mock Sapling API response."""
    return {
        "score": score,
        "sentence_scores": sentences
        or [
            {"score": score, "sentence": "This is a test sentence."},
            {"score": score * 0.5, "sentence": "Another sentence here."},
        ],
    }


def _make_llm_response(content: str) -> MagicMock:
    """Build a mock OpenAI chat completion response."""
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


class TestTextDetectorInsufficientText:
    """Test short text handling."""

    @pytest.mark.asyncio
    async def test_short_text_returns_unverifiable(self, settings):
        detector = TextDetector(settings)
        result = await detector.detect("Too short")
        assert result["verdict"] == Verdict.UNVERIFIABLE
        assert result["analysis_type"] == AnalysisType.TEXT_DETECTION
        assert result["confidence_score"] is None
        assert "insufficient" in result["detailed_breakdown"]["classification"]

    @pytest.mark.asyncio
    async def test_empty_text(self, settings):
        detector = TextDetector(settings)
        result = await detector.detect("")
        assert result["verdict"] == Verdict.UNVERIFIABLE


class TestTextDetectorClassification:
    """Test score-to-verdict mapping."""

    def test_high_score_is_ai_generated(self, settings):
        detector = TextDetector(settings)
        assert detector._score_to_verdict(0.85) == Verdict.FALSE
        assert detector._classify(0.85) == "ai-generated"

    def test_low_score_is_human(self, settings):
        detector = TextDetector(settings)
        assert detector._score_to_verdict(0.15) == Verdict.TRUE
        assert detector._classify(0.15) == "human-written"

    def test_mid_score_is_mixed(self, settings):
        detector = TextDetector(settings)
        assert detector._score_to_verdict(0.5) == Verdict.PARTIALLY_TRUE
        assert detector._classify(0.5) == "mixed"

    def test_boundary_065_is_ai(self, settings):
        detector = TextDetector(settings)
        assert detector._score_to_verdict(0.65) == Verdict.FALSE

    def test_boundary_030_is_mixed(self, settings):
        detector = TextDetector(settings)
        assert detector._score_to_verdict(0.30) == Verdict.PARTIALLY_TRUE

    def test_boundary_029_is_human(self, settings):
        detector = TextDetector(settings)
        assert detector._score_to_verdict(0.29) == Verdict.TRUE


class TestSaplingIntegration:
    """Test Sapling API call and result processing."""

    @pytest.mark.asyncio
    async def test_sapling_ai_detected(self, settings):
        sapling_resp = _make_sapling_response(
            0.85,
            [
                {"score": 0.9, "sentence": "This text exhibits uniform structure."},
                {"score": 0.8, "sentence": "The word choice is highly predictable."},
            ],
        )
        llm_explanation = "The text shows signs of AI generation with uniform sentence lengths."

        detector = TextDetector(settings)

        with (
            patch.object(detector, "_call_sapling", new_callable=AsyncMock, return_value=sapling_resp),
            patch.object(detector, "_generate_explanation", new_callable=AsyncMock, return_value=llm_explanation),
        ):
            result = await detector.detect("A" * 200)

        assert result["verdict"] == Verdict.FALSE
        assert result["analysis_type"] == AnalysisType.TEXT_DETECTION
        assert result["confidence_score"] == 0.7  # abs(0.85 - 0.5) * 2
        breakdown = result["detailed_breakdown"]
        assert breakdown["classification"] == "ai-generated"
        assert len(breakdown["sentence_analysis"]) == 2
        assert breakdown["sentence_analysis"][0]["flag"] == "ai"
        assert breakdown["explanation"] == llm_explanation

    @pytest.mark.asyncio
    async def test_sapling_human_detected(self, settings):
        sapling_resp = _make_sapling_response(
            0.1,
            [
                {"score": 0.05, "sentence": "I really enjoyed writing this piece."},
                {"score": 0.15, "sentence": "The sunset was breathtaking yesterday."},
            ],
        )

        detector = TextDetector(settings)

        with (
            patch.object(detector, "_call_sapling", new_callable=AsyncMock, return_value=sapling_resp),
            patch.object(detector, "_generate_explanation", new_callable=AsyncMock, return_value="Human-written text."),
        ):
            result = await detector.detect("A" * 200)

        assert result["verdict"] == Verdict.TRUE
        assert result["detailed_breakdown"]["classification"] == "human-written"

    @pytest.mark.asyncio
    async def test_sapling_failure_falls_back_to_llm(self, settings):
        """When Sapling returns None, should fall back to LLM-only detection."""
        llm_response = _make_llm_response(
            json.dumps(
                {
                    "ai_probability": 0.7,
                    "classification": "ai-generated",
                    "explanation": "Pattern-matched analysis.",
                    "signals": [{"label": "Repetitive phrasing", "value": "3 instances", "flag": "warn"}],
                }
            )
        )

        detector = TextDetector(settings)

        with (
            patch.object(detector, "_call_sapling", new_callable=AsyncMock, return_value=None),
            patch.object(detector.llm.chat.completions, "create", new_callable=AsyncMock, return_value=llm_response),
        ):
            result = await detector.detect("A" * 200)

        assert result["verdict"] == Verdict.FALSE
        assert "LLM heuristic" in result["summary"]
        assert result["detailed_breakdown"]["classification"] == "ai-generated"


class TestSaplingApiCall:
    """Test the _call_sapling method."""

    @pytest.mark.asyncio
    async def test_successful_call(self, settings):
        expected = {"score": 0.75, "sentence_scores": []}
        mock_response = MagicMock()
        mock_response.json.return_value = expected
        mock_response.raise_for_status = MagicMock()

        detector = TextDetector(settings)

        with patch("app.agents.text_detector.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await detector._call_sapling("test text")

        assert result == expected
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert call_kwargs[1]["json"]["key"] == "test-sapling-key"

    @pytest.mark.asyncio
    async def test_timeout_retries(self, settings):
        detector = TextDetector(settings)

        with patch("app.agents.text_detector.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.TimeoutException("timeout")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await detector._call_sapling("test text")

        assert result is None
        assert mock_client.post.call_count == 2  # retried once

    @pytest.mark.asyncio
    async def test_http_error_no_retry(self, settings):
        detector = TextDetector(settings)

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        error = httpx.HTTPStatusError("forbidden", request=MagicMock(), response=mock_response)

        with patch("app.agents.text_detector.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = error
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await detector._call_sapling("test text")

        assert result is None
        assert mock_client.post.call_count == 1  # no retry on HTTP errors


class TestLlmFallback:
    """Test LLM-only fallback when no Sapling key is configured."""

    @pytest.mark.asyncio
    async def test_fallback_parses_llm_json(self, settings_no_sapling):
        llm_response = _make_llm_response(
            json.dumps(
                {
                    "ai_probability": 0.3,
                    "classification": "mixed",
                    "explanation": "Stylistic inconsistencies suggest partial AI involvement.",
                    "signals": [{"label": "Burstiness", "value": "0.45", "flag": "info"}],
                }
            )
        )

        detector = TextDetector(settings_no_sapling)

        with patch.object(detector.llm.chat.completions, "create", new_callable=AsyncMock, return_value=llm_response):
            result = await detector.detect("A" * 200)

        assert result["verdict"] == Verdict.PARTIALLY_TRUE
        assert result["detailed_breakdown"]["classification"] == "mixed"
        assert len(result["detailed_breakdown"]["signals"]) == 1

    @pytest.mark.asyncio
    async def test_fallback_handles_llm_failure(self, settings_no_sapling):
        detector = TextDetector(settings_no_sapling)

        with patch.object(
            detector.llm.chat.completions, "create", new_callable=AsyncMock, side_effect=Exception("LLM down")
        ):
            result = await detector.detect("A" * 200)

        # Should return a graceful fallback, not crash
        assert result["verdict"] == Verdict.PARTIALLY_TRUE  # default 0.5 score
        assert result["analysis_type"] == AnalysisType.TEXT_DETECTION


class TestConfidenceCalculation:
    """Test confidence score derivation from AI probability."""

    @pytest.mark.asyncio
    async def test_high_ai_score_high_confidence(self, settings):
        sapling_resp = _make_sapling_response(0.95)
        detector = TextDetector(settings)

        with (
            patch.object(detector, "_call_sapling", new_callable=AsyncMock, return_value=sapling_resp),
            patch.object(detector, "_generate_explanation", new_callable=AsyncMock, return_value="AI text."),
        ):
            result = await detector.detect("A" * 200)

        assert result["confidence_score"] == 0.9  # abs(0.95 - 0.5) * 2

    @pytest.mark.asyncio
    async def test_mid_score_low_confidence(self, settings):
        sapling_resp = _make_sapling_response(0.5)
        detector = TextDetector(settings)

        with (
            patch.object(detector, "_call_sapling", new_callable=AsyncMock, return_value=sapling_resp),
            patch.object(detector, "_generate_explanation", new_callable=AsyncMock, return_value="Unclear."),
        ):
            result = await detector.detect("A" * 200)

        assert result["confidence_score"] == 0.0  # abs(0.5 - 0.5) * 2
