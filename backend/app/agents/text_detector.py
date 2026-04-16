"""AI-generated text detection agent — uses Sapling API for detection + LLM for explanation.

Sapling provides statistical AI-probability scores at document, sentence, and token level.
The LLM then interprets the raw scores into a human-readable explanation.
Falls back to LLM-only heuristic analysis when no Sapling API key is configured.
"""

import json
import logging
import re

import httpx
from openai import AsyncOpenAI

from app.core.config import Settings
from app.models import AnalysisType, Verdict

logger = logging.getLogger(__name__)

MIN_TEXT_LENGTH = 100

EXPLANATION_PROMPT = """\
You are an AI text-detection analyst. You have been given the results of a statistical AI \
detection scan on a piece of text. Summarise the findings in 2-4 concise sentences for a \
non-technical user.

Overall AI probability: {score:.0%}
Classification: {classification}

Sentences flagged as likely AI-generated:
{flagged_sentences}

Do NOT repeat the raw numbers. Instead explain *why* the text may or may not be AI-generated \
(e.g. uniform sentence structure, predictable word choice, low stylistic variation, etc.). \
Be balanced — note any human-like qualities too."""

FALLBACK_PROMPT = """\
You are an AI text-authenticity analyst. Examine the provided text for signs of AI generation: \
low perplexity, burstiness patterns, repetitive phrasing, lack of personal voice.
Provide your analysis as a JSON object with these fields:
- "ai_probability": float 0-1 (your best estimate)
- "classification": "ai-generated" | "mixed" | "human-written"
- "explanation": string (2-3 sentences explaining your reasoning)
- "signals": list of {"label": string, "value": string, "flag": "warn" | "ok" | "info"}
Return ONLY valid JSON."""


