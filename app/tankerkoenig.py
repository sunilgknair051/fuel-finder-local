"""Tankerkönig client with strict response validation."""

from __future__ import annotations

import logging
import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

LOGGER = logging.getLogger("fuelfinder")
ENDPOINT = "https://creativecommons.tankerkoenig.de/json/list.php"
KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{7,127}$")


class UpstreamError(Exception):
    pass


def valid_api_key(value: str) -> bool:
    return bool(KEY_PATTERN.fullmatch(value))


def _price(value: Any) -> str | None:
    if value is None or value is False or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number <= 0:
        return None
    return str(number)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def normalize_station(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    try:
        distance = float(raw.get("dist"))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(distance) or distance < 0:
        return None
    street = _text(raw.get("street")).strip()
    house = _text(raw.get("houseNumber")).strip()
    postcode = _text(raw.get("postCode")).strip()
    place = _text(raw.get("place")).strip()
    street_line = " ".join(part for part in (street, house) if part)
    city_line = " ".join(part for part in (postcode, place) if part)
    address = ", ".join(part for part in (street_line, city_line) if part)
    return {
        "id": _text(raw.get("id")),
        "name": _text(raw.get("name")).strip() or "Unnamed station",
        "brand": _text(raw.get("brand")).strip(),
        "address": address or "Address unavailable",
        "distance_km": distance,
        "is_open": raw.get("isOpen") if isinstance(raw.get("isOpen"), bool) else None,
        "prices_eur": {fuel: _price(raw.get(fuel)) for fuel in ("e5", "e10", "diesel")},
    }


class TankerkoenigClient:
    def __init__(self, api_key: str, timeout_seconds: float = 9.0) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def search(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
    ) -> list[dict[str, Any]]:
        params = {
            "lat": latitude,
            "lng": longitude,
            "rad": radius_km,
            "sort": "dist",
            "type": "all",
            "apikey": self.api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(ENDPOINT, params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            LOGGER.warning("upstream request failed")
            raise UpstreamError("Fuel-price service is temporarily unavailable") from None
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            LOGGER.warning("upstream request failed")
            raise UpstreamError("Fuel-price service returned an error")
        stations = payload.get("stations")
        if not isinstance(stations, list):
            LOGGER.warning("upstream request failed")
            raise UpstreamError("Fuel-price service returned invalid data")
        normalized = [
            station for item in stations if (station := normalize_station(item)) is not None
        ]
        LOGGER.info("upstream request succeeded")
        return normalized
