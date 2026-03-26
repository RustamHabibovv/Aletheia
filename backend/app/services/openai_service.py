"""OpenAI service — generates assistant replies with tool-specific system prompts."""

import logging

from openai import AsyncOpenAI

from app.core.config import Settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPTS: dict[str, str] = {
    "general": (
        "You are Aletheia, an AI assistant specialising in misinformation detection. "
        "Analyse the user's content for factual accuracy, potential misinformation, "
        "and credibility. Provide a structured, evidence-based assessment."
    ),
    "fact-check": (
        "You are Aletheia, an expert fact-checker. Extract all verifiable factual claims "
        "from the user's message and assess each one against established knowledge. "
        "State your verdict (True / False / Partially True / Unverifiable / Misleading) "
        "with a confidence percentage and brief explanation for each claim."
    ),
    "image-detection": (
        "You are Aletheia, an AI image-authenticity analyst. The user will describe an image "
        "or provide context about it. Analyse potential indicators of AI generation, deepfake "
        "manipulation, or digital tampering. Provide a verdict with confidence score and key "
        "observations (artefacts, inconsistencies, lighting, metadata anomalies)."
    ),
    "text-detection": (
        "You are Aletheia, an AI text-authenticity analyst. Examine the provided text for "
        "signs of AI generation: low perplexity, burstiness patterns, repetitive phrasing, "
        "lack of personal voice. Provide a verdict (AI-generated / Human-written / Mixed) "
        "with confidence score and supporting observations."
    ),
    "video-detection": (
        "You are Aletheia, an AI deepfake detection analyst. The user will describe a video "
        "or provide context. Analyse for deepfake indicators: facial blending artefacts, "
        "unnatural blinking, lip-sync inconsistencies, lighting mismatches. Provide a verdict "
        "with confidence score and frame-level observations where possible."
    ),
    "bot-detection": (
        "You are Aletheia, a social media bot-detection analyst. Analyse the provided account "
        "description or username for bot-behaviour signals: posting frequency, account age, "
        "follower/following ratio, content originality, coordinated activity. Provide a verdict "
        "(Bot / Likely Bot / Human / Likely Human) with confidence score and key indicators."
    ),
}

DEFAULT_SYSTEM_PROMPT = SYSTEM_PROMPTS["general"]

MOCK_REPLIES: dict[str, str] = {
    "general": (
        "I've analysed the content you provided. Based on the available signals, "
        "the information shows mixed credibility indicators. The narrative structure "
        "and source attribution appear inconsistent with established reporting standards. "
        "I recommend cross-referencing with at least two independent primary sources "
        "before drawing conclusions."
    ),
    "fact-check": (
        "**Fact-check complete.**\n\n"
        "I identified 2 verifiable claims in your message:\n\n"
        "1. **Claim 1** — *Unverifiable* (65% confidence). Insufficient primary source "
        "evidence to confirm or deny.\n"
        "2. **Claim 2** — *Likely False* (78% confidence). Contradicted by peer-reviewed "
        "literature and official statements from relevant authorities.\n\n"
        "Overall verdict: **Misleading**. The framing omits key context that materially "
        "changes the interpretation."
    ),
    "image-detection": (
        "**Image analysis complete.**\n\n"
        "Verdict: **Likely AI-Generated** (82% confidence)\n\n"
        "Key indicators detected:\n"
        "- Unnatural texture smoothing around facial features\n"
        "- GAN-characteristic background blur inconsistency\n"
        "- Metadata anomalies: no EXIF camera data present\n"
        "- Lighting direction inconsistent with shadow angles\n\n"
        "Recommendation: treat as unverified synthetic content."
    ),
    "text-detection": (
        "**Text analysis complete.**\n\n"
        "Verdict: **Likely AI-Generated** (74% confidence)\n\n"
        "Signals detected:\n"
        "- Low perplexity score (12.3) — unusually predictable token distribution\n"
        "- Burstiness score: 0.21 (human text typically scores >0.6)\n"
        "- Repetitive sentence structure patterns across paragraphs\n"
        "- Absence of personal voice, hedging, or idiomatic expression\n\n"
        "The text reads as machine-generated, likely via a large language model."
    ),
    "video-detection": (
        "**Video analysis complete.**\n\n"
        "Verdict: **Deepfake detected** (71% confidence)\n\n"
        "Frame-level findings:\n"
        "- Face-swap artefacts in 34% of analysed frames\n"
        "- Temporal flickering around jaw and hairline regions\n"
        "- Lip-sync delay: ~80ms offset from audio track\n"
        "- Blending boundary visible under contrast enhancement\n\n"
        "Treat this content as manipulated until independently verified."
    ),
    "bot-detection": (
        "**Account analysis complete.**\n\n"
        "Verdict: **Likely Bot** (89% confidence)\n\n"
        "Behavioural signals:\n"
        "- Posting frequency: 112 posts/day (>10× human average)\n"
        "- Account age: 23 days with >2,000 posts\n"
        "- Content originality: 94% retweets/reposts, <6% original\n"
        "- Coordinated activity detected with 14 similar accounts\n"
        "- Follower/following ratio: 1:47 (typical bot pattern)\n\n"
        "High probability of automated or semi-automated operation."
    ),
}


def generate_mock_reply(tool: str) -> str:
    return MOCK_REPLIES.get(tool, MOCK_REPLIES["general"])


async def generate_reply(
    tool: str,
    history: list[dict[str, str]],
    user_content: str,
    settings: Settings,
) -> str:
    """Generate an assistant reply using OpenAI.

    Args:
        tool: Frontend tool identifier (e.g. "fact-check").
        history: Previous messages as {"role": "user"|"assistant", "content": str}.
        user_content: The new user message.
        settings: App settings (provides API key).

    Returns:
        The assistant's reply text.
    """
    client = AsyncOpenAI(api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url)
    system_prompt = SYSTEM_PROMPTS.get(tool, DEFAULT_SYSTEM_PROMPT)

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_content})

    response = await client.chat.completions.create(
        model=settings.openrouter_model,
        messages=messages,  # type: ignore[arg-type]
        max_tokens=1024,
        temperature=0.3,
    )
    return response.choices[0].message.content or ""
