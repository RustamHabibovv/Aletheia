"""Tests for URL content extraction utilities."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.url_extractor import (
    _clean_text,
    _get_domain,
    _parse_html,
    extract_url_content,
)
from app.utils.url_detect import extract_urls

# ── URL detection ─────────────────────────────────────────────────────────────


def test_extract_urls_simple():
    assert extract_urls("Check https://bbc.com for details") == ["https://bbc.com"]


def test_extract_urls_multiple():
    text = "See https://bbc.com and https://reuters.com for the full story."
    urls = extract_urls(text)
    assert "https://bbc.com" in urls
    assert "https://reuters.com" in urls


def test_extract_urls_max_3():
    text = "https://a.com https://b.com https://c.com https://d.com https://e.com"
    assert len(extract_urls(text)) == 3


def test_extract_urls_strips_trailing_punctuation():
    urls = extract_urls("See https://example.com/article. For more info.")
    assert urls[0] == "https://example.com/article"


def test_extract_urls_no_urls():
    assert extract_urls("No links here at all.") == []


def test_extract_urls_deduplicates():
    text = "https://bbc.com https://bbc.com"
    assert extract_urls(text) == ["https://bbc.com"]


# ── HTML parsing ──────────────────────────────────────────────────────────────


def test_parse_html_extracts_title():
    html = "<html><head><title>Test Article</title></head><body><p>Hello</p></body></html>"
    title, text = _parse_html(html)
    assert title == "Test Article"


def test_parse_html_extracts_article_body():
    html = """
    <html><body>
      <nav>Navigation stuff</nav>
      <article><p>Main content here. This is the story.</p></article>
      <footer>Footer junk</footer>
    </body></html>
    """
    _, text = _parse_html(html)
    assert "Main content" in text
    # Navigation and footer should be stripped
    assert "Navigation stuff" not in text


def test_parse_html_strips_scripts():
    html = "<html><body><script>alert('xss')</script><p>Clean text</p></body></html>"
    _, text = _parse_html(html)
    assert "alert" not in text
    assert "Clean text" in text


def test_clean_text_decodes_entities():
    assert _clean_text("Tom &amp; Jerry") == "Tom & Jerry"
    assert _clean_text("&lt;b&gt;bold&lt;/b&gt;") == "<b>bold</b>"
    assert _clean_text("non&nbsp;breaking") == "non breaking"


def test_get_domain():
    assert _get_domain("https://www.bbc.com/news/article") == "bbc.com"
    assert _get_domain("https://sub.example.org/path") == "sub.example.org"


# ── Tavily extraction ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_url_content_tavily_success():
    mock_client = AsyncMock()
    mock_client.extract.return_value = {
        "results": [
            {
                "title": "BBC Article",
                "raw_content": "This is the full article text about important news.",
            }
        ]
    }

    with patch("tavily.AsyncTavilyClient", return_value=mock_client):
        result = await extract_url_content("https://bbc.com/news/1", tavily_api_key="test-key")

    assert result.error is None
    assert result.extraction_method == "tavily"
    assert result.title == "BBC Article"
    assert "article text" in result.text


@pytest.mark.asyncio
async def test_extract_url_content_tavily_empty_falls_back():
    """When Tavily returns no content, falls back to httpx."""
    mock_tavily = AsyncMock()
    mock_tavily.extract.return_value = {"results": []}

    mock_response = AsyncMock()
    mock_response.headers = {"content-type": "text/html"}
    mock_response.text = "<html><head><title>Fallback</title></head><body><p>Fallback text</p></body></html>"
    mock_response.raise_for_status = AsyncMock()

    with (
        patch("tavily.AsyncTavilyClient", return_value=mock_tavily),
        patch("httpx.AsyncClient") as mock_httpx_class,
    ):
        mock_httpx_instance = AsyncMock()
        mock_httpx_instance.__aenter__ = AsyncMock(return_value=mock_httpx_instance)
        mock_httpx_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_instance.get = AsyncMock(return_value=mock_response)
        mock_httpx_class.return_value = mock_httpx_instance

        result = await extract_url_content("https://example.com", tavily_api_key="test-key")

    # Either tavily or httpx succeeded
    assert result is not None


@pytest.mark.asyncio
async def test_extract_url_content_no_tavily_key():
    """Without a Tavily key, falls back to httpx directly."""

    mock_response = AsyncMock()
    mock_response.headers = {"content-type": "text/html"}
    mock_response.text = "<html><body><article><p>News article text here.</p></article></body></html>"
    mock_response.raise_for_status = AsyncMock()

    with patch("httpx.AsyncClient") as mock_httpx_class:
        mock_httpx_instance = AsyncMock()
        mock_httpx_instance.__aenter__ = AsyncMock(return_value=mock_httpx_instance)
        mock_httpx_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_instance.get = AsyncMock(return_value=mock_response)
        mock_httpx_class.return_value = mock_httpx_instance

        result = await extract_url_content("https://example.com/article", tavily_api_key="")

    assert result.extraction_method == "httpx"
    assert "News article text" in result.text


@pytest.mark.asyncio
async def test_extract_url_content_httpx_error_returns_error():
    """Errors are captured gracefully, not raised."""
    with patch("httpx.AsyncClient") as mock_httpx_class:
        mock_httpx_instance = AsyncMock()
        mock_httpx_instance.__aenter__ = AsyncMock(return_value=mock_httpx_instance)
        mock_httpx_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_instance.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_httpx_class.return_value = mock_httpx_instance

        result = await extract_url_content("https://unreachable.example", tavily_api_key="")

    assert result.error is not None
    assert result.text == ""
