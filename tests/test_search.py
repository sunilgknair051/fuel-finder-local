from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import main
from app.cache import RadiusCache
from app.postcode import Location
from app.rate_limit import UpstreamGate
from tests.conftest import FakeClock, FakeUpstream


def test_valid_e5_search(client: TestClient, fake_upstream: FakeUpstream, payload: Any) -> None:
    response = client.post("/api/search", json=payload())
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "new_request"
    assert body["cheapest"]["name"] == "Beta & Sons <Fuel>"
    assert body["cheapest"]["prices"]["e5"]["eur"] == "1.699"
    assert len(fake_upstream.calls) == 1
    assert fake_upstream.calls[0][2] == 5


def test_e10_and_diesel_reuse_cached_all_fuels(
    client: TestClient,
    fake_upstream: FakeUpstream,
    payload: Any,
) -> None:
    e5 = client.post("/api/search", json=payload(fuel="e5"))
    e10 = client.post("/api/search", json=payload(fuel="e10"))
    diesel = client.post("/api/search", json=payload(fuel="diesel"))
    assert [item.status_code for item in (e5, e10, diesel)] == [200, 200, 200]
    assert e10.json()["source"] == "fresh_cache"
    assert diesel.json()["source"] == "fresh_cache"
    assert len(fake_upstream.calls) == 1


def test_all_fuels_have_separate_prices(client: TestClient, payload: Any) -> None:
    body = client.post("/api/search", json=payload(fuel="all")).json()
    alpha = next(item for item in body["stations"] if item["id"] == "alpha")
    assert set(alpha["prices"]) == {"e5", "e10", "diesel"}
    assert alpha["prices"]["e5"]["eur"] == "1.799"


@pytest.mark.parametrize("postal_code", ["3810", "3810A", "123456", ""])
def test_invalid_postcode_makes_no_upstream_call(
    client: TestClient,
    fake_upstream: FakeUpstream,
    payload: Any,
    postal_code: str,
) -> None:
    response = client.post("/api/search", json=payload(postal_code=postal_code))
    assert response.status_code == 422
    assert fake_upstream.calls == []


def test_unresolved_postcode(client: TestClient, fake_upstream: FakeUpstream, payload: Any) -> None:
    response = client.post("/api/search", json=payload(postal_code="99999"))
    assert response.status_code == 422
    assert response.json()["error"] == "postcode_not_found"
    assert fake_upstream.calls == []


def test_miles_are_converted_both_directions(
    client: TestClient,
    fake_upstream: FakeUpstream,
    payload: Any,
) -> None:
    body = client.post(
        "/api/search",
        json=payload(radius=3, distance_unit="mi", sort="distance"),
    ).json()
    assert fake_upstream.calls[0][2] == pytest.approx(4.828032)
    assert body["stations"][0]["distance"] == pytest.approx(0.621, abs=0.001)


@pytest.mark.parametrize(
    ("radius", "unit"),
    [(25.01, "km"), (15.535, "mi")],
)
def test_radius_never_exceeds_25_km(
    client: TestClient,
    fake_upstream: FakeUpstream,
    payload: Any,
    radius: float,
    unit: str,
) -> None:
    response = client.post(
        "/api/search",
        json=payload(radius=radius, distance_unit=unit),
    )
    assert response.status_code == 422
    assert fake_upstream.calls == []


def test_missing_api_key(
    client: TestClient,
    fake_upstream: FakeUpstream,
    payload: Any,
    settings: Any,
) -> None:
    main.configure_services(settings.__class__(**{**settings.__dict__, "api_key": ""}))
    response = client.post("/api/search", json=payload())
    assert response.status_code == 503
    assert "key" not in response.text.lower() or "api key" in response.text.lower()
    assert "artificial-test-key" not in response.text


def test_sorting_by_price_distance_and_name(client: TestClient, payload: Any) -> None:
    by_price = client.post("/api/search", json=payload(sort="price")).json()["stations"]
    by_distance = client.post("/api/search", json=payload(sort="distance")).json()["stations"]
    by_name = client.post("/api/search", json=payload(sort="name")).json()["stations"]
    assert [item["id"] for item in by_price] == ["beta", "alpha"]
    assert [item["id"] for item in by_distance] == ["beta", "alpha"]
    assert [item["id"] for item in by_name] == ["alpha", "beta"]


def test_closed_visible_by_default_and_open_only_explicit(client: TestClient, payload: Any) -> None:
    all_statuses = client.post("/api/search", json=payload()).json()["stations"]
    open_stations = client.post(
        "/api/search",
        json=payload(open_only=True),
    ).json()["stations"]
    assert any(item["is_open"] is False for item in all_statuses)
    assert [item["id"] for item in open_stations] == ["beta"]


def test_currency_conversion_uses_decimal(client: TestClient, payload: Any) -> None:
    body = client.post("/api/search", json=payload(currency="USD")).json()
    beta = body["cheapest"]
    assert beta["prices"]["e5"] == {
        "eur": "1.699",
        "converted": "3.398",
        "currency": "USD",
    }
    assert body["exchange_rate_as_of"] == "2026-01-01"


