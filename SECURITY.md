# Security policy

## Supported version

The latest release on the default branch receives security fixes.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting feature for this repository.
Do not open a public issue for a suspected API-key exposure or exploitable flaw.

Never include a real Tankerkönig API key, personal data, postcode, client address,
request body, or complete upstream URL in a report. Use clearly artificial values.

## Local security model

FuelFinder Local binds to 127.0.0.1 by default, disables access logging, exposes no
interactive API documentation, enables no CORS, and applies a local-only Content
Security Policy and browser hardening headers. It is not designed to be exposed
directly to the public internet.

Keep Python and dependencies updated, protect the local environment file, and rotate
the Tankerkönig key immediately if it may have been disclosed.
