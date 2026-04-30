"""trend-engine CLI: collect, analyze, run. Multi-region, async-first."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from . import analyze as analyze_mod
from . import orchestrator
from . import regions as regions_mod
from . import report as report_mod
from . import storage
from .sources.autocomplete import AutocompleteSource
from .sources.base import Source
from .sources.google_trends import GoogleTrendsSource
from .sources.reddit import RedditSource

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _build_sources(args: argparse.Namespace) -> list[Source]:
    catalog: dict[str, Source] = {
        "google": GoogleTrendsSource(),
        "autocomplete": AutocompleteSource(expand=not args.fast),
        "reddit": RedditSource(limit=args.reddit_limit),
    }
    return [catalog[name] for name in args.sources]


async def cmd_collect(args: argparse.Namespace) -> int:
    log = logging.getLogger("collect")
    regions = regions_mod.resolve(args.regions)
    sources = _build_sources(args)

    log.info("collecting: %s x %s",
             [r.code for r in regions], [s.name for s in sources])
    trends = await orchestrator.collect(regions, sources)
    if not trends:
        log.error("nothing collected")
        return 1

    conn = storage.connect()
    storage.save_trends(conn, trends)
    log.info("saved %d trend rows", len(trends))
    return 0


async def cmd_analyze(args: argparse.Namespace) -> int:
    log = logging.getLogger("analyze")
    regions = regions_mod.resolve(args.regions)
    conn = storage.connect()

    region_trends: dict = {}
    for region in regions:
        rows = storage.recent_trends(conn, geo=region.code, hours=args.hours)
        if rows:
            region_trends[region] = rows[: args.limit]
        else:
            log.warning("[%s] no trends in last %dh - skipping", region.code, args.hours)

    if not region_trends:
        log.error("no trends to analyze - run `collect` first")
        return 1

    log.info("analyzing %d regions concurrently (max %d in-flight)",
             len(region_trends), args.concurrency)

    analyses = await analyze_mod.analyze_all(
        region_trends, concurrency=args.concurrency
    )
    if not analyses:
        log.error("all analyses failed")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = OUTPUT_DIR / f"run-{stamp}"
    run_dir.mkdir()

    file_map: dict[str, str] = {}
    for code, analysis in analyses.items():
        json_path = run_dir / f"{code}.json"
        md_path = run_dir / f"{code}.md"
        sources_summary = (
            f"{len(region_trends[regions_mod.REGIONS[code]])} deduped trends · "
            f"sources: " + ", ".join(sorted({
                s for d in region_trends[regions_mod.REGIONS[code]]
                for s in d['sources'].split(',')
            }))
        )
        json_path.write_text(analyze_mod.to_json(analysis))
        md_path.write_text(report_mod.render_region(analysis, sources_summary=sources_summary))
        file_map[code] = md_path.name
        log.info("[%s] wrote %s", code, md_path)

    index_path = run_dir / "INDEX.md"
    index_path.write_text(report_mod.render_index(analyses, file_map))
    log.info("index: %s", index_path)
    print(index_path)
    return 0


async def cmd_run(args: argparse.Namespace) -> int:
    rc = await cmd_collect(args)
    if rc != 0:
        return rc
    return await cmd_analyze(args)


def _add_regions_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--regions", nargs="+", default=None,
                   help=f"region codes (default: all). Available: {','.join(regions_mod.ALL_CODES)}")


def _add_collect_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--sources", nargs="+",
                   default=["google", "autocomplete", "reddit"],
                   choices=["google", "autocomplete", "reddit"])
    p.add_argument("--fast", action="store_true",
                   help="skip a-z autocomplete expansion")
    p.add_argument("--reddit-limit", type=int, default=25)


def _add_analyze_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--hours", type=int, default=24)
    p.add_argument("--limit", type=int, default=300,
                   help="cap trends sent to Claude per region")
    p.add_argument("--concurrency", type=int, default=4,
                   help="max regions analyzed in parallel")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="trend-engine")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_collect = sub.add_parser("collect", help="pull from sources, save to db")
    _add_regions_arg(p_collect)
    _add_collect_args(p_collect)

    p_analyze = sub.add_parser("analyze", help="analyze recent trends per region")
    _add_regions_arg(p_analyze)
    _add_analyze_args(p_analyze)

    p_run = sub.add_parser("run", help="collect then analyze")
    _add_regions_arg(p_run)
    _add_collect_args(p_run)
    _add_analyze_args(p_run)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    coro = {"collect": cmd_collect, "analyze": cmd_analyze, "run": cmd_run}[args.cmd]
    return asyncio.run(coro(args))


if __name__ == "__main__":
    sys.exit(main())
