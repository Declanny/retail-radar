# trend-engine

Multi-region, multi-source US/EU/MENA/APAC trend aggregator. Pulls from Google Trends, Google autocomplete, and Reddit; dedupes per region; sends each region to Claude for parallel e-commerce intelligence analysis.

## Architecture

```
regions.py         single source of truth - one Region dataclass per locale
sources/           each implements the Source protocol (async fetch)
  base.py            Trend dataclass, Source protocol
  google_trends.py   pytrends in a worker thread
  autocomplete.py    httpx.AsyncClient, region-localized seeds
  reddit.py          public JSON API, async
storage.py         SQLite, per-region dedup
analyze.py         AsyncAnthropic, parallel region analysis, prompt-cached persona
orchestrator.py    asyncio.gather across (regions x sources) with bounded concurrency
report.py          markdown rendering (per-region + cross-region index)
cli.py             collect | analyze | run
```

Hot paths are async; the only sync code is pytrends (wrapped with `asyncio.to_thread`) and SQLite (fast enough). Bounded concurrency at three layers: per-region, global collection, and per-region Claude analysis.

## Supported regions

US, GB (UK), FR, DE, AU, CA, AE (UAE), SA (Saudi Arabia), CH (Switzerland). Add more by appending to `REGIONS` in `regions.py`.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env  # add ANTHROPIC_API_KEY
```

## Run

```bash
# Collect + analyze every region (default)
trend-engine run

# Specific regions
trend-engine run --regions US GB FR

# Just one stage
trend-engine collect --regions DE CH
trend-engine analyze --regions DE CH

# Faster, skip a-z autocomplete expansion
trend-engine run --fast
```

Output lands in `output/run-<timestamp>/`:
- `INDEX.md` — links to every region's report
- `<CODE>.md` + `<CODE>.json` — per-region analysis

## Cost / latency notes

- Each region analysis is one Claude call (Opus 4.7, adaptive thinking, effort=high). Persona is prompt-cached, so within a single multi-region run the cache hit rate climbs after region 1.
- Collection: ~30s for all 9 regions (concurrent). Autocomplete dominates wall time; pass `--fast` to skip the a-z expansion.
- Analysis: 9 regions × ~30s sequential ≈ 4.5min, but `--concurrency 4` cuts that to ~2min.
