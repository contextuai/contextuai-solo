# Gaps & Findings Register

> Every issue found in the 2026-06-11/12 review. Severity is judged against a **single-user desktop threat model** (different from server). Items marked *(audit)* came from a sub-agent audit pass and should be re-verified at file level by the implementing agent; items marked *(verified)* were confirmed first-hand (code read + reproduced where applicable).
>
> Status: ✅ Fixed · 🔴 Open · 🟠 Open (needs verification) · ⚪ Accepted risk / informational

## Security

| ID | Finding | Sev | Status | Evidence | Spec |
|----|---------|-----|--------|----------|------|
| SEC-1 | Sidecar has **no auth** and `allow_origins=["*"]` — any local process or drive-by webpage can call `localhost:18741`, including `/v1/chat/completions` which spends saved cloud API keys | Critical | 🔴 | `backend/app.py:71-76` *(verified)*; desktop auth bypass via dependency overrides in `app.py` | SPEC-01 |
| SEC-2 | Cloud provider keys + channel tokens (Telegram/Discord/Reddit/SMTP) stored **plaintext** in SQLite (`cloud_provider_keys` etc.) | High | 🔴 | `backend/models/cloud_provider_models.py` ("no encryption layer in v1") *(audit)* | SPEC-02 |
| SEC-3 | Coder "allowlist" is only a per-project `trusted` boolean — a trusted project can execute any binary | High | 🔴 | `backend/services/coder_run_service.py` *(audit)* | — (shape in FEATURES first) |
| SEC-4 | Tauri CSP is `null` — any XSS escalates to IPC access | Medium | 🔴 | `frontend/src-tauri/tauri.conf.json` `security.csp: null` *(audit)* | SPEC-12 |
| SEC-5 | SSRF blocklist (localhost, 169.254.169.254) only active when `environment == "prod"` — desktop mode skips it; agents can call the sidecar's own API | Medium | 🔴 | `backend/services/tools/api_tools.py` *(audit)* | SPEC-05 |
| SEC-6 | `create_index` interpolates field names into SQL f-strings (internal-only callers today) | Low | 🟠 | `backend/adapters/sqlite_adapter.py:~370` *(audit)* | fold into SPEC-04 |
| SEC-7 | No rate limiting on inference endpoints | Low | ⚪ | Single-user desktop; revisit if SEC-1 token ships and `/v1` stays open | — |
| SEC-8 | Personal-docs folder walker accepts any path (user-chosen, so partly by design) | Low | ⚪ | `services/folder_walker.py` — `followlinks=False` already set *(audit)*; the "attacker" is the user themselves on desktop | — |

## Reliability

| ID | Finding | Sev | Status | Evidence | Spec |
|----|---------|-----|--------|----------|------|
| REL-0 | **Model Hub downloads failed on many Windows machines.** Root causes: (1) huggingface_hub 1.x Xet protocol (`*.xethub.hf.co`) blocked by firewalls/AV/DNS filters while huggingface.co works; (2) 60s stall detector fired before first progress on slow links (progress only per 10MB tqdm chunk), deleted the partial file, and left a hung thread holding the HF lock → all retries failed until restart; (3) cancel flag never checked → cancel was a no-op; (4) 3 catalog Gemma QAT repos are gated → anonymous 401 for everyone | Critical | ✅ Fixed | *(verified, reproduced, tested)* — branch `fix/model-hub-downloads`, commit `f987477`. New plain-HTTPS downloader w/ resume, cancel, disk preflight, friendly errors | done |
| REL-1 | Port-18741 conflict / orphaned sidecar = silent blank app; startup errors not surfaced; crash leaves orphan process that blocks next launch | High | 🔴 | `frontend/src-tauri/src/sidecar.rs`, `main.rs` (setup spawns sidecar without awaiting result) *(audit)* | SPEC-03 |
| REL-2 | `update_one` is read-modify-write — concurrent crew runs can clobber each other's state; no versioning/CAS | High | 🔴 | `backend/adapters/sqlite_adapter.py:166-189` *(audit, code excerpt seen)* | SPEC-04 |
| REL-3 | Streamed assistant message stored once after stream end with `except Exception: pass` — DB lock = message silently lost; no dedup on client resubmit | Medium | 🔴 | `backend/routers/ai_chat.py` (`local_event_generator`, ~472-517) *(audit)* | SPEC-06 |
| REL-4 | Ollama streaming path doesn't catch `GeneratorExit`/`CancelledError` (local path does) — backend keeps generating after client abort | Medium | 🔴 | `backend/routers/ai_chat.py` Ollama generator *(audit)* | SPEC-06 |
| REL-5 | Startup seeds/migrations fail with log-and-continue → blank `/agents` page, silent migration skips | Medium | 🔴 | `backend/app.py` startup event (~472-610) *(audit)* | SPEC-07 |
| REL-6 | Frontend: stale personas/KBs on mode toggle (only models reload on `aiMode` change); missing loading states in chat/models/crews pickers | Low | 🔴 | `frontend/src/routes/chat.tsx` (~88-144) *(audit)* | fold into SPEC-09 or later UX pass |
| REL-7 | `huggingface-hub>=0.20.0` unpinned — source installs drift across major versions | Low | 🔴 | `backend/requirements.txt:63` *(verified)* | fold into SPEC-08 |
| REL-8 | Local model swap: `.close()` and `.__del__()` both called on Llama; n_ctx tuning not persisted across reloads | Low | 🟠 | `backend/services/local_model_service.py` (~253-268) *(audit)* | — |

