from __future__ import annotations

from collections.abc import Callable, Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import ROOT, Settings
from app.tankerkoenig import UpstreamError


class FakeClock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class FakeUpstream:
    def __init__(self, stations: list[dict[str, Any]]) -> None:
        self.stations = stations
        self.calls: list[tuple[float, float, float]] = []
        self.fail = False

    async def search(
        self,
        latitude: float,
        longitude: float,
        radius: float,
    ) -> list[dict[str, Any]]:
        self.calls.append((latitude, longitude, radius))
        if self.fail:
            raise UpstreamError("Fuel-price service is temporarily unavailable")
        return self.stations


@pytest.fixture
def stations() -> list[dict[str, Any]]:
    return [
        {
            "id": "alpha",
            "name": "Alpha Fuel",
            "brand": "ALPHA",
            "address": "A-Straße 1, 38102 Braunschweig",
            "distance_km": 2.0,
            "is_open": False,
            "prices_eur": {"e5": "1.799", "e10": "1.749", "diesel": "1.659"},
        },
        {
            "id": "beta",
            "name": "Beta & Sons <Fuel>",
            "brand": "BETA",
            "address": "<Main> 2, 38102 Braunschweig",
            "distance_km": 1.0,
            "is_open": True,
            "prices_eur": {"e5": "1.699", "e10": "1.689", "diesel": None},
        },
        {
            "id": "gamma",
            "name": "Gamma",
            "brand": "",
            "address": "G-Weg 3, 38102 Braunschweig",
            "distance_km": 0.5,
            "is_open": None,
            "prices_eur": {"e5": None, "e10": None, "diesel": "1.709"},
        },
    ]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        api_key="artificial-test-key",
        exchange_base="EUR",
        exchange_as_of="2026-01-01",
        exchange_rates={"EUR": Decimal("1"), "USD": Decimal("2")},
        postcode_file=Path(ROOT / "data" / "postcodes_de.json"),
        cache_ttl_seconds=300,
        stale_ttl_seconds=1800,
        upstream_interval_seconds=65,
        upstream_timeout_seconds=1,
        circuit_failure_threshold=3,
        circuit_cooldown_seconds=300,
    )


@pytest.fixture
def fake_upstream(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    stations: list[dict[str, Any]],
) -> FakeUpstream:
    main.configure_services(settings)
    fake = FakeUpstream(stations)
    monkeypatch.setattr(main, "UPSTREAM", fake)
    return fake


@pytest.fixture
def client(fake_upstream: FakeUpstream) -> Iterator[TestClient]:
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def payload() -> Callable[..., dict[str, Any]]:
    def make(**overrides: Any) -> dict[str, Any]:
        value: dict[str, Any] = {
            "postal_code": "38102",
            "radius": 5,
            "distance_unit": "km",
            "fuel": "e5",
            "currency": "EUR",
            "open_only": False,
            "sort": "price",
        }
        value.update(overrides)
        return value

    return make
