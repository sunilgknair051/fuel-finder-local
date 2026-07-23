"""Single-process FuelFinder Local FastAPI application."""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.cache import CacheEntry, RadiusCache
from app.config import ROOT, Settings, load_settings
from app.currency import convert_price
from app.models import SearchRequest
from app.postcode import Location, PostcodeIndex
from app.rate_limit import UpstreamGate
from app.tankerkoenig import TankerkoenigClient, UpstreamError, valid_api_key

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
LOGGER = logging.getLogger("fuelfinder")
MILES_TO_KM = Decimal("1.609344")
FUEL_LABELS = {
    "e5": "Super E5 / Super 95",
    "e10": "Super E10",
    "diesel": "Diesel",
}
RADIUS_OPTIONS = [1, 2, 3, 5, 10, 15, 20, 25]


class ServiceError(Exception):
    def __init__(
        self,
        status_code: int,
        error: str,
        message: str,
        retry_after_seconds: int | None = None,
    ) -> None:
        self.status_code = status_code
        self.error = error
        self.message = message
        self.retry_after_seconds = retry_after_seconds


SETTINGS: Settings
POSTCODES: PostcodeIndex
CACHE: RadiusCache
GATE: UpstreamGate
UPSTREAM: TankerkoenigClient


def configure_services(settings: Settings | None = None) -> None:
    global SETTINGS, POSTCODES, CACHE, GATE, UPSTREAM
    SETTINGS = settings or load_settings()
    POSTCODES = PostcodeIndex(SETTINGS.postcode_file)
    CACHE = RadiusCache(SETTINGS.cache_ttl_seconds, SETTINGS.stale_ttl_seconds)
    GATE = UpstreamGate(
        SETTINGS.upstream_interval_seconds,
        SETTINGS.circuit_failure_threshold,
        SETTINGS.circuit_cooldown_seconds,
    )
    UPSTREAM = TankerkoenigClient(SETTINGS.api_key, SETTINGS.upstream_timeout_seconds)


