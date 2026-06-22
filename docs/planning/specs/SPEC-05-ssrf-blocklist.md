# SPEC-05 — Always-On SSRF Blocklist

- **Links:** GAPS SEC-5 · FEATURES B5
- **Priority:** P0 (XS effort — good first spec to execute)
- **Review status:** ⬜ pending review

## 1. Goal

Agent-driven HTTP tools (API Connector, web tools) can never target loopback, link-local/metadata, or the sidecar itself — regardless of environment.

## 2. Context (verify before coding)

- `backend/services/tools/api_tools.py`: blocklist (`localhost`, `127.0.0.1`, `0.0.0.0`, `169.254.169.254`) is only installed when `environment == "prod"`. Desktop runs as non-prod → unprotected.
- `backend/services/tools/web_tools.py`: reported to have no localhost blocking — verify.
- Risk on desktop: a crew/automation prompt (possibly fed by inbound channel content — i.e., attacker-influenced) makes an agent call `http://127.0.0.1:18741/api/v1/...`, reaching the unauthenticated sidecar API.

## 3. Plan

1. Create one shared helper, e.g. `services/tools/url_guard.py`: `assert_url_allowed(url: str) -> None`.
   - Parse host; resolve DNS (`socket.getaddrinfo`) and reject if **any** resolved address is loopback (`127.0.0.0/8`, `::1`), link-local (`169.254.0.0/16`, `fe80::/10`), unspecified (`0.0.0.0`, `::`), or the sidecar port on any host. Use `ipaddress` stdlib.
   - Rejecting private LAN ranges (`10/8`, `172.16/12`, `192.168/16`) would break legitimate home-lab use (local Ollama on another box, self-hosted blog) — **default allow, but block when scheme is http and host is the sidecar**. (Reviewer: confirm this trade-off.)
2. Apply unconditionally in `api_tools.py` and `web_tools.py` before every request, including on **redirect targets** (requests: use `allow_redirects=False` loop or hook to re-validate each hop).
3. Keep the existing prod-only config as additional entries, not the mechanism.

## 4. Acceptance criteria

- Agent tool call to `http://localhost:18741/...`, `http://127.1:18741`, `http://169.254.169.254/latest/meta-data/` → blocked with a clear tool-result error, in desktop mode.
- `https://example.com` and `http://192.168.x.x:11434` (Ollama) still work.
- A 302 from a public URL to `http://127.0.0.1:18741` is blocked.

## 5. Test plan

Unit tests for `url_guard` (each range + DNS-resolution case with mocked `getaddrinfo`, redirect re-check). Existing tool tests stay green.
