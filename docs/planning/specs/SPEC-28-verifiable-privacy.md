# SPEC-28 — Verifiable Privacy (Egress Monitor + Airplane Lock)

- **Links:** MARKET-PAINS-2026 P-2 · relates to SEC-1/SPEC-01 (sidecar auth), SPEC-24 (ledger)
- **Priority:** P1 · **Effort:** M
- **Review status:** ⬜ pending review
- **Type:** gap-driven product spec (community pain research)
- **Why ours is different:** Solo already makes zero telemetry calls — but so do tools that *claim* to and then get caught (Ollama startup pings, ComfyUI telemetry that ignored its own off-switch). The differentiator is not "we're private," it's "you can *watch* that we're private." Cloud assistants structurally cannot offer this.

## 1. Problem

The most trust-corrosive theme in the local-AI world isn't cloud AI — it's discovering that supposedly-local tools phone home anyway. Users want *verifiable* offline behaviour, not a promise: a way to see exactly what (if anything) leaves the machine, and a hard switch to guarantee nothing does. Today Solo is clean but opaque — a privacy-conscious user has no in-app way to confirm it, which means we get zero credit for a real advantage.

## 2. v1 Scope

1. **Network activity panel** (Settings → Privacy, or a status-bar shield icon). A live, human-readable log of every outbound connection the sidecar makes: timestamp, destination host, purpose (model download / cloud provider you configured / channel you connected / update check), and bytes. Empty by default during local inference — that emptiness is the feature.
2. **The honest manifest.** A static, in-app statement: "Solo only ever connects to the internet for: (a) downloading models you choose, (b) cloud providers *you* added a key for, (c) channels *you* connected, (d) [update check, if any — see §5]. Nothing else, ever." Each item links to where in the UI it's controlled.
3. **Airplane lock** — a hard egress toggle. When ON, the sidecar refuses all outbound network calls except an explicit allowlist (loopback always; nothing else unless the user adds it). Flips the app into provably-offline mode: local models + KB + crews keep working; any code path that tries to reach the network fails closed with a clear "blocked by Airplane lock" message rather than silently.
4. **"What just happened" on block.** If something is blocked by the lock (e.g. a crew step tries to post to a channel), surface it in the panel + as a ledger entry, so the user sees the system *enforcing* the promise.

## 3. Architecture sketch

- **Chokepoint, not sprinkling.** Route all backend outbound HTTP through a single client wrapper (`services/net_guard.py` or extend the existing requests/httpx usage) so there's exactly one place that logs + enforces. Audit for bypasses: `model_manager` (downloads), `cloud_provider_service` / `model_dispatcher` (cloud inference), channel adapters (`reddit_poller`, telegram/discord/etc.), `huggingface-hub` (whoami/test). Each gets a `purpose` tag.
- **Enforcement:** the wrapper checks the airplane-lock state + allowlist before every request; blocked → raise a typed `EgressBlocked` exception mapped to a friendly message. Loopback (sidecar↔frontend) is never affected.
- **Log store:** ring buffer in memory + optional persisted tail (the panel reads it); also emit SPEC-24 ledger events so egress is auditable post-hoc.
- **Frontend:** Privacy panel + a small persistent shield indicator (green = no egress since launch / amber = configured egress occurred / locked = airplane on). Keep it glanceable.
- **Caveat to document honestly:** this monitors *Solo's own* traffic via its single client, not the whole OS. It is not a firewall and shouldn't claim to be. Wording must say "everything Solo sends goes through here" — true because we own the chokepoint — without implying we police other processes.

## 4. Enterprise port

Inverts cleanly: the same egress log becomes a compliance/audit feed (which data left, to which provider, under whose key), and "airplane lock" becomes an admin policy ("this workspace may only reach approved endpoints"). Feeds the SPEC-24 governance ledger directly.

## 5. Open questions

- **Update checks:** does Solo check for app updates on launch? If yes, it must appear in the manifest and be independently toggleable (the Ollama #2567 complaint is *exactly* an undisclosed update ping). If no, state "Solo never checks for updates automatically" as a selling point. **Decide before shipping the manifest — getting this wrong is the one thing that would detonate the whole trust play.**
- Airplane lock default: off (with a one-tap enable) vs. a first-run choice. Proposed: off by default, prominently offered during onboarding for the privacy-max crowd.
- Persist the egress log across restarts, or session-only? (Proposed: session-only in v1 + opt-in persistence, to avoid creating a sensitive history file by default.)

## 6. Acceptance criteria

- With no cloud keys and no channels configured, running local chat + a KB query + a crew produces an **empty** egress panel and a green shield. (Verifiable by a test that asserts the net-guard logged zero outbound calls during a local-only flow.)
- Adding a cloud provider and sending one message shows exactly one egress entry to that provider's host, tagged correctly.
- Airplane lock ON: a crew step that would post to a channel fails closed with "blocked by Airplane lock", logs the block, and local inference is unaffected.
- No outbound code path bypasses the net-guard (enforced by a test that greps for direct `requests`/`httpx`/`urllib` use outside the wrapper, or a runtime assertion in debug builds).

## 7. Out of scope (v1)

OS-level firewalling; per-destination granular allowlist UI (v1 is a single lock + the fixed legitimate categories); network monitoring of the Tauri/Rust shell itself (document that the shell makes no calls rather than instrumenting it, if true — verify).