def test_missing_exchange_rate(client: TestClient, payload: Any) -> None:
    response = client.post("/api/search", json=payload(currency="CHF"))
    assert response.status_code == 422
    assert response.json()["error"] == "unsupported_currency"


def test_null_false_zero_negative_and_missing_prices_are_empty(
    client: TestClient,
    fake_upstream: FakeUpstream,
    payload: Any,
) -> None:
    fake_upstream.stations = [
        {
            "id": "none",
            "name": "No prices",
            "brand": "",
            "address": "Unknown",
            "distance_km": 1,
            "is_open": True,
            "prices_eur": {"e5": None, "e10": None, "diesel": None},
        }
    ]
    body = client.post("/api/search", json=payload(fuel="all")).json()
    assert body["stations"] == []
    assert body["cheapest"] is None


def test_five_minute_cache(monkeypatch: pytest.MonkeyPatch, settings: Any, stations: Any) -> None:
    clock = FakeClock()
    main.configure_services(settings)
    main.CACHE = RadiusCache(300, 1800, clock)
    main.GATE = UpstreamGate(65, 3, 300, clock)
    fake = FakeUpstream(stations)
    monkeypatch.setattr(main, "UPSTREAM", fake)

    async def run() -> None:
        location = Location(52.2647, 10.5266, "Braunschweig")
        assert (await main._get_stations(location, Decimal("5"), False))[0] == "new_request"
        clock.advance(299)
        assert (await main._get_stations(location, Decimal("5"), False))[0] == "fresh_cache"
        clock.advance(2)
        assert (await main._get_stations(location, Decimal("5"), False))[0] == "new_request"

    asyncio.run(run())
    assert len(fake.calls) == 2


def test_global_65_second_limiter(
    monkeypatch: pytest.MonkeyPatch,
    settings: Any,
    stations: Any,
) -> None:
    clock = FakeClock()
    main.configure_services(settings)
    main.CACHE = RadiusCache(300, 1800, clock)
    main.GATE = UpstreamGate(65, 3, 300, clock)
    fake = FakeUpstream(stations)
    monkeypatch.setattr(main, "UPSTREAM", fake)

    async def run() -> None:
        location = Location(52.2647, 10.5266, "Braunschweig")
        await main._get_stations(location, Decimal("5"), False)
        with pytest.raises(main.ServiceError) as caught:
            await main._get_stations(location, Decimal("10"), False)
        assert caught.value.status_code == 429
        assert caught.value.retry_after_seconds == 65

    asyncio.run(run())
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_concurrent_same_key_coalesces(
    monkeypatch: pytest.MonkeyPatch,
    settings: Any,
    stations: Any,
) -> None:
    main.configure_services(settings)

    class SlowFake(FakeUpstream):
        async def search(self, latitude: float, longitude: float, radius: float) -> Any:
            self.calls.append((latitude, longitude, radius))
            await asyncio.sleep(0.02)
            return self.stations

    fake = SlowFake(stations)
    monkeypatch.setattr(main, "UPSTREAM", fake)
    location = Location(52.2647, 10.5266, "Braunschweig")
    results = await asyncio.gather(
        main._get_stations(location, Decimal("5"), False),
        main._get_stations(location, Decimal("5"), False),
    )
    assert {item[0] for item in results} == {"new_request", "fresh_cache"}
    assert len(fake.calls) == 1


def test_stale_fallback_on_upstream_failure(
    monkeypatch: pytest.MonkeyPatch,
    settings: Any,
    stations: Any,
) -> None:
    clock = FakeClock()
    main.configure_services(settings)
    main.CACHE = RadiusCache(300, 1800, clock)
    main.GATE = UpstreamGate(65, 3, 300, clock)
    fake = FakeUpstream(stations)
    monkeypatch.setattr(main, "UPSTREAM", fake)

    async def run() -> None:
        location = Location(52.2647, 10.5266, "Braunschweig")
        first = await main._get_stations(location, Decimal("5"), False)
        clock.advance(301)
        fake.fail = True
        fallback = await main._get_stations(location, Decimal("5"), False)
        assert first[1].retrieved_at == fallback[1].retrieved_at
        assert fallback[0] == "stale_cache"

    asyncio.run(run())


def test_circuit_breaker_after_repeated_failures(
    monkeypatch: pytest.MonkeyPatch,
    settings: Any,
    stations: Any,
) -> None:
    clock = FakeClock()
    main.configure_services(settings)
    main.CACHE = RadiusCache(300, 1800, clock)
    main.GATE = UpstreamGate(65, 3, 300, clock)
    fake = FakeUpstream(stations)
    fake.fail = True
    monkeypatch.setattr(main, "UPSTREAM", fake)

    async def run() -> None:
        location = Location(52.2647, 10.5266, "Braunschweig")
        for radius in (1, 2, 3):
            with pytest.raises(main.ServiceError) as caught:
                await main._get_stations(location, Decimal(radius), False)
            assert caught.value.status_code == 502
            clock.advance(66)
        with pytest.raises(main.ServiceError) as caught:
            await main._get_stations(location, Decimal("4"), False)
        assert caught.value.status_code == 429
        assert caught.value.retry_after_seconds is not None

    asyncio.run(run())
    assert len(fake.calls) == 3
