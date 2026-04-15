"""URL content extractor — fetches a URL and returns its readable text.

Uses Tavily Extract as the primary method (handles JS-rendered pages and many social
media platforms).  Falls back to httpx + basic HTML parsing as a secondary method for
simple pages when Tavily is not configured.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Maximum character length of extracted text sent to the fact-checker
MAX_CONTENT_CHARS = 8_000


@dataclass
class ExtractedContent:
    url: str
    title: str
    text: str
    source_domain: str
    extraction_method: str  # "tavily" | "httpx" | "failed"
    error: str | None = None


async def extract_url_content(url: str, tavily_api_key: str = "") -> ExtractedContent:
    """Extract readable text from a URL.

    Tries Tavily Extract first (supports JS-rendered pages, social media).
    Falls back to httpx + HTML stripping for simple pages.
    Returns an ExtractedContent even on failure (with error field set).
    """
    domain = _get_domain(url)

    if tavily_api_key:
        result = await _extract_via_tavily(url, tavily_api_key, domain)
        if result.error is None:
            return result
        logger.warning("Tavily extraction failed for %s: %s — trying httpx fallback", url[:80], result.error)

    return await _extract_via_httpx(url, domain)


# ── Tavily Extract ─────────────────────────────────────────────────────────────


async def _extract_via_tavily(url: str, api_key: str, domain: str) -> ExtractedContent:
    try:
        from tavily import AsyncTavilyClient

        client = AsyncTavilyClient(api_key=api_key)
        response = await client.extract(urls=[url])

        results = response.get("results", [])
        if not results:
            return ExtractedContent(
                url=url,
                title="",
                text="",
                source_domain=domain,
                extraction_method="tavily",
                error="Tavily returned no results",
            )

        first = results[0]
        raw_content = first.get("raw_content") or first.get("content") or ""
        title = first.get("title") or ""

        if not raw_content:
            return ExtractedContent(
                url=url,
                title=title,
                text="",
                source_domain=domain,
                extraction_method="tavily",
                error="Tavily returned empty content",
            )

        text = _clean_text(raw_content)[:MAX_CONTENT_CHARS]
        return ExtractedContent(
            url=url,
            title=title,
            text=text,
            source_domain=domain,
            extraction_method="tavily",
        )

    except Exception as exc:
        logger.exception("Tavily extract error for %s", url[:80])
        return ExtractedContent(
            url=url,
            title="",
            text="",
            source_domain=domain,
            extraction_method="tavily",
            error=str(exc),
        )


# ── httpx fallback ─────────────────────────────────────────────────────────────


async def _extract_via_httpx(url: str, domain: str) -> ExtractedContent:
    try:
        import httpx

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; AletheiaBot/1.0; +https://aletheia.ai/bot)"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(10.0),
            limits=httpx.Limits(max_connections=5),
        ) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "html" not in content_type and "text" not in content_type:
                return ExtractedContent(
                    url=url,
                    title="",
                    text="",
                    source_domain=domain,
                    extraction_method="httpx",
                    error=f"Non-HTML content-type: {content_type}",
                )

            # Limit to 1 MB to avoid parsing huge pages
            raw_html = resp.text[:1_048_576]

        title, text = _parse_html(raw_html)
        text = text[:MAX_CONTENT_CHARS]

        if not text.strip():
            return ExtractedContent(
                url=url,
                title=title,
                text="",
                source_domain=domain,
                extraction_method="httpx",
                error="No readable text found in page",
            )

        return ExtractedContent(
            url=url,
            title=title,
            text=text,
            source_domain=domain,
            extraction_method="httpx",
        )

    except Exception as exc:
        logger.exception("httpx extraction error for %s", url[:80])
        return ExtractedContent(
            url=url,
            title="",
            text="",
            source_domain=domain,
            extraction_method="httpx",
            error=str(exc),
        )


# ── HTML parsing (no dependency — pure regex soup) ────────────────────────────


def _parse_html(html: str) -> tuple[str, str]:
    """Extract title and main text from raw HTML without BeautifulSoup."""
    # Title
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = _clean_text(title_match.group(1)) if title_match else ""

    # Remove script / style / nav / footer blocks entirely
    cleaned = re.sub(r"<(script|style|nav|footer|header|aside|form)[^>]*>.*?</\1>", "", html,
                     flags=re.IGNORECASE | re.DOTALL)

    # Prefer <article> or <main> if present
    article_match = re.search(r"<(article|main)[^>]*>(.*?)</\1>", cleaned, re.IGNORECASE | re.DOTALL)
    body = article_match.group(2) if article_match else cleaned

    # Strip remaining tags, decode entities
    text = re.sub(r"<[^>]+>", " ", body)
    text = _clean_text(text)
    return title, text


def _clean_text(raw: str) -> str:
    """Decode common HTML entities and collapse whitespace."""
    entities = {
        "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&quot;": '"', "&#39;": "'", "&nbsp;": " ",
        "&#x27;": "'", "&#x2F;": "/",
    }
    for entity, char in entities.items():
        raw = raw.replace(entity, char)
    # Collapse whitespace
    return " ".join(raw.split())


def _get_domain(url: str) -> str:
    try:
        parsed = urlparse(url if url.startswith("http") else f"https://{url}")
        return (parsed.netloc or "").removeprefix("www.")
    except Exception:
        return ""
