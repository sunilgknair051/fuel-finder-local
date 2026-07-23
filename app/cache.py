"""Concurrency-safe in-memory cache; nothing is written to disk."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable


@dataclass
class CacheEntry:
    stations: list[dict[str, Any]]
    created_monotonic: float
    retrieved_at: str


class RadiusCache:
    def __init__(
        self,
        fresh_seconds: float = 300.0,
        stale_seconds: float = 1800.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.fresh_seconds = fresh_seconds
        self.stale_seconds = stale_seconds
        self.clock = clock
        self.entries: dict[tuple[float, float, float], CacheEntry] = {}
        self.flight_lock = asyncio.Lock()

    def lookup(self, key: tuple[float, float, float]) -> tuple[str, CacheEntry] | None:
        entry = self.entries.get(key)
        if entry is None:
            return None
        age = self.clock() - entry.created_monotonic
        if age <= self.fresh_seconds:
            return "fresh_cache", entry
        if age <= self.stale_seconds:
            return "stale_cache", entry
        self.entries.pop(key, None)
        return None

    def store(self, key: tuple[float, float, float], stations: list[dict[str, Any]]) -> CacheEntry:
        entry = CacheEntry(
            stations=stations,
            created_monotonic=self.clock(),
            retrieved_at=datetime.now(UTC).isoformat(),
        )
        self.entries[key] = entry
        return entry