## Product gaps (features that exist but underperform, or missing)

| ID | Finding | Status | Spec / FEATURES |
|----|---------|--------|-----------------|
| PROD-1 | No way to supply an HF token from the UI — anonymous 429 rate limits + gated custom repos fail with env-var-only workaround | 🔴 | SPEC-08 / A7 |
| PROD-2 | First local-model message takes 5–15s (cold load) with no feedback | 🔴 | SPEC-09 / A1 |
| PROD-3 | No way to test a crew before it goes live on a channel | 🔴 | SPEC-10 / A2 |
| PROD-4 | Folder-mapped KBs can silently go stale; no freshness signal anywhere | 🔴 | SPEC-11 / A4 |
| PROD-5 | No crew sharing/templates beyond the 10 built-in blueprints | 🔴 | FEATURES A5 (not spec'd yet) |
| PROD-6 | No batch processing story | 🔴 | FEATURES A6 (not spec'd yet — needs scope decision) |
| PROD-7 | No crew/automation observability (runs, errors, trigger hit-rates) | 🔴 | FEATURES A3 (not spec'd yet) |

## Marketing site

| ID | Finding | Status | Spec |
|----|---------|--------|------|
| MKT-1 | Reddit integration built but absent from the channels grid / site | 🔴 | SPEC-13 |
| MKT-2 | `cookbook.html` exists but is orphaned (no navbar/footer link) | 🔴 | SPEC-13 |
| MKT-3 | ~5 footer links and 3 blog cards are `href="#"` placeholders | 🔴 | SPEC-13 |
| MKT-4 | No persistent download CTA after hero scroll | 🔴 | SPEC-13 |
| MKT-5 | No sitemap.xml, no custom 404, thin/missing alt text on screenshots | 🔴 | SPEC-13 |
| MKT-6 | Differentiators unmarketed: folder-mapped KB, OpenAI-compat API ("use with Cursor/Continue/Aider"), coder-companion agents, Brand Voice | 🔴 | SPEC-13 (C5/C6 scoped as content pages) |
| MKT-7 | `firebase.json` references `firestore.rules` + `functions/` — existence/deployability unverified; "Workshop" naming on index.html is outdated (now Crews/Projects) | 🟠 | SPEC-13 |

## Cross-cutting notes for reviewers

- SEC-1 has a product tension: the OpenAI-compat `/v1/*` endpoints are *meant* for third-party local clients. SPEC-01 proposes gating `/api/v1/*` with a token while leaving `/v1/*` configurable (off by default? toggle in Settings?). **Decision needed from Nagendra.**
- SEC-3 (coder exec allowlist) is deliberately not spec'd: a per-binary allowlist will frustrate legitimate dev workflows. Needs a product conversation (prompt-per-command? trust levels?) before speccing.
- REL-2's fix (SPEC-04) touches the hottest code path in the adapter; it must keep the Motor-compat semantics intact — large test surface, do not rush.
