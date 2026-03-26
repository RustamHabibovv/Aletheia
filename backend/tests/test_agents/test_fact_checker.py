"""Tests for the fact-checker agent."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.fact_checker import FactChecker
from app.core.config import get_settings
from app.models import AnalysisType, Verdict


@pytest.fixture
def settings():
    s = get_settings()
    return s


@pytest.fixture
def fact_checker(settings):
    return FactChecker(settings)


def _mock_chat_response(content: str):
    """Build a fake OpenAI chat completion response."""
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ── Claim extraction ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_claims_returns_list(fact_checker):
    mock_resp = _mock_chat_response(json.dumps({"claims": ["Earth is round", "Water is dry"]}))

    with patch.object(fact_checker.llm.chat.completions, "create", new_callable=AsyncMock, return_value=mock_resp):
        claims = await fact_checker._extract_claims("Earth is round and water is dry.")

    assert claims == ["Earth is round", "Water is dry"]


@pytest.mark.asyncio
async def test_extract_claims_empty_on_failure(fact_checker):
    with patch.object(
        fact_checker.llm.chat.completions, "create", new_callable=AsyncMock, side_effect=Exception("LLM down")
    ):
        claims = await fact_checker._extract_claims("anything")

    assert claims == []


# ── Evidence search ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_evidence_no_api_key(fact_checker):
    fact_checker.settings.tavily_api_key = ""
    text, sources = await fact_checker._search_evidence("some claim")
    assert "not configured" in text
    assert sources == []


@pytest.mark.asyncio
async def test_search_evidence_returns_snippets(fact_checker):
    fact_checker.settings.tavily_api_key = "test-key"

    mock_client = AsyncMock()
    mock_client.search.return_value = {
        "results": [
            {"title": "Source A", "url": "https://a.com", "content": "Evidence text A"},
            {"title": "Source B", "url": "https://b.com", "content": "Evidence text B"},
        ]
    }

    with patch("tavily.AsyncTavilyClient", return_value=mock_client):
        text, sources = await fact_checker._search_evidence("test claim")

    assert "Source A" in text
    assert "Source B" in text
    assert len(sources) == 2
    assert sources[0]["url"] == "https://a.com"


# ── Claim evaluation ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evaluate_claim_returns_result(fact_checker):
    eval_response = json.dumps(
        {
            "verdict": "TRUE",
            "confidence": 0.95,
            "explanation": "Verified by multiple sources.",
            "key_sources": ["https://example.com"],
        }
    )
    mock_resp = _mock_chat_response(eval_response)

    with patch.object(fact_checker.llm.chat.completions, "create", new_callable=AsyncMock, return_value=mock_resp):
        result = await fact_checker._evaluate_claim("Earth is round", "Evidence here")

    assert result["verdict"] == "TRUE"
    assert result["confidence"] == 0.95
    assert result["claim"] == "Earth is round"


@pytest.mark.asyncio
async def test_evaluate_claim_fallback_on_error(fact_checker):
    with patch.object(
        fact_checker.llm.chat.completions, "create", new_callable=AsyncMock, side_effect=Exception("fail")
    ):
        result = await fact_checker._evaluate_claim("anything", "no evidence")

    assert result["verdict"] == "UNVERIFIABLE"
    assert result["confidence"] == 0.0


# ── Full pipeline ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_no_claims(fact_checker):
    mock_resp = _mock_chat_response(json.dumps({"claims": []}))

    with patch.object(fact_checker.llm.chat.completions, "create", new_callable=AsyncMock, return_value=mock_resp):
        result = await fact_checker.check("Just an opinion, nothing factual.")

    assert result["verdict"] is None
    assert "No verifiable" in result["summary"]


@pytest.mark.asyncio
async def test_check_full_pipeline(fact_checker):
    fact_checker.settings.tavily_api_key = ""  # skip real search

    # First LLM call → claim extraction, subsequent calls → evaluation
    claims_resp = _mock_chat_response(json.dumps({"claims": ["Claim A"]}))
    eval_resp = _mock_chat_response(
        json.dumps(
            {
                "verdict": "PARTIALLY_TRUE",
                "confidence": 0.7,
                "explanation": "Some evidence supports this.",
                "key_sources": [],
            }
        )
    )

    with patch.object(
        fact_checker.llm.chat.completions, "create", new_callable=AsyncMock, side_effect=[claims_resp, eval_resp]
    ):
        result = await fact_checker.check("Claim A is true.")

    assert result["analysis_type"] == AnalysisType.FACT_CHECK
    assert result["verdict"] == Verdict.PARTIALLY_TRUE
    # Confidence calibrated down: no Tavily key → capped at 0.3
    assert result["confidence_score"] <= 0.3
    assert "1 claim" in result["summary"]


# ── Aggregation ───────────────────────────────────────────────────


def test_aggregate_picks_worst_verdict(fact_checker):
    claims = [
        {"verdict": "TRUE", "confidence": 0.9, "key_sources": ["a.com"]},
        {"verdict": "FALSE", "confidence": 0.8, "key_sources": ["b.com"]},
    ]
    result = fact_checker._aggregate(claims, ["a.com", "b.com"])

    assert result["verdict"] == Verdict.FALSE
    assert result["confidence_score"] == 0.85
    assert result["sources"] == ["a.com", "b.com"]


# ── Confidence calibration ────────────────────────────────────────


def test_calibrate_no_evidence_caps_at_03(fact_checker):
    result = {"confidence": 0.95}
    evidence = "No search results available (Tavily API key not configured)."
    assert fact_checker._calibrate_confidence(result, evidence) <= 0.3


def test_calibrate_search_unavailable(fact_checker):
    result = {"confidence": 0.9}
    evidence = "Search unavailable — evaluating with model knowledge only."
    assert fact_checker._calibrate_confidence(result, evidence) <= 0.3


def test_calibrate_no_source_lines(fact_checker):
    result = {"confidence": 0.8}
    evidence = "No relevant results found."
    assert fact_checker._calibrate_confidence(result, evidence) == 0.4  # 0.8 * 0.5


def test_calibrate_few_sources(fact_checker):
    result = {"confidence": 0.8}
    evidence = "- [Src A](https://a.com): text A\n- [Src B](https://b.com): text B"
    assert fact_checker._calibrate_confidence(result, evidence) == 0.6  # 0.8 * 0.75


def test_calibrate_many_sources(fact_checker):
    result = {"confidence": 0.8}
    lines = [f"- [Src {i}](https://{i}.com): text {i}" for i in range(6)]
    evidence = "\n".join(lines)
    assert fact_checker._calibrate_confidence(result, evidence) == 0.8  # 0.8 * 1.0


def test_calibrate_clamps_to_1(fact_checker):
    result = {"confidence": 1.5}  # LLM might hallucinate >1
    lines = [f"- [Src {i}](https://{i}.com): text" for i in range(6)]
    evidence = "\n".join(lines)
    assert fact_checker._calibrate_confidence(result, evidence) == 1.0
