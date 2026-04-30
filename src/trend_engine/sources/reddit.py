"""Reddit source via public JSON API. No auth required; fully async."""

from __future__ import annotations

import asyncio
import logging

import httpx

from ..regions import Region
from .base import Source, Trend

log = logging.getLogger(__name__)


class RedditSource:
    name = "reddit"

    def __init__(self, limit: int = 25, concurrency: int = 4) -> None:
        self.limit = limit
        self._sem = asyncio.Semaphore(concurrency)

    async def fetch(self, region: Region) -> list[Trend]:
        if not region.reddit_subs:
            return []

        async with httpx.AsyncClient(
            headers={"User-Agent": f"trend-engine/0.1 region={region.code}"},
            timeout=10.0,
        ) as client:
            results = await asyncio.gather(
                *(self._fetch_sub(client, region, sub) for sub in region.reddit_subs),
                return_exceptions=True,
            )

        out: list[Trend] = []
        for r in results:
            if isinstance(r, list):
                out.extend(r)
        log.info("[%s] %s: %d posts from %d subs",
                 region.code, self.name, len(out), len(region.reddit_subs))
        return out

    async def _fetch_sub(
        self, client: httpx.AsyncClient, region: Region, sub: str
    ) -> list[Trend]:
        async with self._sem:
            try:
                r = await client.get(
                    f"https://www.reddit.com/r/{sub}/hot.json",
                    params={"limit": self.limit},
                )
                r.raise_for_status()
                posts = r.json().get("data", {}).get("children", [])
            except Exception as e:
                log.debug("[%s] r/%s failed: %s", region.code, sub, e)
                return []

        out: list[Trend] = []
        for rank, p in enumerate(posts, start=1):
            d = p.get("data", {})
            title = d.get("title")
            if not title:
                continue
            out.append(Trend(
                source=self.name, geo=region.code,
                query=title, rank=rank, volume=d.get("score"),
                metadata={"sub": sub, "url": "https://reddit.com" + d.get("permalink", "")},
            ))
        return out
