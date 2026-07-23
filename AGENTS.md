# Repository guidance

FuelFinder Local is a privacy-first, single-process FastAPI application.

- Never commit or log a Tankerkönig API key.
- Never add browser storage, analytics, telemetry, cookies, geolocation, external frontend assets, or automatic polling.
- Keep the browser same-origin and the runtime bound to 127.0.0.1 by default.
- Mock every upstream request in tests.
- Preserve Tankerkönig / MTS-K and GeoNames attribution.
- Use Decimal for currency calculations and monotonic time for limit enforcement.
