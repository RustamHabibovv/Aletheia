"""URL detection utilities — find HTTP/HTTPS URLs in free-form text."""

import re

# Matches http/https URLs, including paths and query strings.
# Stops at whitespace, quotes, parentheses, and common sentence-ending punctuation.
_URL_RE = re.compile(
    r"https?://"  # scheme
    r"(?:[a-zA-Z0-9\-._~:/?#\[\]@!$&'()*+,;=%])"  # first char (no space)
    r"[a-zA-Z0-9\-._~:/?#\[\]@!$&'*+,;=%]*",  # rest of URL
    re.IGNORECASE,
)

MAX_URLS_PER_REQUEST = 3


def extract_urls(text: str) -> list[str]:
    """Return up to MAX_URLS_PER_REQUEST unique HTTP/HTTPS URLs found in text.

    Strips trailing punctuation that commonly appears at the end of a URL
    embedded in a sentence (e.g. periods, commas, closing brackets).
    """
    matches = _URL_RE.findall(text)
    cleaned: list[str] = []
    seen: set[str] = set()
    for url in matches:
        # Strip trailing sentence punctuation that isn't part of the URL
        url = url.rstrip(".,;:!?)\"'")
        if url not in seen:
            seen.add(url)
            cleaned.append(url)
        if len(cleaned) >= MAX_URLS_PER_REQUEST:
            break
    return cleaned