class TextDetector:
    """Detects AI-generated text using Sapling API with LLM explanation."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.llm = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )
        self.model = settings.openrouter_model

    async def detect(self, text: str) -> dict:
        """Run AI text detection pipeline. Returns dict matching AnalysisResult fields."""
        if len(text.strip()) < MIN_TEXT_LENGTH:
            return self._insufficient_text_result()

        if self.settings.sapling_api_key:
            return await self._detect_with_sapling(text)
        return await self._detect_with_llm_fallback(text)

    # ── Sapling-based detection ────────────────────────────────────

    async def _detect_with_sapling(self, text: str) -> dict:
        """Primary path: Sapling API for detection + LLM for explanation."""
        sapling_data = await self._call_sapling(text)
        if sapling_data is None:
            # Sapling failed — fall back to LLM-only
            return await self._detect_with_llm_fallback(text)

        score = sapling_data.get("score", 0.5)
        sentence_scores = sapling_data.get("sentence_scores", [])

        classification = self._classify(score)
        verdict = self._score_to_verdict(score)

        # Build sentence analysis
        sentence_analysis = []
        for s in sentence_scores:
            sent_score = s.get("score", 0.5)
            sentence_analysis.append(
                {
                    "sentence": s.get("sentence", ""),
                    "ai_probability": round(sent_score, 3),
                    "flag": "ai" if sent_score >= 0.65 else "human" if sent_score < 0.3 else "mixed",
                }
            )

        # Count flagged sentences
        ai_count = sum(1 for s in sentence_analysis if s["flag"] == "ai")
        total_count = len(sentence_analysis) or 1

        # Generate human-readable explanation via LLM
        flagged_texts = [
            f'- "{s["sentence"][:120]}" ({s["ai_probability"]:.0%})' for s in sentence_analysis if s["flag"] == "ai"
        ][:5]
        flagged_str = "\n".join(flagged_texts) if flagged_texts else "(none)"

        explanation = await self._generate_explanation(score, classification, flagged_str)

        # Build signals
        signals = [
            {"label": "Overall AI probability", "value": f"{score:.0%}", "flag": "warn" if score >= 0.65 else "ok"},
            {
                "label": "Sentences flagged as AI",
                "value": f"{ai_count} of {total_count}",
                "flag": "warn" if ai_count > total_count / 2 else "ok",
            },
        ]

        confidence = round(abs(score - 0.5) * 2, 2)  # 0.5 → 0.0 confidence, 0.0/1.0 → 1.0 confidence

        return {
            "analysis_type": AnalysisType.TEXT_DETECTION,
            "verdict": verdict,
            "confidence_score": confidence,
            "summary": f"This text has a {score:.0%} probability of being AI-generated.",
            "detailed_breakdown": {
                "ai_score": round(score, 4),
                "classification": classification,
                "sentence_analysis": sentence_analysis,
                "explanation": explanation,
                "signals": signals,
            },
            "sources": None,
        }

    async def _call_sapling(self, text: str) -> dict | None:
        """Call Sapling AI Detector API. Returns parsed response or None on failure."""
        url = "https://api.sapling.ai/api/v1/aidetect"
        payload = {
            "key": self.settings.sapling_api_key,
            "text": text[:200_000],  # Sapling limit
            "sent_scores": True,
        }

        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    return resp.json()
            except httpx.TimeoutException:
                logger.warning("Sapling API timeout (attempt %d)", attempt + 1)
            except httpx.HTTPStatusError as e:
                logger.error("Sapling API error %s: %s", e.response.status_code, e.response.text[:200])
                return None
            except Exception:
                logger.exception("Sapling API unexpected error (attempt %d)", attempt + 1)

        logger.error("Sapling API failed after 2 attempts")
        return None

    async def _generate_explanation(self, score: float, classification: str, flagged_sentences: str) -> str:
        """Use LLM to generate a human-readable explanation of Sapling results."""
        try:
            prompt = EXPLANATION_PROMPT.format(
                score=score,
                classification=classification,
                flagged_sentences=flagged_sentences,
            )
            resp = await self.llm.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception:
            logger.exception("LLM explanation generation failed")
            return "Analysis complete. See the detailed signals above for more information."

    # ── LLM-only fallback ──────────────────────────────────────────

    async def _detect_with_llm_fallback(self, text: str) -> dict:
        """Fallback: use LLM heuristic analysis when Sapling is unavailable."""
        try:
            resp = await self.llm.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": FALLBACK_PROMPT},
                    {"role": "user", "content": text[:10_000]},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
                timeout=30,
            )
            content = resp.choices[0].message.content or "{}"
            parsed = self._parse_json(content)
        except Exception:
            logger.exception("LLM fallback detection failed")
            parsed = {}

        ai_prob = float(parsed.get("ai_probability", 0.5))
        classification = parsed.get("classification", "mixed")
        explanation = parsed.get("explanation", "Analysis could not be completed.")
        signals = parsed.get("signals", [])

        verdict = self._score_to_verdict(ai_prob)
        confidence = round(abs(ai_prob - 0.5) * 2, 2)

        return {
            "analysis_type": AnalysisType.TEXT_DETECTION,
            "verdict": verdict,
            "confidence_score": confidence,
            "summary": (
                f"This text has a {ai_prob:.0%} estimated probability of being"
                " AI-generated. (LLM heuristic — no dedicated detector configured.)"
            ),
            "detailed_breakdown": {
                "ai_score": round(ai_prob, 4),
                "classification": classification,
                "sentence_analysis": [],
                "explanation": explanation,
                "signals": signals,
            },
            "sources": None,
        }

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _classify(score: float) -> str:
        if score >= 0.65:
            return "ai-generated"
        if score < 0.3:
            return "human-written"
        return "mixed"

    @staticmethod
    def _score_to_verdict(score: float) -> Verdict:
        if score >= 0.65:
            return Verdict.FALSE  # AI-Generated
        if score < 0.3:
            return Verdict.TRUE  # Human-Written
        return Verdict.PARTIALLY_TRUE  # Mixed

    @staticmethod
    def _insufficient_text_result() -> dict:
        return {
            "analysis_type": AnalysisType.TEXT_DETECTION,
            "verdict": Verdict.UNVERIFIABLE,
            "confidence_score": None,
            "summary": "Insufficient text for reliable AI detection. Please provide at least 100 characters.",
            "detailed_breakdown": {
                "ai_score": None,
                "classification": "insufficient",
                "sentence_analysis": [],
                "explanation": "The text is too short for meaningful analysis.",
                "signals": [],
            },
            "sources": None,
        }

    @staticmethod
    def _parse_json(raw: str) -> dict:
        text = raw.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
        if not text:
            return {}
        try:
            result = json.loads(text)
            return result if isinstance(result, dict) else {}
        except json.JSONDecodeError:
            return {}
