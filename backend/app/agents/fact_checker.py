"""Fact-checking agent — extracts claims, searches for evidence, evaluates truthfulness.

Uses OpenRouter (OpenAI-compatible API) for LLM and Tavily for web search.
"""

import asyncio
import json
import logging
import re

from openai import AsyncOpenAI

from app.core.config import Settings
from app.models import AnalysisType, Verdict

logger = logging.getLogger(__name__)

CLAIM_EXTRACTION_PROMPT = """\
You are a claim extraction system. Extract ALL verifiable factual claims from the user's text.
A claim is any statement that asserts something about the real world that can be checked.
Extract claims EVEN IF they appear to be false or inaccurate — your job is extraction, not verification.
Skip opinions, questions, and purely subjective statements.
Return a JSON object: {"claims": ["claim 1", "claim 2"]}.
If there are truly no factual claims, return: {"claims": []}."""

VERDICT_PROMPT = """\
You are a fact-checking expert. Evaluate the following claim against the provided evidence.

Claim: {claim}

Evidence:
{evidence}

Respond with ONLY a JSON object:
{{"verdict": "TRUE" | "FALSE" | "PARTIALLY_TRUE" | "UNVERIFIABLE" | "MISLEADING", \
"confidence": 0.0, "explanation": "brief reason", "key_sources": ["source1"]}}"""


class FactChecker:
    """Extracts claims from text, searches for evidence, and evaluates each claim."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.llm = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )
        self.model = settings.openrouter_model

    @staticmethod
    def _parse_json(raw: str) -> dict | list:
        """Strip markdown fences and parse JSON. Raises on failure."""
        text = raw.strip()
        # Remove ```json ... ``` or ``` ... ``` wrappers
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
        if not text:
            return {}
        return json.loads(text)

    async def check(self, text: str) -> dict:
        """Run full fact-check pipeline. Returns dict matching AnalysisResult fields."""
        claims = await self._extract_claims(text)
        if not claims:
            return self._no_claims_result()

        # Search evidence for all claims in parallel
        evidence_list = await asyncio.gather(*(self._search_evidence(claim) for claim in claims))

        # Evaluate all claims against their evidence in parallel
        raw_results = await asyncio.gather(
            *(self._evaluate_claim(claim, evidence) for claim, evidence in zip(claims, evidence_list, strict=True))
        )

        # Calibrate confidence based on evidence quality
        claim_results = []
        all_sources: list[str] = []
        for result, evidence in zip(raw_results, evidence_list, strict=True):
            result["confidence"] = self._calibrate_confidence(result, evidence)
            claim_results.append(result)
            all_sources.extend(result.get("key_sources", []))

        return self._aggregate(claim_results, list(dict.fromkeys(all_sources)))

    # ── Pipeline steps ─────────────────────────────────────────────

    async def _extract_claims(self, text: str) -> list[str]:
        """Use LLM to pull out verifiable factual claims."""
        try:
            resp = await self.llm.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": CLAIM_EXTRACTION_PROMPT},
                    {"role": "user", "content": text},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content or "{}"
            parsed = self._parse_json(content)
            if isinstance(parsed, dict):
                return parsed.get("claims", [])[:10]
            if isinstance(parsed, list):
                return parsed[:10]
            return []
        except Exception:
            logger.exception("Claim extraction failed")
            return []

    async def _search_evidence(self, claim: str) -> str:
        """Search the web for evidence using Tavily. Degrades gracefully."""
        if not self.settings.tavily_api_key:
            return "No search results available (Tavily API key not configured)."

        try:
            from tavily import AsyncTavilyClient

            client = AsyncTavilyClient(api_key=self.settings.tavily_api_key)
            results = await client.search(query=claim, max_results=10)
            snippets = []
            for r in results.get("results", []):
                title = r.get("title", "Source")
                url = r.get("url", "")
                content = r.get("content", "")[:300]
                snippets.append(f"- [{title}]({url}): {content}")
            return "\n".join(snippets) if snippets else "No relevant results found."
        except Exception:
            logger.exception("Tavily search failed for: %s", claim[:80])
            return "Search unavailable — evaluating with model knowledge only."

    async def _evaluate_claim(self, claim: str, evidence: str) -> dict:
        """Ask LLM to judge a single claim against evidence."""
        try:
            prompt = VERDICT_PROMPT.format(claim=claim, evidence=evidence)
            resp = await self.llm.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content or "{}"
            result = self._parse_json(content)
            if not isinstance(result, dict):
                result = {}
            result["claim"] = claim
            return result
        except Exception:
            logger.exception("Claim evaluation failed for: %s", claim[:80])
            return {
                "claim": claim,
                "verdict": "UNVERIFIABLE",
                "confidence": 0.0,
                "explanation": "Evaluation failed due to an error.",
                "key_sources": [],
            }

    # ── Confidence calibration ─────────────────────────────────────

    @staticmethod
    def _calibrate_confidence(result: dict, evidence: str) -> float:
        """Adjust raw LLM confidence using evidence quality signals."""
        raw = float(result.get("confidence", 0.0))

        # Count how many evidence snippets were returned
        source_lines = [ln for ln in evidence.splitlines() if ln.strip().startswith("- [")]
        source_count = len(source_lines)

        if "No search results" in evidence or "Search unavailable" in evidence or "not configured" in evidence:
            # No external evidence — heavily penalise confidence
            return round(min(raw, 0.3), 2)

        if source_count == 0:
            return round(raw * 0.5, 2)

        # Boost/penalise based on evidence volume (sweet spot: 3-5 sources)
        if source_count >= 5:
            factor = 1.0
        elif source_count >= 3:
            factor = 0.9
        elif source_count >= 1:
            factor = 0.75
        else:
            factor = 0.5

        calibrated = raw * factor
        return round(max(0.0, min(calibrated, 1.0)), 2)

    # ── Aggregation ────────────────────────────────────────────────

    def _aggregate(self, claim_results: list[dict], all_sources: list[str]) -> dict:
        """Combine per-claim results into one AnalysisResult-compatible dict."""
        priority = {"FALSE": 0, "MISLEADING": 1, "PARTIALLY_TRUE": 2, "UNVERIFIABLE": 3, "TRUE": 4}

        worst = "TRUE"
        total_conf = 0.0

        for r in claim_results:
            v = r.get("verdict", "UNVERIFIABLE")
            if priority.get(v, 3) < priority.get(worst, 4):
                worst = v
            total_conf += r.get("confidence", 0.0)

        avg_conf = round(total_conf / len(claim_results), 2) if claim_results else 0.0

        return {
            "analysis_type": AnalysisType.FACT_CHECK,
            "verdict": Verdict(worst),
            "confidence_score": avg_conf,
            "summary": f"Checked {len(claim_results)} claim(s). Overall verdict: {worst}.",
            "detailed_breakdown": {"claims": claim_results},
            "sources": all_sources or None,
        }

    @staticmethod
    def _no_claims_result() -> dict:
        return {
            "analysis_type": AnalysisType.FACT_CHECK,
            "verdict": None,
            "confidence_score": None,
            "summary": "No verifiable factual claims found in the provided text.",
            "detailed_breakdown": {"claims": []},
            "sources": None,
        }
