# SPEC-33 — Enterprise Desktop Lite Build Target

- **Links:** Enterprise Desktop track · Solo SPEC-31/32 · evaluation of 2026-08-12 (build-flags decision: separate app, same codebase — "a fork would drift in a month")
- **Priority:** P2 (gated on the same demand gate as SPEC-32) · **Effort:** L
- **Review status:** ⬜ pending review
- **Prereqs:** SPEC-31 merged; SPEC-32 at least in progress (the lite app's headline surface is enrollment); code-signing credential acquired (EV cert on ContextuAI LLC — external lead time, started separately).

## 1. Goal

A second build target of this codebase — **ContextuAI Enterprise Desktop** (`com.contextuai.desktop`) — that ships only: chat + history, org/managed models (the ladder), MCP personas, enrollment/settings. Everything else is **compiled out, not hidden**: smaller installer, smaller attack surface, and a security-review one-pager that can say "agents, crews, automations, coder mode, publishing are not in the binary" as an auditable claim. Solo's own build is byte-identical to today.

## 2. Context (verify before coding)

- **No variant mechanism exists**: single `frontend/src-tauri/tauri.conf.json` (`com.contextuai.solo`, `targets: "all"`), no Cargo features, no Vite mode branching (`vite.config.ts` only sets `envPrefix`). Tauri supports `--config` overlay merging — the intended mechanism.
- **Updater collision (must-fix)**: `tauri.conf.json` plugins.updater (~lines 56-64) — one minisign pubkey, one GitHub `latest.json`. A lite build sharing it would auto-update into full Solo. Lite needs its own keypair + endpoint.
- **No code signing anywhere**: no `certificateThumbprint`/`signCommand` in tauri.conf; `codesign_identity=None` in `backend/contextuai-solo-backend.spec:63`. Signing lands here for the lite target (Solo may adopt it after). Note: CI's `TAURI_SIGNING_PRIVATE_KEY` secret is the **updater minisign key**, not Authenticode — do not confuse the two.
- **CI/CD release pipeline already exists** (`.github/workflows/release.yml`, verified 2026-08-14): three triggers (workflow_dispatch with version input · `v*` tag push · `chore: release vX.Y.Z` commit on main), a compute job that cross-checks the version across `package.json`/`tauri.conf.json`/`Cargo.toml` before tagging, a 3-OS build matrix (PyInstaller sidecar → Tauri bundle → collect installers), GitHub Release publish, and generated updater `latest.json`. **Solo-specific assumptions baked in**: asset names hardcode "ContextuAI Solo", `latest.json` points at the Solo release URL, and the tag pattern is `v*` only — the desktop edition cannot ride this workflow unmodified.
- Sidecar flag precedent: `backend/services/feature_flags.py` (env-truthy pattern). Frontend mode precedent: `src/contexts/mode-context.tsx` — but that is a *runtime* toggle; this spec is *build-time*.
- Measured baseline artifacts (Jun 2026 build): sidecar dir 268MB (llama-cpp, onnxruntime, HF hub, embedding model, agent-library, blueprints), MSI ~137MB, NSIS ~109MB. The lite sidecar should drop the agent-library/blueprint/crew payloads; measure the delta as an acceptance number.
- Persona types seeded in `backend/app.py:_DEFAULT_PERSONA_TYPES` (~130-230): DB types (postgresql/mysql/mssql/snowflake/mongodb), `mcp`, `api_integration`, `file_operations`. Lite keeps `mcp` (endpoint + headers; credentials stay on the MCP server) and drops raw-credential types — the evaluation's refined guardrail: *credential-holding stays off the laptop*.

## 3. Plan

> **Layering note (founder decision 2026-08-14):** SPEC-32 ships the same feature flags as a *runtime* policy layer first (enrolled Solo can present the lite experience via org policy). This spec consumes the identical flag names and evaluates them at **build time** — tree-shaken frontend, unregistered routers, excluded payloads — because "not in the binary" is the security-review claim runtime hiding cannot make. Runtime = governance knob; build-time = security boundary.

1. **One flag, three layers.** `CONTEXTUAI_EDITION=solo|desktop`:
   - **Frontend**: Vite `define` constant → route registry and nav exclude stripped surfaces at build time (tree-shaken, not `display:none`). Stripped: agent library, crews, blueprints, automations, coder mode, publishing/social connections, workspace/approvals. Kept: chat, models/settings, connections limited to MCP personas, enrollment card.
   - **Sidecar**: edition env baked by the shell at spawn; stripped routers are **not registered** in `app.py` for the desktop edition (a 404 surface, not a policy check); `_DEFAULT_PERSONA_TYPES` seeds only `mcp` for desktop edition.
   - **Packaging**: second PyInstaller spec (or spec parameterization) excluding agent-library/blueprints/crew-template payloads from the bundle.
2. **Tauri overlay** `tauri.desktop.conf.json`: `com.contextuai.desktop`, productName "ContextuAI Enterprise Desktop", its own icon, **its own updater pubkey + endpoint** (new minisign keypair; separate `latest.json` — decision below on hosting), window title. Build via `tauri build --config tauri.desktop.conf.json`; `build.ps1` gains an `-Edition` parameter driving all three layers.
3. **Code signing**: wire `signCommand` (cloud-HSM CLI — SSL.com eSigner or equivalent CI signer on the ContextuAI LLC EV cert) into the desktop overlay; sign the sidecar exe inside the bundle too (the PyInstaller output is what EDR actually inspects). Document the local-dev path (unsigned dev builds still work when the signing env is absent).
4. **KB stays out of the lite v1** (evaluation: v1.1 candidate) — behind the same edition flag, one-line flip later.
5. **CI/CD**: a second workflow `release-desktop.yml` keyed on `desktop-v*` tags (+ workflow_dispatch), cloned from `release.yml` with: matrix = **Windows only** in v1; edition env + desktop PyInstaller spec + `--config tauri.desktop.conf.json`; an **Authenticode signing step** (EV cloud-signing CLI on new secrets — cert credentials/TOTP) signing the MSI/NSIS *and* the inner sidecar exe; its own updater secret (`TAURI_SIGNING_PRIVATE_KEY_DESKTOP`, new minisign keypair) and its own `latest.json` with desktop asset names/URLs. The compute job's version cross-check reads the desktop overlay's `version` (the overlay carries it, so the two edition versions are independent). `pr-checks.yml` gains the cheap dual-edition assertion: run the sidecar route-matrix pytest with `CONTEXTUAI_EDITION` set both ways.
5. **Docs**: README section "Solo vs Enterprise Desktop" (one table); the "no accounts, no telemetry" promise gets its precise form: *"this app talks to no one unless you connect it to your organization"* — applies to both editions.

## 4. Acceptance criteria

- `build.ps1 -Edition desktop` produces a signed MSI/NSIS with its own identity; installing both apps side-by-side works; **neither updater ever offers the other edition's artifact** (test with a staged manifest).
- In the desktop edition: stripped routes 404 at the sidecar and are absent from the JS bundle (grep the built assets for a crew-only string as a build test); persona-type list contains only `mcp`; raw-credential persona creation is impossible via API, not just UI.
- `build.ps1 -Edition solo` (and default) output is byte-comparable to pre-spec behavior (same routes registered, same seeds, same updater endpoint).
- Lite installer measurably smaller than Solo's (record the number; expectation: sidecar payload drop is the bulk).
- `signtool verify` passes on the MSI and the inner sidecar exe; SmartScreen shows the LLC publisher name on a fresh VM.

## 5. Decision needed

- **Lite updater hosting**: separate GitHub repo/release train vs the Enterprise server itself serving update manifests to enrolled fleets (the evaluation flagged GitHub-blocked bank networks; server-hosted updates may become an Enterprise spec). v1 proposal: GitHub for the free/standalone lite build, note the org-hosted channel as the follow-up.
- Whether the desktop edition is present in this public repo's release page from day one (free/OSS per the pricing decision) or only distributed from the marketing site initially.

## 6. Out of scope

macOS signing/notarization (Windows-first; own spec when a customer runs Macs); MDM deployment guide (launch asset, not code); VDI golden-image packaging docs; auto-update staged rollouts; renaming anything in the Solo edition.

## 7. Test plan

- CI: build both editions on every release branch; assert route-registration matrix per edition (pytest against the sidecar with `CONTEXTUAI_EDITION` set both ways); bundle-grep test for stripped surfaces; updater-manifest cross-check test.
- Manual: fresh Windows VM — install signed lite build, enroll against a dev Enterprise stack (SPEC-32 flow), verify publisher name in the UAC prompt, uninstall cleanly.
