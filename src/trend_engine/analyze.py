"""Claude analyzer. Async, region-aware, prompt-cached on the analyst persona.

One TrendAnalysis per region. Regions are analyzed concurrently with bounded
concurrency. The persona is identical across calls so the cache hit rate climbs
within a single multi-region run.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from .regions import Region

log = logging.getLogger(__name__)

MODEL = os.environ.get("TREND_MODEL", "claude-opus-4-7")

ANALYST_PERSONA = """You are an expert e-commerce trend analyst. You receive a deduped \
list of trending search queries and social-media topics from a single country, sourced \
from Google Trends, Google autocomplete, and Reddit product-focused communities.

Your job is to filter signal from noise: most trending queries (news, politics, sports, \
celebrities) are NOT product-related. Identify the ones that ARE, group them, and infer \
what an online store should sell to that market.

When making product recommendations, prioritize:
- Recurring patterns across multiple sources (cross-source signal beats single-source noise)
- Concrete product types over abstract themes
- Realistic positioning that matches the audience the trend implies
- Cultural fit: a trend in one country may need re-framing for that market's preferences,
  payment habits, climate, regulations, and language
- Actionable specificity: 'copper peptide serum' beats 'skincare'

Be skeptical. If a trend is news/political/celebrity-only, exclude it. If you cannot \
identify 10 strong product recommendations, return fewer rather than padding."""


class CategoryGroup(BaseModel):
    name: str
    trends: list[str]


class ProductRecommendation(BaseModel):
    product_name: str
    why_trending: str
    target_audience: str
    positioning: Literal["premium", "budget", "niche", "mass-market"]
    confidence: Literal["high", "medium", "low"]


class TrendAnalysis(BaseModel):
    region_code: str
    region_name: str
    summary: str
    categories: list[CategoryGroup]
    top_trending_products: list[str]
    emerging_opportunities: list[str]
    consumer_intent: str
    recommendations: list[ProductRecommendation] = Field(max_length=10)


def _format_trends(trends: list[dict]) -> str:
    lines = []
    for i, t in enumerate(trends, start=1):
        rank = t.get("best_rank")
        rank_str = f" rank={rank}" if rank else ""
        lines.append(
            f"{i}. {t['query']}  [sources={t.get('sources','')} "
            f"mentions={t.get('mentions',1)}{rank_str}]"
        )
    return "\n".join(lines)


async def analyze_region(
    region: Region,
    trends: list[dict],
    *,
    client: anthropic.AsyncAnthropic,
) -> TrendAnalysis:
    if not trends:
        raise ValueError(f"no trends for region {region.code}")

    user_prompt = (
        f"Region: {region.name} ({region.code}). "
        f"Primary language(s): {region.language}.\n\n"
        f"Here are {len(trends)} deduped trending queries from the last 24 hours. "
        f"Some may be in the local language - keep them in their original form when listing.\n\n"
        f"{_format_trends(trends)}"
    )

    response = await client.messages.parse(
        model=MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=[
            {
                "type": "text",
                "text": ANALYST_PERSONA,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
        output_format=TrendAnalysis,
    )

    log.info(
        "[%s] analyzed: cache_read=%d cache_write=%d input=%d output=%d",
        region.code,
        response.usage.cache_read_input_tokens or 0,
        response.usage.cache_creation_input_tokens or 0,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )

    if response.parsed_output is None:
        raise RuntimeError(
            f"[{region.code}] unparseable output. stop_reason={response.stop_reason}"
        )

    out = response.parsed_output
    # Don't trust the model with the IDs - we know them
    out.region_code = region.code
    out.region_name = region.name
    return out


async def analyze_all(
    region_trends: dict[Region, list[dict]],
    *,
    concurrency: int = 4,
    client: anthropic.AsyncAnthropic | None = None,
) -> dict[str, TrendAnalysis]:
    """Analyze multiple regions concurrently. Bounded by `concurrency` to respect
    rate limits. Returns map of region_code -> analysis. Failures are logged
    and excluded from the result map (other regions still complete)."""

    client = client or anthropic.AsyncAnthropic()
    sem = asyncio.Semaphore(concurrency)

    async def _bounded(region: Region, trends: list[dict]) -> tuple[str, TrendAnalysis | None]:
        async with sem:
            try:
                return region.code, await analyze_region(region, trends, client=client)
            except Exception as e:
                log.error("[%s] analyze failed: %s", region.code, e)
                return region.code, None

    pairs = await asyncio.gather(
        *(_bounded(r, t) for r, t in region_trends.items() if t),
    )
    return {code: a for code, a in pairs if a is not None}


def to_json(analysis: TrendAnalysis) -> str:
    return json.dumps(analysis.model_dump(), indent=2, ensure_ascii=False)