configure_services()
app = FastAPI(
    title="FuelFinder Local",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.mount("/static", StaticFiles(directory=ROOT / "app" / "static"), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next: Any) -> Any:
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Permissions-Policy"] = (
        "geolocation=(), camera=(), microphone=(), payment=(), usb=()"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(ServiceError)
async def service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
    payload: dict[str, Any] = {"error": exc.error, "message": exc.message}
    if exc.retry_after_seconds is not None:
        payload["retry_after_seconds"] = exc.retry_after_seconds
    return JSONResponse(payload, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, __: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        {"error": "invalid_request", "message": "Check all search fields and try again."},
        status_code=422,
    )


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(Path(ROOT / "app" / "templates" / "index.html"))


@app.get("/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/meta")
async def meta() -> dict[str, Any]:
    return {
        "fuels": [{"value": key, "label": label} for key, label in FUEL_LABELS.items()]
        + [{"value": "all", "label": "All fuels"}],
        "radii": RADIUS_OPTIONS,
        "distance_units": [
            {"value": "km", "label": "Kilometres"},
            {"value": "mi", "label": "Miles"},
        ],
        "currencies": [
            {"code": code, "rate": str(rate)}
            for code, rate in sorted(SETTINGS.exchange_rates.items())
        ],
        "exchange_rate_as_of": SETTINGS.exchange_as_of,
        "maximum_radius_km": 25,
        "privacy_summary": (
            "No accounts, cookies, tracking, browser storage, or search history. "
            "Postcodes are resolved locally."
        ),
    }


def _radius_km(request: SearchRequest) -> Decimal:
    radius = request.radius * (MILES_TO_KM if request.distance_unit == "mi" else Decimal("1"))
    if radius > Decimal("25"):
        raise ServiceError(422, "invalid_radius", "Radius cannot exceed 25 kilometres.")
    return radius


async def _get_stations(
    location: Location,
    radius_km: Decimal,
    refresh: bool,
) -> tuple[str, CacheEntry]:
    key = (
        round(location.latitude, 6),
        round(location.longitude, 6),
        round(float(radius_km), 6),
    )
    initial = CACHE.lookup(key)
    initial_created = initial[1].created_monotonic if initial else None
    if initial and initial[0] == "fresh_cache" and not refresh:
        LOGGER.info("cache hit")
        return initial

    async with CACHE.flight_lock:
        current = CACHE.lookup(key)
        if current and current[0] == "fresh_cache":
            replaced = current[1].created_monotonic != initial_created
            if not refresh or replaced:
                LOGGER.info("cache hit")
                return current

        if not valid_api_key(SETTINGS.api_key):
            if current:
                LOGGER.info("cache hit")
                return current
            raise ServiceError(
                503,
                "api_key_unavailable",
                "The local operator must configure a valid Tankerkönig API key.",
            )

        wait = GATE.wait_seconds()
        if wait:
            LOGGER.warning("rate limit activated")
            if current:
                LOGGER.info("cache hit")
                return current
            raise ServiceError(
                429,
                "upstream_limited",
                "A new fuel-price request is not available yet. Please try again later.",
                wait,
            )

        GATE.mark_attempt()
        try:
            stations = await UPSTREAM.search(
                location.latitude,
                location.longitude,
                float(radius_km),
            )
        except UpstreamError as exc:
            GATE.mark_failure()
            if current:
                LOGGER.info("cache hit")
                return "stale_cache", current[1]
            raise ServiceError(502, "upstream_error", str(exc)) from None
        GATE.mark_success()
        return "new_request", CACHE.store(key, stations)


def _station_view(
    station: dict[str, Any],
    currency: str,
    rate: Decimal,
    unit: str,
) -> dict[str, Any]:
    prices: dict[str, Any] = {}
    for fuel, raw in station["prices_eur"].items():
        if raw is None:
            prices[fuel] = None
            continue
        eur = Decimal(raw)
        prices[fuel] = {
            "eur": f"{eur:.3f}",
            "converted": f"{convert_price(eur, rate):.3f}",
            "currency": currency,
        }
    distance_km = float(station["distance_km"])
    display_distance = distance_km / float(MILES_TO_KM) if unit == "mi" else distance_km
    return {
        "id": station["id"],
        "name": station["name"],
        "brand": station["brand"],
        "address": station["address"],
        "distance": round(display_distance, 3),
        "distance_km": round(distance_km, 3),
        "distance_unit": unit,
        "is_open": station["is_open"],
        "prices": prices,
    }


def _selected_value(station: dict[str, Any], fuel: str) -> Decimal | None:
    values = []
    fuels = FUEL_LABELS if fuel == "all" else (fuel,)
    for key in fuels:
        item = station["prices"].get(key)
        if item is not None:
            values.append(Decimal(item["eur"]))
    return min(values) if values else None


@app.post("/api/search")
async def search(payload: SearchRequest) -> dict[str, Any]:
    location = POSTCODES.resolve(payload.postal_code)
    if location is None:
        raise ServiceError(
            422,
            "postcode_not_found",
            "This German postal code is not available in the local dataset.",
        )
    radius_km = _radius_km(payload)
    rate = SETTINGS.exchange_rates.get(payload.currency)
    if rate is None:
        raise ServiceError(422, "unsupported_currency", "The selected currency is not configured.")

    source, entry = await _get_stations(location, radius_km, payload.refresh)
    stations = [
        _station_view(item, payload.currency, rate, payload.distance_unit)
        for item in entry.stations
    ]
    available_stations = stations.copy()
    stations = [
        item
        for item in stations
        if _selected_value(item, payload.fuel) is not None
        and (not payload.open_only or item["is_open"] is True)
    ]

    if payload.sort == "price":
        stations.sort(key=lambda item: (_selected_value(item, payload.fuel), item["distance"]))
    elif payload.sort == "distance":
        stations.sort(key=lambda item: (item["distance"], item["name"].casefold()))
    else:
        stations.sort(key=lambda item: (item["name"].casefold(), item["distance"]))

    cheapest = (
        min(stations, key=lambda item: (_selected_value(item, payload.fuel), item["distance"]))
        if stations
        else None
    )
    return {
        "stations": stations,
        "available_stations": available_stations,
        "cheapest": cheapest,
        "result_count": len(stations),
        "selection": {
            "fuel": payload.fuel,
            "fuel_label": "All fuels" if payload.fuel == "all" else FUEL_LABELS[payload.fuel],
            "currency": payload.currency,
            "distance_unit": payload.distance_unit,
            "open_only": payload.open_only,
            "sort": payload.sort,
            "radius_km": float(radius_km),
        },
        "retrieved_at": entry.retrieved_at,
        "source": source,
        "exchange_rate_as_of": SETTINGS.exchange_as_of,
        "conversion_notice": (
            "EUR prices are converted using the locally configured indicative rate."
            if payload.currency != "EUR"
            else None
        ),
    }


def _startup_banner() -> None:
    print("FuelFinder Local started")
    print("Local address: http://127.0.0.1:8000")
    print(f"Postcode dataset loaded: {'yes' if POSTCODES.loaded else 'no'}")
    print(f"Tankerkönig API key configured: {'yes' if valid_api_key(SETTINGS.api_key) else 'no'}")


if __name__ == "__main__":
    _startup_banner()
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        access_log=False,
        log_level="critical",
    )
