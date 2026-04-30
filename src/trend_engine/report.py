"""Render TrendAnalysis to markdown. One report per region; an index links them."""

from __future__ import annotations

from datetime import datetime, timezone

from .analyze import TrendAnalysis


def render_region(analysis: TrendAnalysis, *, sources_summary: str = "") -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = [
        f"# {analysis.region_name} ({analysis.region_code}) — Trend Report",
        f"_{now}_",
        "",
    ]
    if sources_summary:
        out.extend([f"_{sources_summary}_", ""])

    out.extend(["## Executive summary", "", analysis.summary, ""])
    out.extend(["## Consumer intent", "", analysis.consumer_intent, ""])

    out.append("## Top trending products")
    out.append("")
    for p in analysis.top_trending_products:
        out.append(f"- {p}")
    out.append("")

    out.append("## Categories")
    out.append("")
    for cat in analysis.categories:
        out.append(f"### {cat.name}")
        for t in cat.trends:
            out.append(f"- {t}")
        out.append("")

    out.append("## Emerging opportunities")
    out.append("")
    for o in analysis.emerging_opportunities:
        out.append(f"- {o}")
    out.append("")

    out.append("## Product recommendations")
    out.append("")
    out.append("| # | Product | Positioning | Confidence | Audience | Why |")
    out.append("|---|---|---|---|---|---|")
    for i, r in enumerate(analysis.recommendations, 1):
        name = r.product_name.replace("|", "\\|")
        why = r.why_trending.replace("|", "\\|").replace("\n", " ")
        aud = r.target_audience.replace("|", "\\|")
        out.append(f"| {i} | {name} | {r.positioning} | {r.confidence} | {aud} | {why} |")
    out.append("")
    return "\n".join(out)


def render_index(analyses: dict[str, TrendAnalysis], file_map: dict[str, str]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = [f"# Multi-Region Trend Report — {now}", ""]
    out.append("## Regions analyzed")
    out.append("")
    for code, a in analyses.items():
        out.append(f"- [{a.region_name} ({code})]({file_map[code]}) — {a.summary}")
    return "\n".join(out) + "\n"
