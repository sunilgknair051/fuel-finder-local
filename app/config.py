"""Local configuration loading with no secret logging."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Load a minimal .env file without adding a runtime dependency."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


@dataclass(frozen=True)
class Settings:
    api_key: str
    exchange_base: str
    exchange_as_of: str
    exchange_rates: dict[str, Decimal]
    postcode_file: Path
    cache_ttl_seconds: float = 300.0
    stale_ttl_seconds: float = 1800.0
    upstream_interval_seconds: float = 65.0
    upstream_timeout_seconds: float = 9.0
    circuit_failure_threshold: int = 3
    circuit_cooldown_seconds: float = 300.0


def load_settings() -> Settings:
    _load_dotenv(ROOT / ".env")
    exchange_path = ROOT / "config" / "exchange_rates.json"
    raw: dict[str, Any] = json.loads(exchange_path.read_text(encoding="utf-8"))
    rates = {
        str(code).upper(): Decimal(str(value))
        for code, value in raw.get("rates", {}).items()
        if Decimal(str(value)) > 0
    }
    rates["EUR"] = Decimal("1.0")
    return Settings(
        api_key=os.getenv("TANKERKOENIG_API_KEY", "").strip(),
        exchange_base="EUR",
        exchange_as_of=str(raw.get("as_of", "unknown")),
        exchange_rates=rates,
        postcode_file=ROOT / "data" / "postcodes_de.json",
        cache_ttl_seconds=float(os.getenv("CACHE_TTL_SECONDS", "300")),
        stale_ttl_seconds=float(os.getenv("STALE_TTL_SECONDS", "1800")),
        upstream_interval_seconds=float(os.getenv("UPSTREAM_INTERVAL_SECONDS", "65")),
        upstream_timeout_seconds=float(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "9")),
        circuit_failure_threshold=int(os.getenv("CIRCUIT_FAILURE_THRESHOLD", "3")),
        circuit_cooldown_seconds=float(os.getenv("CIRCUIT_COOLDOWN_SECONDS", "300")),
    )
