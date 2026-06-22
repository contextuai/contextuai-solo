# SPEC-25 — Mobile Companion (Approvals + Pulse)

- **Links:** ROADMAP F-13 (Q2 2027) · MOONSHOT BL-7 · depends on SPEC-01 (auth), SPEC-16 (Pulse)
- **Priority:** P2 · **Effort:** L
- **Review status:** ⬜ pending review
- **Type:** roadmap spec (requires a design doc; biggest unknown is connectivity)

## 1. Goal

Approve drafted replies and read your Pulse from your phone. Deliberately narrow: a remote control for the trust surface, not Solo-on-mobile.

## 2. v1 Scope

1. **App** — React Native (one codebase, reuse TS types from `lib/api/`) or Tauri Mobile (evaluate maturity in design doc). Two screens + settings: **Approvals** (list → detail → approve/edit/reject) and **Pulse** (card stack, read-only actions where safe).
2. **Connectivity (the hard part)** — v1: **same-LAN direct** to the sidecar over HTTPS with the SPEC-01 token, paired via QR code shown in desktop Settings (encodes host, port, token, self-signed cert fingerprint). No cloud relay in v1 — keeps the privacy story pure and scope sane. Out-of-home access documented honestly: "use Tailscale/WireGuard" (works unmodified with LAN mode).
3. **Notifications** — no APNS/FCM without a relay; v1 uses background fetch polling (platform-limited, ~15 min granularity) + honest docs. Real push arrives with the (optional, off-by-default) relay in v2.
4. **Desktop side** — sidecar serves the paired-device API surface (auth via device-scoped tokens, revocable in Settings → Devices); TLS via self-signed cert generated at pairing.

## 3. Enterprise port

Same app pointed at the SaaS backend (real push, real accounts) — connectivity problem disappears; approvals/Pulse map to enterprise equivalents. The Solo LAN mode stays as the privacy-max option.

## 4. Acceptance criteria

- QR pairing from desktop to phone on the same Wi-Fi in < 1 minute; approve a real pending reply from the phone; it sends from the desktop.
- Token revocation in desktop Settings immediately cuts the device off.
- Phone on another network: clean "can't reach your Solo" state with the Tailscale doc link (no hang, no crash).
- Works on Android + iOS (TestFlight/internal track acceptable for v1).

## 5. Open questions

- React Native vs Tauri Mobile vs a PWA served by the sidecar (PWA = zero app-store friction, weaker notifications — genuinely tempting for v1; design doc must compare all three).
- iOS app review with a "connects to your own server" app — known friction; PWA sidesteps it entirely.
- Is edit-before-approve needed on phone v1, or approve/reject only? (Proposed: full edit — it's the whole point of approvals.)
