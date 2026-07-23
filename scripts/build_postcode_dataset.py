#!/usr/bin/env python3
"""Build the local postcode index from a downloaded GeoNames DE ZIP or text file."""

from __future__ import annotations

import argparse
import io
import json
import math
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import TextIO


def open_source(path: Path) -> TextIO:
    if path.suffix.lower() != ".zip":
        return path.open("r", encoding="utf-8")
    archive = zipfile.ZipFile(path)
    candidates = sorted(
        name
        for name in archive.namelist()
        if name.lower().endswith(".txt") and not name.startswith("__MACOSX")
    )
    preferred = next((name for name in candidates if Path(name).name == "DE.txt"), None)
    if preferred is None and not candidates:
        archive.close()
        raise ValueError("ZIP file contains no text dataset")
    raw = archive.open(preferred or candidates[0])
    stream = io.TextIOWrapper(raw, encoding="utf-8")
    original_close = stream.close

    def close_both() -> None:
        original_close()
        archive.close()

    stream.close = close_both  # type: ignore[method-assign]
    return stream


def build(source: Path, output: Path) -> tuple[int, int]:
    candidates: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    rejected = 0
    with open_source(source) as stream:
        for line in stream:
            columns = line.rstrip("\n").split("\t")
            if len(columns) < 12:
                rejected += 1
                continue
            country, code, place = columns[0], columns[1], columns[2]
            if country != "DE" or len(code) != 5 or not code.isdigit():
                rejected += 1
                continue
            try:
                lat, lng = float(columns[9]), float(columns[10])
            except ValueError:
                rejected += 1
                continue
            if not (
                math.isfinite(lat)
                and math.isfinite(lng)
                and -90 <= lat <= 90
                and -180 <= lng <= 180
            ):
                rejected += 1
                continue
            candidates[code].append((place.strip(), lat, lng))

    postcodes = {}
    for code, rows in sorted(candidates.items()):
        # A stable lexical choice makes duplicate consolidation reproducible.
        place, lat, lng = sorted(
            rows,
            key=lambda item: (item[0].casefold(), item[1], item[2]),
        )[0]
        postcodes[code] = {
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "place": place,
        }

    payload = {
        "_meta": {
            "source": "GeoNames DE postal-code dataset",
            "source_file": source.name,
            "source_url": "https://download.geonames.org/export/zip/",
            "license": "Creative Commons Attribution 4.0",
            "attribution": ("Contains GeoNames geographical data, available under CC BY 4.0."),
            "duplicate_policy": "lexically first place name, then latitude and longitude",
        },
        "postcodes": postcodes,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )
    return len(postcodes), rejected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Downloaded GeoNames DE.zip or DE.txt")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/postcodes_de.json"),
    )
    args = parser.parse_args()
    count, rejected = build(args.source, args.output)
    print(f"Wrote {count} postcodes; rejected {rejected} invalid rows.")


if __name__ == "__main__":
    main()
