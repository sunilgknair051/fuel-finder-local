from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import ROOT
from app.tankerkoenig import TankerkoenigClient, UpstreamError, normalize_station
from tests.conftest import FakeUpstream


class DummyResponse:
    def __init__(self, payload: Any = None, malformed: bool = False) -> None:
        self.payload = payload
        self.malformed = malformed

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        if self.malformed:
            raise ValueError("bad json")
        return self.payload


class DummyClient:
    response: DummyResponse
    calls: list[dict[str, Any]] = []

    def __init__(self, **_: Any) -> None:
        pass

    async def __aenter__(self) -> DummyClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def get(self, _: str, params: dict[str, Any]) -> DummyResponse:
        self.calls.append(params)
        return self.response


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        DummyResponse({"ok": False, "message": "no"}),
        DummyResponse({"ok": True, "stations": {}}),
        DummyResponse(malformed=True),
    ],
)
async def test_invalid_upstream_responses(
    monkeypatch: pytest.MonkeyPatch,
    response: DummyResponse,
) -> None:
    DummyClient.response = response
    DummyClient.calls = []
    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)
    with pytest.raises(UpstreamError):
        await TankerkoenigClient("artificial-test-key").search(52, 10, 5)
    assert len(DummyClient.calls) == 1


@pytest.mark.asyncio
async def test_upstream_request_has_exact_safe_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    DummyClient.response = DummyResponse({"ok": True, "stations": []})
    DummyClient.calls = []
    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)
    await TankerkoenigClient("artificial-test-key").search(52, 10, 5)
    assert DummyClient.calls == [
        {
            "lat": 52,
            "lng": 10,
            "rad": 5,
            "sort": "dist",
            "type": "all",
            "apikey": "artificial-test-key",
        }
    ]
    assert "38102" not in json.dumps(DummyClient.calls)


@pytest.mark.parametrize("value", [False, None, 0, -1, "bad"])
def test_invalid_price_normalization(value: Any) -> None:
    station = normalize_station({"dist": 1, "e5": value})
    assert station is not None
    assert station["prices_eur"]["e5"] is None


def test_security_headers_no_cookie_and_health(client: TestClient) -> None:
    response = client.get("/api/meta")
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "geolocation=()" in response.headers["permissions-policy"]
    assert response.headers["cache-control"] == "no-store"
    assert "set-cookie" not in response.headers
    assert client.get("/healthz").json() == {"status": "ok"}


def test_api_key_and_search_values_absent_from_responses_and_logs(
    client: TestClient,
    fake_upstream: FakeUpstream,
    payload: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client.post("/api/search", json=payload())
    client.post("/api/search", json=payload())
    combined = caplog.text
    assert "artificial-test-key" not in combined
    assert "38102" not in combined
    assert "creativecommons.tankerkoenig.de" not in combined
    assert "38102" not in client.get("/api/meta").text
    assert "artificial-test-key" not in client.get("/api/meta").text


def test_frontend_has_no_direct_upstream_or_unsafe_dom() -> None:
    script = Path(ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    lowered = script.lower()
    assert "tankerkoenig" not in lowered
    assert "innerhtml" not in lowered
    assert "localstorage" not in lowered
    assert "sessionstorage" not in lowered
    assert "indexeddb" not in lowered
    assert "setinterval" not in lowered
    assert "serviceworker" not in lowered
    assert ".textcontent" in lowered


def test_untrusted_station_text_is_only_handled_as_text() -> None:
    script = Path(ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    assert "name.textContent = station.name" in script
    assert "meta.textContent =" in script


def test_no_likely_real_uuid_api_key_committed() -> None:
    root = Path(ROOT)
    pattern = re.compile(
        r"(?i)(?:TANKERKOENIG_API_KEY\s*=\s*)"
        r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
        r"[89ab][0-9a-f]{3}-[0-9a-f]{12}"
    )
    excluded = {".git", ".venv", "__pycache__", ".pytest_cache"}
    for path in root.rglob("*"):
        if not path.is_file() or any(part in excluded for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        assert pattern.search(text) is None, f"Likely API key in {path.relative_to(root)}"
