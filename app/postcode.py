"""Local-only German postcode resolution."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Location:
    latitude: float
    longitude: float
    place_name: str


class PostcodeIndex:
    def __init__(self, path: Path) -> None:
        self._locations: dict[str, Location] = {}
        self.source: dict[str, str] = {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.source = dict(raw.get("_meta", {}))
            entries = raw.get("postcodes", raw)
            for code, item in entries.items():
                if not (isinstance(code, str) and len(code) == 5 and code.isdigit()):
                    continue
                lat = float(item["lat"])
                lng = float(item["lng"])
                if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                    continue
                if not (math.isfinite(lat) and math.isfinite(lng)):
                    continue
                self._locations[code] = Location(lat, lng, str(item.get("place", "")))
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            self._locations = {}

    @property
    def loaded(self) -> bool:
        return bool(self._locations)

    def resolve(self, postal_code: str) -> Location | None:
        return self._locations.get(postal_code)
