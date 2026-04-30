"""Source interface. Every source is async and region-aware."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..regions import Region


@dataclass(slots=True)
class Trend:
    source: str
    geo: str
    query: str
    rank: int | None = None
    volume: int | None = None
    metadata: dict = field(default_factory=dict)


@runtime_checkable
class Source(Protocol):
    """A region-aware async source. Implementations must never raise -
    they log and return [] so a single broken source can't fail an entire run."""

    name: str

    async def fetch(self, region: Region) -> list[Trend]: ...
