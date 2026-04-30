"""Single source of truth for supported regions.

Each Region carries every locale-specific knob a source needs - pytrends pn,
Google's gl/hl, language label for the analyzer, and curated subreddit list.
Add a region by appending to REGIONS - no source-side changes needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Region:
    code: str               # ISO 3166-1 alpha-2, used as primary key in storage
    name: str               # Human label for prompts/reports
    pytrends_pn: str        # pytrends country slug
    gl: str                 # Google geolocation param (alpha-2)
    hl: str                 # Google language param (BCP-47)
    language: str           # Human language label for analyzer prompt
    reddit_subs: list[str] = field(default_factory=list)


REGIONS: dict[str, Region] = {
    r.code: r for r in [
        Region(
            code="US", name="United States",
            pytrends_pn="united_states", gl="US", hl="en-US", language="English",
            reddit_subs=[
                "BuyItForLife", "ProductPorn", "AmazonFinds", "ShopRecommendations",
                "deals", "tiktokproducts", "Skincare_Addiction", "malefashionadvice",
                "femalefashionadvice",
            ],
        ),
        Region(
            code="GB", name="United Kingdom",
            pytrends_pn="united_kingdom", gl="GB", hl="en-GB", language="English",
            reddit_subs=[
                "UKDeals", "CasualUK", "ukfood", "BritishProblems", "AskUK",
                "UnitedKingdom",
            ],
        ),
        Region(
            code="FR", name="France",
            pytrends_pn="france", gl="FR", hl="fr-FR", language="French",
            reddit_subs=["france", "AskFrance", "QuelLeBonCoin"],
        ),
        Region(
            code="DE", name="Germany",
            pytrends_pn="germany", gl="DE", hl="de-DE", language="German",
            reddit_subs=["de", "Finanzen", "GermanShopping"],
        ),
        Region(
            code="AU", name="Australia",
            pytrends_pn="australia", gl="AU", hl="en-AU", language="English",
            reddit_subs=["australia", "AusFinance", "ozbargain", "AusShopping"],
        ),
        Region(
            code="CA", name="Canada",
            pytrends_pn="canada", gl="CA", hl="en-CA", language="English",
            reddit_subs=[
                "canada", "PersonalFinanceCanada", "BuyCanadian", "askTO",
                "vancouver",
            ],
        ),
        Region(
            code="AE", name="United Arab Emirates",
            pytrends_pn="united_arab_emirates", gl="AE", hl="en-AE",
            language="English (Arabic also common)",
            reddit_subs=["dubai", "UAE"],
        ),
        Region(
            code="SA", name="Saudi Arabia",
            pytrends_pn="saudi_arabia", gl="SA", hl="ar-SA",
            language="Arabic (English also common)",
            reddit_subs=["saudiarabia"],
        ),
        Region(
            code="CH", name="Switzerland",
            pytrends_pn="switzerland", gl="CH", hl="de-CH",
            language="German, French, Italian",
            reddit_subs=["Switzerland", "askswitzerland", "Schweiz"],
        ),
    ]
}

ALL_CODES: list[str] = list(REGIONS.keys())


def resolve(codes: list[str] | None) -> list[Region]:
    """Resolve user-supplied region codes (case-insensitive) to Region objects."""
    if not codes:
        return list(REGIONS.values())
    out: list[Region] = []
    for c in codes:
        key = c.upper()
        if key not in REGIONS:
            raise ValueError(f"unknown region {c!r}; supported: {', '.join(ALL_CODES)}")
        out.append(REGIONS[key])
    return out
