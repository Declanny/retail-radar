"""Google Trends source. pytrends is sync, so we run it in a worker thread."""

from __future__ import annotations

import asyncio
import logging

from ..regions import Region
from .base import Source, Trend

log = logging.getLogger(__name__)


class GoogleTrendsSource:
    name = "google_trends"

    async def fetch(self, region: Region) -> list[Trend]:
        return await asyncio.to_thread(self._fetch_sync, region)

    def _fetch_sync(self, region: Region) -> list[Trend]:
        try:
            from pytrends.request import TrendReq
        except ImportError:
            log.error("pytrends not installed")
            return []

        out: list[Trend] = []
        try:
            client = TrendReq(hl=region.hl, tz=0)
        except Exception as e:
            log.warning("[%s] pytrends init failed: %s", region.code, e)
            return out

        # Daily trending searches
        try:
            df = client.trending_searches(pn=region.pytrends_pn)
            for rank, query in enumerate(df[0].tolist(), start=1):
                out.append(Trend(
                    source=self.name, geo=region.code,
                    query=query, rank=rank,
                ))
        except Exception as e:
            log.debug("[%s] daily trends unavailable: %s", region.code, e)

        # Realtime trends (broader; not all regions supported)
        try:
            df = client.realtime_trending_searches(pn=region.gl)
            for rank, row in enumerate(df.itertuples(index=False), start=1):
                title = getattr(row, "title", None)
                if isinstance(title, list):
                    title = title[0] if title else None
                if not title:
                    continue
                out.append(Trend(
                    source=self.name + "_rt", geo=region.code,
                    query=str(title), rank=rank,
                    metadata={"category": getattr(row, "category", None)},
                ))
        except Exception as e:
            log.debug("[%s] realtime trends unavailable: %s", region.code, e)

        log.info("[%s] %s: %d trends", region.code, self.name, len(out))
        return out
