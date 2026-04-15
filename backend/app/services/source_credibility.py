"""Source credibility ranking — maps domains to trust tiers.

Tiers and weights:
  TIER_1 (1.00) — Wire services, government, major scientific publishers
  TIER_2 (0.80) — Major international and national news outlets
  TIER_3 (0.60) — Regional news, encyclopaedias, established platforms
  TIER_4 (0.40) — Blogs, opinion platforms, aggregators
  TIER_5 (0.20) — Social media, user-generated platforms
  UNKNOWN (0.50) — Domain not in the registry

Weights are used as a multiplier on the LLM's raw confidence score during
confidence calibration inside the FactChecker agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

# ── Tier definitions ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SourceCredibility:
    domain: str
    tier: int
    weight: float
    label: str


_TIERS: dict[int, tuple[float, str]] = {
    1: (1.00, "High credibility"),
    2: (0.80, "Credible"),
    3: (0.60, "Moderate credibility"),
    4: (0.40, "Low credibility"),
    5: (0.20, "Very low credibility"),
}

UNKNOWN_TIER = 3
UNKNOWN_WEIGHT = 0.50
UNKNOWN_LABEL = "Unknown credibility"


# ── Domain registry ────────────────────────────────────────────────────────────
# Format: "domain.tld" -> tier (int)
# Subdomains (e.g. "health.gov") are resolved by stripping until a match is found.

_DOMAIN_TIERS: dict[str, int] = {
    # ── Tier 1: Wire services, government, major scientific publishers ──────────
    "apnews.com": 1,
    "reuters.com": 1,
    "afp.com": 1,
    "bloomberg.com": 1,
    "bbc.com": 1,
    "bbc.co.uk": 1,
    "npr.org": 1,
    "pbs.org": 1,
    # Government — common TLDs (subdomain stripping handles bbc.gov, cdc.gov, etc.)
    "gov.uk": 1,
    "europa.eu": 1,
    "un.org": 1,
    "who.int": 1,
    "cdc.gov": 1,
    "nih.gov": 1,
    "nasa.gov": 1,
    "whitehouse.gov": 1,
    "congress.gov": 1,
    # Scientific publishers
    "nature.com": 1,
    "science.org": 1,
    "pubmed.ncbi.nlm.nih.gov": 1,
    "ncbi.nlm.nih.gov": 1,
    "thelancet.com": 1,
    "nejm.org": 1,
    "bmj.com": 1,
    "jamanetwork.com": 1,
    "cell.com": 1,
    "sciencedirect.com": 1,
    "springer.com": 1,
    "wiley.com": 1,
    "oxfordjournals.org": 1,
    "academic.oup.com": 1,
    # Major international broadcasters
    "dw.com": 1,
    "rfi.fr": 1,
    "aljazeera.com": 1,
    "france24.com": 1,
    "abc.net.au": 1,  # Australian Broadcasting Corporation
    "cbc.ca": 1,      # Canadian Broadcasting Corporation
    # Fact-checking organisations
    "factcheck.org": 1,
    "snopes.com": 1,
    "politifact.com": 1,
    "fullfact.org": 1,
    "aap.com.au": 1,
    # ── Tier 2: Major national/international news ───────────────────────────────
    "nytimes.com": 2,
    "wsj.com": 2,
    "washingtonpost.com": 2,
    "theguardian.com": 2,
    "ft.com": 2,
    "economist.com": 2,
    "cnn.com": 2,
    "msnbc.com": 2,
    "foxnews.com": 2,
    "nbcnews.com": 2,
    "abcnews.go.com": 2,
    "cbsnews.com": 2,
    "time.com": 2,
    "newsweek.com": 2,
    "theatlantic.com": 2,
    "newyorker.com": 2,
    "politico.com": 2,
    "axios.com": 2,
    "independent.co.uk": 2,
    "telegraph.co.uk": 2,
    "thetimes.co.uk": 2,
    "lemonde.fr": 2,
    "spiegel.de": 2,
    "bild.de": 2,
    "sueddeutsche.de": 2,
    "corriere.it": 2,
    "elpais.com": 2,
    "20minutos.es": 2,
    "asahi.com": 2,
    "japantimes.co.jp": 2,
    "thehindu.com": 2,
    "ndtv.com": 2,
    "dawn.com": 2,
    "koreatimes.co.kr": 2,
    "scmp.com": 2,
    "straitstimes.com": 2,
    # ── Tier 3: Regional news, encyclopaedias, established reference ────────────
    "wikipedia.org": 3,
    "britannica.com": 3,
    "history.com": 3,
    "nationalgeographic.com": 3,
    "sciencenews.org": 3,
    "theconversation.com": 3,
    "vox.com": 3,
    "vice.com": 3,
    "huffpost.com": 3,
    "salon.com": 3,
    "slate.com": 3,
    "buzzfeednews.com": 3,
    "propublica.org": 3,
    "theintercept.com": 3,
    "motherjones.com": 3,
    "wired.com": 3,
    "arstechnica.com": 3,
    "techcrunch.com": 3,
    "theverge.com": 3,
    "engadget.com": 3,
    # ── Tier 4: Blogs, opinion, aggregators ────────────────────────────────────
    "medium.com": 4,
    "substack.com": 4,
    "wordpress.com": 4,
    "blogspot.com": 4,
    "tumblr.com": 4,
    "quora.com": 4,
    "breitbart.com": 4,
    "dailywire.com": 4,
    "infowars.com": 4,
    "naturalnews.com": 4,
    "zerohedge.com": 4,
    "rt.com": 4,
    "sputniknews.com": 4,
    # ── Tier 5: Social media / user-generated ──────────────────────────────────
    "twitter.com": 5,
    "x.com": 5,
    "facebook.com": 5,
    "instagram.com": 5,
    "tiktok.com": 5,
    "youtube.com": 5,
    "youtu.be": 5,
    "reddit.com": 5,
    "t.co": 5,        # Twitter short URL
    "fb.com": 5,
    "threads.net": 5,
    "linkedin.com": 5,
    "pinterest.com": 5,
    "snapchat.com": 5,
    "telegram.org": 5,
    "t.me": 5,
    "discord.com": 5,
    "twitch.tv": 5,
    "rumble.com": 5,
    "parler.com": 5,
    "gab.com": 5,
    "gettr.com": 5,
    "truth.social": 5,
}


# ── Public API ─────────────────────────────────────────────────────────────────


def get_credibility(url: str) -> SourceCredibility:
    """Return credibility metadata for a given URL.

    Looks up the domain, then progressively strips subdomains until a match
    is found.  Falls back to UNKNOWN constants (tier 3, weight 0.50) if not
    in the registry.

    Also handles .gov TLD — any URL ending in .gov is treated as Tier 1.
    """
    domain = _extract_domain(url)

    # Any government TLD → Tier 1
    if domain.endswith(".gov"):
        weight, label = _TIERS[1]
        return SourceCredibility(domain=domain, tier=1, weight=weight, label=label)

    # Progressive subdomain lookup against registry
    candidate = domain
    while candidate:
        if candidate in _DOMAIN_TIERS:
            tier = _DOMAIN_TIERS[candidate]
            weight, label = _TIERS[tier]
            return SourceCredibility(domain=domain, tier=tier, weight=weight, label=label)
        parts = candidate.split(".", 1)
        if len(parts) < 2:
            break
        candidate = parts[1]

    # Domain not found in registry
    return SourceCredibility(domain=domain, tier=UNKNOWN_TIER, weight=UNKNOWN_WEIGHT, label=UNKNOWN_LABEL)


# ── Internal helpers ────────────────────────────────────────────────────────────


def _extract_domain(url: str) -> str:
    """Extract bare domain from a URL string."""
    try:
        parsed = urlparse(url if url.startswith("http") else f"https://{url}")
        return (parsed.netloc or parsed.path).lower().removeprefix("www.")
    except Exception:
        return url.lower()


def _lookup_tier(domain: str) -> int:
    """Look up tier by progressively stripping subdomains.

    e.g. "health.gov" → "gov" → matches .gov rule → Tier 1
         "science.bbc.co.uk" → "bbc.co.uk" → Tier 1
    """
    # Direct .gov TLD check (any government site)
    if domain.endswith(".gov"):
        return 1

    candidate = domain
    while candidate:
        if candidate in _DOMAIN_TIERS:
            return _DOMAIN_TIERS[candidate]
        # Strip one subdomain level
        parts = candidate.split(".", 1)
        if len(parts) < 2:
            break
        candidate = parts[1]

    return UNKNOWN_TIER
