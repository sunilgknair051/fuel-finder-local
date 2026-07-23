# Privacy

FuelFinder Local is designed to minimize data handling and to run on one computer.

## What the application does not do

The application has no accounts, login, cookies, sessions, analytics, advertising,
telemetry, fingerprinting, crash-reporting service, persistent search history,
database, browser storage, browser geolocation, or external address autocomplete.
It does not intentionally retain client IP addresses, user-agent strings, postcodes,
coordinates, request bodies, or search preferences in logs.

The postcode and search preferences exist temporarily in browser and backend request
memory. The in-memory station cache is keyed by resolved coordinates and normalized
radius, expires completely after the stale window, and is never persisted to disk.

## What leaves the computer

Postcode lookup happens against the local bundled dataset. The raw postcode is not
sent to Tankerkönig, GeoNames, Google, OpenStreetMap, or any geocoding service.

An explicit search may cause the local server to send latitude, longitude, radius,
and the operator's API key to Tankerkönig. The network connection exposes the app
host's IP address to Tankerkönig in the normal operation of the internet. FuelFinder
Local therefore cannot truthfully promise that absolutely no information leaves the
device.

The browser communicates only with the local FastAPI server. No frontend asset,
font, icon, map, script, stylesheet, tracker, or analytics resource is loaded from a
third party.

## Operator responsibility

The operator controls the machine, API key, network, process logs, and any reverse
proxy they add. Running behind another server can change this privacy description.
The supported default binds only to 127.0.0.1 and disables Uvicorn access logs.
