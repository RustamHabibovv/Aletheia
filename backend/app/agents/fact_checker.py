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
from app.services.source_credibility import get_credibility

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
        search_results = await asyncio.gather(*(self._search_evidence(claim) for claim in claims))
        evidence_texts = [r[0] for r in search_results]
        evidence_sources = [r[1] for r in search_results]

        # Evaluate all claims against their evidence in parallel
        raw_results = await asyncio.gather(
            *(self._evaluate_claim(claim, evidence) for claim, evidence in zip(claims, evidence_texts, strict=True))
        )

        # Calibrate confidence based on evidence quality and source credibility
        claim_results = []
        all_sources: list[dict] = []
        seen_urls: set[str] = set()
        for result, evidence_text, sources in zip(raw_results, evidence_texts, evidence_sources, strict=True):
            result["confidence"] = self._calibrate_confidence(result, evidence_text, sources)
            claim_results.append(result)
            for src in sources:
                if src["url"] not in seen_urls:
                    seen_urls.add(src["url"])
                    all_sources.append(src)

        return self._aggregate(claim_results, all_sources)

    # ── Pipeline steps ─────────────────────────────────────────────

    async def _extract_claims(self, text: str) -> list[str]:
        """Use LLM to pull out verifiable factual claims."""
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                resp = await self.llm.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": CLAIM_EXTRACTION_PROMPT},
                        {"role": "user", "content": text},
                    ],
                    temperature=0.1,
                    response_format={"type": "json_object"},
                    timeout=30,
                )
                content = resp.choices[0].message.content or "{}"
                parsed = self._parse_json(content)
                if isinstance(parsed, dict):
                    return parsed.get("claims", [])[:10]
                if isinstance(parsed, list):
                    return parsed[:10]
                return []
            except Exception as exc:
                last_exc = exc
                logger.warning("Claim extraction attempt %d failed: %s", attempt + 1, exc)
                if attempt == 0:
                    await asyncio.sleep(1)

        # Both attempts failed — re-raise so the caller surfaces a real error
        logger.error("Claim extraction failed after 2 attempts")
        raise last_exc  # type: ignore[misc]

    async def _search_evidence(self, claim: str) -> tuple[str, list[dict]]:
        """Search the web for evidence using Tavily. Returns (evidence_text, structured_sources)."""
        if not self.settings.tavily_api_key:
            return "No search results available (Tavily API key not configured).", []

        try:
            from tavily import AsyncTavilyClient

            client = AsyncTavilyClient(api_key=self.settings.tavily_api_key)
            results = await client.search(query=claim, max_results=10)
            snippets = []
            sources: list[dict] = []
            for r in results.get("results", []):
                title = r.get("title", "Source")
                url = r.get("url", "")
                content = r.get("content", "")[:300]
                snippets.append(f"- [{title}]({url}): {content}")
                if url:
                    cred = get_credibility(url)
                    sources.append(
                        {
                            "title": title,
                            "url": url,
                            "credibility_tier": cred.tier,
                            "credibility_weight": cred.weight,
                            "credibility_label": cred.label,
                        }
                    )
            evidence = "\n".join(snippets) if snippets else "No relevant results found."
            return evidence, sources
        except Exception:
            logger.exception("Tavily search failed for: %s", claim[:80])
            return "Search unavailable — evaluating with model knowledge only.", []

    async def _evaluate_claim(self, claim: str, evidence: str) -> dict:
        """Ask LLM to judge a single claim against evidence."""
        try:
            prompt = VERDICT_PROMPT.format(claim=claim, evidence=evidence)
            resp = await self.llm.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"},
                timeout=30,
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
    def _calibrate_confidence(result: dict, evidence: str, sources: list[dict] | None = None) -> float:
        """Adjust raw LLM confidence using evidence quality signals and source credibility."""
        raw = float(result.get("confidence", 0.0))

        # Count how many evidence snippets were returned
        source_lines = [ln for ln in evidence.splitlines() if ln.strip().startswith("- [")]
        source_count = len(source_lines)

        if "No search results" in evidence or "Search unavailable" in evidence or "not configured" in evidence:
            # No external evidence — heavily penalise confidence
            return round(min(raw, 0.3), 2)

        if source_count == 0:
            return round(raw * 0.5, 2)

        # Factor 1: evidence volume
        if source_count >= 5:
            volume_factor = 1.0
        elif source_count >= 3:
            volume_factor = 0.95
        elif source_count >= 1:
            volume_factor = 0.85
        else:
            volume_factor = 0.5

        # Factor 2: source credibility.
        # Uses best_weight*0.7 + avg_weight*0.3 so that having even one reliable
        # source (Reuters alongside TikTok) keeps the score high.  Penalty only
        # applies when *all* sources are low-tier (e.g. purely social media).
        #
        # Examples (remapped → credibility_factor):
        #   Reuters(1.0) + 2×TikTok(0.2):  eff=0.84 → factor 0.94
        #   3×Wikipedia(0.6):               eff=0.60 → factor 0.84
        #   3×TikTok(0.2):                  eff=0.20 → factor 0.68
        if sources:
            weights = [s.get("credibility_weight", 0.5) for s in sources]
            best_weight = max(weights)
            avg_weight = sum(weights) / len(weights)
            effective_weight = best_weight * 0.7 + avg_weight * 0.3
        else:
            effective_weight = 0.8  # no data → assume decent, don't penalise
        credibility_factor = 0.6 + effective_weight * 0.4

        calibrated = raw * volume_factor * credibility_factor
        return round(max(0.0, min(calibrated, 1.0)), 2)

    # ── Aggregation ────────────────────────────────────────────────

    def _aggregate(self, claim_results: list[dict], all_sources: list[dict]) -> dict:
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
