# OpenBiliClaw XHS Sidecar

This directory defines an isolated Docker container that provides xhs
(小红书) note-detail enrichment for the OpenBiliClaw backend. It exists to
keep GPL-3.0 code out of the main backend's import graph.

## What it does

Exposes exactly two HTTP endpoints on port 5556:

- `GET /health` — liveness probe
- `POST /xhs/detail` — body `{ "url": "<xhs note URL>" }`, returns normalized note metadata

That is the complete surface. The sidecar never accepts search, feed, or
user-listing requests. Content **discovery** (finding which URLs to enrich) is
the responsibility of the browser extension, not this sidecar.

## Architecture

```
OpenBiliClaw backend  ──HTTP──▶  xhs-sidecar (this container)
                                    │
                                    └── imports XHS-Downloader (GPL-3.0)
```

The main backend talks to this sidecar exclusively over HTTP. It does not
`pip install` XHS-Downloader, does not import from it, does not bundle its
code. That separation is intentional:

- XHS-Downloader is GPL-3.0. Embedding it as a library would make the whole
  OpenBiliClaw project a GPL-3.0 derivative.
- Running it in a separate process and communicating via HTTP is generally
  accepted as aggregation rather than a derivative work boundary.

This wrapper itself (the `wrapper.py` file) *is* a derivative work of
XHS-Downloader and is therefore distributed under GPL-3.0. See `LICENSE`.

## Upstream

- Project: https://github.com/JoeanAmier/XHS-Downloader
- Pinned commit: `5f9bd542e3c0c2689e5ea4481b8726927da761c2` (2026-04-17)
- License: GPL-3.0

The Dockerfile clones the upstream repo at build time, pinned to the commit
above, so builds are reproducible and license compliance is transparent.

## Running locally

```bash
docker build -t openbiliclaw-xhs-sidecar:dev sidecar/xhs-downloader/
docker run --rm -p 5556:5556 openbiliclaw-xhs-sidecar:dev
curl -sf http://127.0.0.1:5556/health
```

Inside `docker compose` the sidecar is reachable from the backend at
`http://xhs-sidecar:5556/xhs/detail`.

## License

GPL-3.0. See `LICENSE` for the full text. This is a derivative work of
XHS-Downloader under the same terms.
