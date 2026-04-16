"""URL detection and content extraction utility.

Detects URLs in user input, fetches the page content (via Tavily Extract or httpx
fallback), and returns the readable text. Used by chat dispatch to pre-process input
before sending to agents like FactChecker or TextDetector.
"""

from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)

# Matches common http/https URLs
_URL_RE = re.compile(r"https?://[^\s<>\"'\)\]]+", re.IGNORECASE)

MAX_CONTENT_CHARS = 12_000


def extract_urls(text: str) -> list[str]:
    """Return deduplicated list of URLs found in text (max 3)."""
    seen: set[str] = set()
    urls: list[str] = []
    for m in _URL_RE.finditer(text):
        url = m.group().rstrip(".,;:!?)")
        if url not in seen:
            seen.add(url)
            urls.append(url)
        if len(urls) >= 3:
            break
    return urls


def looks_like_url_only(text: str) -> bool:
    """Return True if the text is just a URL (possibly with whitespace)."""
    stripped = text.strip()
    return bool(_URL_RE.fullmatch(stripped.rstrip(".,;:!?)")))


async def fetch_url_text(url: str, tavily_api_key: str = "") -> str | None:
    """Fetch readable text from a URL. Returns None on failure.

    Tries Tavily Extract first (handles JS-rendered pages).
    Falls back to httpx + basic HTML tag stripping.
    """
    if tavily_api_key:
        result = await _fetch_via_tavily(url, tavily_api_key)
        if result:
            return result
        logger.warning("Tavily extraction failed for %s — trying httpx fallback", url[:80])

    return await _fetch_via_httpx(url)


async def _fetch_via_tavily(url: str, api_key: str) -> str | None:
    try:
        from tavily import AsyncTavilyClient

        client = AsyncTavilyClient(api_key=api_key)
        response = await client.extract(urls=[url])

        results = response.get("results", [])
        if not results:
            return None

        first = results[0]
        raw_content = first.get("raw_content") or first.get("content") or ""
        if not raw_content:
            return None

        return _clean_text(raw_content)[:MAX_CONTENT_CHARS]
    except Exception:
        logger.exception("Tavily extract error for %s", url[:80])
        return None


async def _fetch_via_httpx(url: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Aletheia/1.0"})
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type and "text/plain" not in content_type:
                return None
            html = resp.text
            text = _strip_html(html)
            text = _clean_text(text)
            return text[:MAX_CONTENT_CHARS] if text else None
    except Exception:
        logger.exception("httpx fetch error for %s", url[:80])
        return None


def _strip_html(html: str) -> str:
    """Remove HTML tags, scripts, styles and return plain text."""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)  # HTML entities
    text = re.sub(r"&#?\w+;", " ", text)
    return text


def _clean_text(text: str) -> str:
    """Collapse whitespace and strip."""
    text = re.sub(r"\s+", " ", text)
    return text.strip()
