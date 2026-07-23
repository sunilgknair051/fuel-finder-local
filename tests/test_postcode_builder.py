from __future__ import annotations

import json
from pathlib import Path

from scripts.build_postcode_dataset import build


def test_postcode_builder_validates_and_consolidates(tmp_path: Path) -> None:
    source = tmp_path / "DE.txt"
    source.write_text(
        "DE\t38102\tZulu\tNI\t03\tX\t0\tX\t0\t52.2\t10.5\t6\n"
        "DE\t38102\tAlpha\tNI\t03\tX\t0\tX\t0\t52.3\t10.6\t6\n"
        "DE\tbad\tBad\tNI\t03\tX\t0\tX\t0\t999\t10\t6\n",
        encoding="utf-8",
    )
    output = tmp_path / "postcodes.json"
    count, rejected = build(source, output)
    result = json.loads(output.read_text(encoding="utf-8"))
    assert count == 1
    assert rejected == 1
    assert result["postcodes"]["38102"]["place"] == "Alpha"
    assert result["_meta"]["license"] == "Creative Commons Attribution 4.0"
