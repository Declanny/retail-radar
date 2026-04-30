"""Concurrency coordinator. Runs (regions x sources) as a single task graph."""

from __future__ import annotations

import asyncio
import logging

from .regions import Region
from .sources.base import Source, Trend

log = logging.getLogger(__name__)


async def collect(
    regions: list[Region],
    sources: list[Source],
    *,
    per_region_concurrency: int = 3,
    global_concurrency: int = 6,
) -> list[Trend]:
    """Fetch (region x source) concurrently with bounded parallelism.

    Two semaphores:
    - per-region: how many sources hit one region at once (default = all 3)
    - global: total in-flight fetches (protects against rate limits)
    """
    global_sem = asyncio.Semaphore(global_concurrency)
    region_sems: dict[str, asyncio.Semaphore] = {
        r.code: asyncio.Semaphore(per_region_concurrency) for r in regions
    }

    async def _one(region: Region, source: Source) -> list[Trend]:
        async with global_sem, region_sems[region.code]:
            try:
                return await source.fetch(region)
            except Exception as e:
                log.exception("[%s] %s crashed: %s", region.code, source.name, e)
                return []

    tasks = [_one(r, s) for r in regions for s in sources]
    results = await asyncio.gather(*tasks)

    flat: list[Trend] = []
    for batch in results:
        flat.extend(batch)
    log.info(
        "collected %d trends across %d regions x %d sources",
        len(flat), len(regions), len(sources),
    )
    return flat
