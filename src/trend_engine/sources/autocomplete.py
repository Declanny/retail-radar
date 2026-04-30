"""Google autocomplete source. Mines suggestions for product-intent seed phrases.

Uses Google's public suggestion endpoint with region-specific gl + hl.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from ..regions import Region
from .base import Source, Trend

log = logging.getLogger(__name__)

ENDPOINT = "https://suggestqueries.google.com/complete/search"

# Multilingual product-intent seeds. Each region uses the matching language(s).
SEEDS_BY_LANG: dict[str, list[str]] = {
    "en": ["best", "buy", "trending", "new", "must have", "viral", "tiktok made me buy",
           "amazon", "gift for"],
    "fr": ["meilleur", "acheter", "tendance", "nouveau", "incontournable",
           "viral", "cadeau pour"],
    "de": ["bester", "kaufen", "trend", "neu", "muss haben", "viral",
           "geschenk fuer"],
    "ar": ["أفضل", "شراء", "جديد", "هدية"],
}


def _seeds_for(region: Region) -> list[str]:
    primary = region.hl.split("-")[0].lower()
    seeds = list(SEEDS_BY_LANG.get(primary, SEEDS_BY_LANG["en"]))
    # Multilingual regions: also fold in English (common online)
    if primary not in ("en",) and region.code in ("CH", "AE", "SA", "DE", "FR"):
        seeds += SEEDS_BY_LANG["en"][:5]
    return seeds


class AutocompleteSource:
    name = "google_autocomplete"

    def __init__(self, expand: bool = True, concurrency: int = 8) -> None:
        self.expand = expand
        self._sem = asyncio.Semaphore(concurrency)

    async def fetch(self, region: Region) -> list[Trend]:
        seeds = _seeds_for(region)
        seen: set[str] = set()
        out: list[Trend] = []

        async with httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 trend-engine/0.1"},
            timeout=8.0,
        ) as client:
            queries = self._expand(seeds)
            results = await asyncio.gather(
                *(self._suggest(client, region, q) for q in queries),
                return_exceptions=True,
            )

        for q, suggestions in zip(queries, results):
            if isinstance(suggestions, BaseException):
                continue
            for s in suggestions:
                key = s.lower().strip()
                if key and key not in seen and key != q.lower():
                    seen.add(key)
                    out.append(Trend(
                        source=self.name, geo=region.code,
                        query=s, metadata={"seed_query": q},
                    ))

        log.info("[%s] %s: %d suggestions", region.code, self.name, len(out))
        return out

    def _expand(self, seeds: list[str]) -> list[str]:
        if not self.expand:
            return seeds
        # a-z append for breadth (English/Latin scripts only - Arabic seeds skip this)
        out = []
        for seed in seeds:
            out.append(seed)
            if seed.isascii():
                out.extend(f"{seed} {chr(c)}" for c in range(ord("a"), ord("z") + 1))
        return out

    async def _suggest(
        self, client: httpx.AsyncClient, region: Region, q: str
    ) -> list[str]:
        async with self._sem:
            try:
                r = await client.get(
                    ENDPOINT,
                    params={"client": "firefox", "hl": region.hl,
                            "gl": region.gl, "q": q},
                )
                r.raise_for_status()
                data = r.json()
                return data[1] if len(data) > 1 else []
            except Exception as e:
                log.debug("[%s] autocomplete %r failed: %s", region.code, q, e)
                return []
