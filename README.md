# FuelFinder Local

FuelFinder Local is a privacy-focused, open-source fuel-price webpage for Germany.
One Python process serves one local webpage and a same-origin FastAPI backend at
<http://127.0.0.1:8000>.

It searches current E5, E10, and Diesel prices through one Tankerkönig type=all
radius request, resolves German postcodes locally, and protects the free upstream API
with a five-minute in-memory cache, a 65-second global limiter, request coalescing,
stale fallback, and a circuit breaker.

## Privacy and architecture

- One Python process; no separate frontend service, database, container stack, or cloud service.
- No accounts, cookies, sessions, tracking, analytics, telemetry, advertising, browser storage, or automatic polling.
- No geolocation, online geocoding, maps, CDNs, external fonts, scripts, or styles.
- POST search keeps the postcode out of URLs and ordinary access logs.
- The raw postcode is resolved locally and is never sent to Tankerkönig.
- An explicit uncached search necessarily sends latitude, longitude, radius, and the
  operator's API key to Tankerkönig. The host IP is visible to Tankerkönig in the
  normal way. See [PRIVACY.md](PRIVACY.md).

## Requirements

- Python 3.12 or newer
- A Tankerkönig API key
- A locally downloaded GeoNames DE.zip only when building the complete postcode dataset

Do not use the free Tankerkönig API if you are a mineral-oil company, fuel-station
operator, related company, or an IT service provider acting for that industry.

## Install and run

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
Copy-Item .env.example .env
# Edit .env and set TANKERKOENIG_API_KEY to your own key.
python -m app.main
```

You can subsequently start it with run.bat.

### Linux or macOS

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
cp .env.example .env
# Edit .env and set TANKERKOENIG_API_KEY to your own key.
python -m app.main
```

You can subsequently start it with ./run.sh.

Open <http://127.0.0.1:8000>. The process binds only to 127.0.0.1 and disables
Uvicorn access logs. Never commit .env or place the key in a command, URL, test,
screenshot, issue, or log.

## German postcode dataset

The repository includes the 38102 bootstrap entry so the documented acceptance
search works immediately. For complete German coverage:

1. Download DE.zip yourself from <https://download.geonames.org/export/zip/>.
2. Do not extract it unless desired.
3. Run:

```sh
python scripts/build_postcode_dataset.py /path/to/DE.zip
```

The script validates German five-digit postcodes and coordinates, deterministically
consolidates duplicates, and writes data/postcodes_de.json with source, license,
and attribution metadata. It performs no network access. Normal startup never
downloads or calls a geocoder.

## Currency configuration

Tankerkönig supplies EUR per litre. No live conversion service is used. Edit
config/exchange_rates.json to add a locally sourced indicative rate:

```json
{
  "base": "EUR",
  "as_of": "YYYY-MM-DD",
  "rates": {
    "EUR": 1.0,
    "USD": 0.0
  }
}
```

Replace 0.0 with an actual positive operator-provided rate; zero and negative
rates are ignored. The selector is generated from this file. The calculation is
converted_price = eur_price * configured_rate, performed with Python Decimal
and displayed to three decimal places. You can similarly configure GBP, CHF, INR,
or another ISO-style code. Original EUR/L values remain visible.

## API behavior

- GET / — the single locally served webpage
- GET /api/meta — safe UI options and exchange-rate metadata
- POST /api/search — validated search; no API key is returned
- GET /healthz — basic status only

The upstream cache key contains only resolved coordinates and radius in kilometres.
Fuel, currency, sorting, unit display, and open-only changes are applied locally.
A refresh is always explicit. There are no scheduled, focus-triggered, or background
requests and no immediate automatic retry.

Fresh cache entries last 300 seconds. Entries remain eligible as visibly marked stale
fallback for up to 30 minutes. Across the process, at most one real upstream attempt
starts per 65 seconds. After three failures, the circuit pauses upstream calls for five
minutes. Defaults can be adjusted with the uppercase environment variables documented
in app/config.py; lower values are intended only for tests.

## Tests and quality

Live Tankerkönig access is forbidden in tests. Install the test extra and run:

```sh
pip install -e ".[test]"
pytest
ruff check .
ruff format --check .
mypy app scripts
```

GitHub Actions runs the same checks on Python 3.12. Tests use an artificial API key
and mocked clients only.

## Attribution and license

Fuel-price and station data: **Tankerkönig / MTS-K, CC BY 4.0**.

Postal-code coordinates: **GeoNames, CC BY 4.0**.

Neither data provider endorses FuelFinder Local. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Application source code is licensed under
[AGPL-3.0-or-later](LICENSE).
