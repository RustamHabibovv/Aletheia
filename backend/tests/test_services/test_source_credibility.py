"""Tests for source credibility ranking."""


from app.services.source_credibility import (
    SourceCredibility,
    _extract_domain,
    _lookup_tier,
    get_credibility,
)

# ── Domain extraction ─────────────────────────────────────────────────────────


def test_extract_domain_full_url():
    assert _extract_domain("https://www.bbc.com/news/article") == "bbc.com"


def test_extract_domain_no_scheme():
    assert _extract_domain("reuters.com/article") == "reuters.com"


def test_extract_domain_subdomain():
    assert _extract_domain("https://health.bbc.co.uk/page") == "health.bbc.co.uk"


# ── Tier lookup ───────────────────────────────────────────────────────────────


def test_tier1_direct_match():
    assert _lookup_tier("bbc.com") == 1
    assert _lookup_tier("reuters.com") == 1
    assert _lookup_tier("apnews.com") == 1


def test_tier1_gov_tld():
    assert _lookup_tier("cdc.gov") == 1
    assert _lookup_tier("fda.gov") == 1
    assert _lookup_tier("someagency.gov") == 1  # any .gov is Tier 1


def test_tier1_subdomain_stripped():
    # "health.bbc.co.uk" → strip "health" → "bbc.co.uk" → Tier 1
    assert _lookup_tier("health.bbc.co.uk") == 1


def test_tier2_major_news():
    assert _lookup_tier("nytimes.com") == 2
    assert _lookup_tier("theguardian.com") == 2
    assert _lookup_tier("cnn.com") == 2


def test_tier5_social_media():
    assert _lookup_tier("tiktok.com") == 5
    assert _lookup_tier("twitter.com") == 5
    assert _lookup_tier("x.com") == 5
    assert _lookup_tier("instagram.com") == 5
    assert _lookup_tier("facebook.com") == 5
    assert _lookup_tier("youtube.com") == 5
    assert _lookup_tier("reddit.com") == 5


def test_unknown_domain_returns_tier3():
    # Unknown domain falls back to UNKNOWN_TIER = 3
    assert _lookup_tier("randomobscureblog12345.net") == 3


# ── Full get_credibility ──────────────────────────────────────────────────────


def test_get_credibility_bbc():
    cred = get_credibility("https://www.bbc.com/news/world")
    assert isinstance(cred, SourceCredibility)
    assert cred.tier == 1
    assert cred.weight == 1.0
    assert cred.domain == "bbc.com"


def test_get_credibility_tiktok():
    cred = get_credibility("https://www.tiktok.com/@user/video/123")
    assert cred.tier == 5
    assert cred.weight == 0.2


def test_get_credibility_unknown():
    cred = get_credibility("https://www.somerandomblog.xyz/post/1")
    assert cred.tier == 3
    assert cred.weight == 0.50


def test_get_credibility_gov_url():
    cred = get_credibility("https://www.cdc.gov/report")
    assert cred.tier == 1
    assert cred.weight == 1.0


def test_get_credibility_returns_label():
    cred = get_credibility("https://reuters.com/article")
    assert "credibility" in cred.label.lower() or cred.label != ""
