"""SQLite storage. Geo-partitioned: dedup happens within (geo, normalized) tuples."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .sources.base import Trend

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "trends.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    geo TEXT NOT NULL,
    source TEXT NOT NULL,
    query TEXT NOT NULL,
    normalized TEXT NOT NULL,
    rank INTEGER,
    volume INTEGER,
    metadata TEXT,
    collected_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trends_geo_norm ON trends(geo, normalized);
CREATE INDEX IF NOT EXISTS idx_trends_collected_at ON trends(collected_at);
"""

_NORMALIZE_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_NORMALIZE_WS = re.compile(r"\s+")


def normalize(s: str) -> str:
    s = s.lower().strip()
    s = _NORMALIZE_PUNCT.sub(" ", s)
    return _NORMALIZE_WS.sub(" ", s)


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_trends(conn: sqlite3.Connection, trends: list[Trend]) -> int:
    if not trends:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        (t.geo, t.source, t.query, normalize(t.query), t.rank, t.volume,
         json.dumps(t.metadata) if t.metadata else None, now)
        for t in trends
    ]
    conn.executemany(
        "INSERT INTO trends (geo, source, query, normalized, rank, volume, metadata, collected_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def recent_trends(conn: sqlite3.Connection, geo: str, hours: int = 24) -> list[dict]:
    """Deduped trends for one region, ranked by source-diversity then frequency."""
    cur = conn.execute(
        """
        SELECT
            normalized,
            MIN(query) AS query,
            GROUP_CONCAT(DISTINCT source) AS sources,
            COUNT(*) AS mentions,
            MIN(rank) AS best_rank,
            MAX(volume) AS peak_volume
        FROM trends
        WHERE geo = ? AND collected_at >= datetime('now', ?)
        GROUP BY normalized
        ORDER BY
            (LENGTH(GROUP_CONCAT(DISTINCT source))
             - LENGTH(REPLACE(GROUP_CONCAT(DISTINCT source), ',', ''))) DESC,
            mentions DESC,
            best_rank ASC NULLS LAST
        """,
        (geo, f"-{hours} hours"),
    )
    return [dict(r) for r in cur.fetchall()]
