# TODO — ContextuAI Lite ("Vesper" / "Lumen") & ContextuAI Solo (2026 Q4 – 2027 Plan)

> **Repository:** `contextuai-solo/`  
> **Created:** 2026-11-14  
> **Status:** 🟡 Awaiting Founder Review & Approval Before Implementation  
> **Strategy Alignment:** Build the next-generation local GGUF + MCP runtime inside `contextuai-solo` first, ship **Lite** (*Vesper* / *Lumen*) from the same repo as a sleek 4-tab MIT-licensed build target, and graduate users seamlessly into full **ContextuAI Solo**.

---

## Executive Architecture Decision: One Codebase, Two Build Targets

To move fast as a lean team without maintaining two diverging desktop repositories:
1. **Shared Core (`contextuai-solo`):** Both **Lite** and **Solo** share the same Tauri v2 Rust shell (`frontend/src-tauri/`), the same FastAPI sidecar (`backend/`), the same SQLite database (`~/.contextuai-solo/data/contextuai.db`), and the same local GGUF model directory (`~/.contextuai-solo/models/`).
2. **Build-Time & Runtime Edition Switch:** Controlled via `VITE_APP_EDITION=lite|solo` (frontend) and `CONTEXTUAI_EDITION=lite|solo` (backend).
3. **Zero-Friction Upgrade:** Because both editions use `~/.contextuai-solo/models/`, a user who downloads 20 GB of GGUF models in Lite can unlock/switch to Solo in one click with **zero re-downloading or migration**.

---

## TRACK 0: Immediate Hygiene, Security & Downloader Fixes (Week 1 — Prerequisite Baseline)

> **Goal:** Fix every broken promise, security hole, and download failure in Solo today before touching the new GPU runtime or Lite UI.

### PR 0.1: Merge Model Hub Downloader Fix, Ungate Gemma & Add HF Token UI (`SPEC-08`)
- **Why:** Branch `fix/model-hub-downloads` (`f987477`) was never merged to `main`; 3 Gemma catalog entries point to gated HuggingFace repos that fail without auth; users hitting HF anonymous 429 rate limits have no UI to add a token; power users cannot import an existing `.gguf` file from disk.
- **Files to Modify:**
  - [ ] Merge `fix/model-hub-downloads` into a fresh branch off `main`.
  - [ ] `backend/services/model_catalog.py` (lines 270–330) — Replace the 3 gated Google Gemma repos with ungated `bartowski/` or `unsloth/` GGUF repos so anonymous one-click downloads succeed.
  - [ ] `backend/models/cloud_provider_models.py` & `backend/routers/cloud_providers.py` — Add `huggingface` token storage in `cloud_provider_keys` (or dedicated settings key) and inject into `ModelManager._download_files()` alongside the `HF_TOKEN` env var.
  - [ ] `backend/routers/local_models.py` & `backend/services/model_manager.py` — Add `POST /api/v1/local-models/import` accepting a local file path (via Tauri file picker) to symlink/copy an existing `.gguf` file into `~/.contextuai-solo/models/` and auto-sync it.
  - [ ] `frontend/src/routes/models.tsx` & `frontend/src/components/cloud-providers/cloud-providers-tab.tsx` — Add "Import `.gguf` from Disk" button on the Models page and an optional "HuggingFace Access Token" card in Settings → AI Providers.
- **Verification / Tests:**
  - [ ] `pytest backend/tests/test_model_manager.py` — Verify cancel button stops active stream, HF token header is injected when saved, and all 41 catalog URLs return HTTP 200 on `HEAD` probe.

### PR 0.2: Sidecar Auth Token, CORS Lockdown & Unconditional SSRF Guard (`SPEC-01`, `SPEC-05`)
- **Why:** Currently `app.py` sets `allow_origins=["*"]` with credentials and requires no token on `/api/v1/*`, allowing any drive-by webpage to call `localhost:18741` and spend saved cloud API keys. Also, the SSRF guard in `api_tools.py` is only active in prod mode.
- **Files to Modify:**
  - [ ] `frontend/src-tauri/src/sidecar.rs` & `frontend/src-tauri/src/commands.rs` — Generate a 32-byte random hex `CONTEXTUAI_SIDECAR_TOKEN` at sidecar spawn, pass it in sidecar env, and expose an IPC getter `get_sidecar_token` for the frontend.
  - [ ] `frontend/src/lib/transport.ts` — Attach `X-ContextuAI-Token: <token>` header to all `/api/v1/*` HTTP and SSE requests when running inside Tauri.
  - [ ] `backend/app.py` (lines 70–85) — Restrict CORS `allow_origins` to `["tauri://localhost", "http://tauri.localhost", "https://tauri.localhost", "http://localhost:1420", "http://127.0.0.1:1420"]`. Add middleware requiring `X-ContextuAI-Token` on `/api/v1/*` when `CONTEXTUAI_SIDECAR_TOKEN` is set.
  - [ ] `backend/routers/openai_compat.py` — Keep `/v1/*` accessible for external dev tools (Cursor, Continue.dev, Aider), with an optional user-configurable `Bearer sk-local-...` key in Settings, and restrict `/v1/*` to local models by default unless "Allow Cloud Relay on `/v1`" is explicitly toggled on.
  - [ ] `backend/services/tools/api_tools.py` — Make the localhost/link-local/cloud-metadata IP SSRF blocklist unconditional across all environments.
- **Verification / Tests:**
  - [ ] `pytest backend/tests/test_sidecar_auth.py` — Unauthenticated `/api/v1/chat` returns `401` when token is configured; valid token returns `200`; SSRF unit test blocks `169.254.169.254` and `127.0.0.1` in dev and prod.

### PR 0.3: Fix `/v1` Concurrency Lock, Custom GGUF Resolution & CI Gate (`SPEC-03`)
- **Why:** `openai_compat.py:237` calls `_ensure_model()` directly without `local_model_service._inference_lock` (risking a native crash on concurrent IDE autocomplete + chat requests), `_resolve_model()` (`lines 114-135`) returns 404 for custom `.gguf` files not in `LOCAL_MODEL_CATALOG`, and `pr-checks.yml` never runs backend `pytest`.
- **Files to Modify:**
  - [ ] `backend/routers/openai_compat.py` (lines 114–136, 210–240, 550–620) — Fallback in `_resolve_model()` to check `model_manager.list_installed()` so any custom `.gguf` in `~/.contextuai-solo/models/` works via `/v1/chat/completions`, `/v1/completions` (FIM), and Crews. Route all `/v1` inference calls through `local_model_service._inference_lock` and `_LLAMA_EXECUTOR`.
  - [ ] `frontend/src-tauri/src/sidecar.rs` — Detect orphaned process on port `18741` at startup (health-check `/api/v1/health`; terminate stale sidecar before spawning fresh one) and surface startup errors to the frontend (`SPEC-03`, `SPEC-07`).
  - [ ] `.github/workflows/pr-checks.yml` — Add a `backend-pytest` job running `pytest backend/tests/ -v`.
- **Verification / Tests:**
  - [ ] `pytest backend/tests/test_openai_compat.py` — Verify custom non-catalog `.gguf` resolves and streams via `/v1/chat/completions` and `/v1/completions`.

---

## TRACK 1: The Next-Gen Local GGUF & MCP Engine (Weeks 2–5 — Shared Core for Lite & Solo)

> **Goal:** Make local GGUF inference in Lite and Solo genuinely superior to Ollama, LM Studio, and Jan in 2027 by solving hardware fit, GPU acceleration, silent context truncation, local MCP tool calling, vision, and verifiable privacy.

### PR 1.1: Hardware X-Ray & Per-Quant Fit Engine (`SPEC-27` — P0 Differentiator)
- **Why:** The #1 user pain in local AI is *"Will this model run on my PC, and what does `Q4_K_M` mean?"* Today `model_manager.py:105-120` only checks `nvidia-smi`.
- **Files to Create / Modify:**
  - [ ] **NEW:** `backend/services/hardware.py` — Pure-local hardware probe (0 network calls):
    - CPU: physical/logical cores, AVX2/AVX-512/NEON detection, architecture.
    - RAM: total & available GB via `psutil`, plus estimated memory bandwidth tier.
    - GPU: NVIDIA via `nvidia-smi` / NVML; AMD & Intel Arc on Windows via PowerShell/CIM `Win32_VideoController` + DXGI dedicated VRAM (`AdapterRAM` / registry `HardwareInformation.qwMemorySize`); Linux via `/sys/class/drm` / `vulkaninfo`; macOS Apple Silicon Unified Memory via `sysctl hw.memsize` + `system_profiler SPDisplaysDataType`.
  - [ ] **NEW:** `backend/services/model_fit_engine.py` — Deterministic `classify_model_fit(catalog_entry, hardware_profile)` returning:
    - `verdict`: `"fits_gpu"` (`✅ Runs Fast in GPU`), `"partial_offload"` (`⚠️ Runs on CPU / Partial Offload`), or `"wont_fit"` (`🚫 Needs X GB, you have Y GB`).
    - `estimated_tps`: coarse `tok/s` range based on model GB, quant, and GPU/CPU bandwidth class.
    - `recommended_n_ctx`: largest safe power-of-two context (`4096`, `8192`, `16384`, `32768`, `65536`) that fits in remaining memory after weights load.
    - `select_best_model_for_machine(catalog, hardware_profile, category="general")`: picks the single best model for the user's hardware.
  - [ ] `backend/routers/local_models.py` — Expose `GET /api/v1/local-models/hardware` (with `?rescan=true`) and enrich `GET /api/v1/local-models/catalog` with per-model `fit` badges and a top-level `recommended_model_id`.
  - [ ] `frontend/src/routes/models.tsx` — Add the **"Best Model for Your Machine"** hero banner (1-click Download & Run), per-card fit badges (`✅ ~45 tok/s · Fits in 8GB VRAM`), plain-English quantization tooltips, and a confirmation guardrail modal if the user clicks download on a `🚫 Won't Fit` model.
- **Verification / Tests:**
  - [ ] `pytest backend/tests/test_hardware_fit.py` — Test matrix covering 8GB RAM CPU-only laptop, 16GB RAM + 8GB RTX 4060, 32GB RAM + 16GB AMD Radeon (Vulkan), and 64GB Apple Silicon Mac.

### PR 1.2: Managed `llama-server` Native GPU Engine & Dynamic Context (`SPEC-15` Upgrade)
- **Why:** In-process `llama-cpp-python` on Windows/Linux ships CPU-only (`ggml-cpu.dll`), blocks on Python's single-thread executor, and hardcodes `n_ctx = 2048` / `4096` (`local_model_service.py:202-208`). Switching to managed upstream `llama-server` binaries delivers 5–20× GPU speedups, Flash Attention, KV-cache quantization, vision (`--mmproj`), and native GBNF grammar support.
- **Files to Create / Modify:**
  - [ ] **NEW:** `backend/services/llama_runtime_manager.py` — Manages `llama-server` binaries in `~/.contextuai-solo/runtimes/<backend>/`:
    - Detects optimal backend from `hardware.py`: `metal` (macOS arm64), `cuda` (NVIDIA), `vulkan` (AMD / Intel Arc / fallback GPU), or `cpu`.
    - Provides `POST /api/v1/local-models/runtime/install` (SSE download of official pre-built `llama.cpp` release zip for CUDA/Vulkan if not already installed) and health verification.
  - [ ] `backend/services/local_model_service.py` — Refactor to drive the managed `llama-server` subprocess on an internal loopback port (with graceful fallback to in-process `llama-cpp-python` if binary is absent):
    - Replace hardcoded `n_ctx = 4096` (`lines 202-208`) with `model_fit_engine.recommended_n_ctx` (up to `32768`+ when VRAM allows).
    - Pass `--flash-attn`, `--cache-type-k q8_0 --cache-type-v q8_0` (halves KV-cache VRAM usage), and `--n-gpu-layers <auto>`.
    - Implement `POST /api/v1/local-models/{model_id}/preload` (`SPEC-09`) and `POST /api/v1/local-models/{model_id}/benchmark` (runs a 64-token warmup + evaluation and stores measured prompt/generation `tok/s` on the model card).
  - [ ] `frontend/src/components/chat/context-meter.tsx` — Subtle context window usage pill in Chat (`3.2k / 32k tokens`) with a visible warning banner if history is truncated—never silent truncation.
- **Verification / Tests:**
  - [ ] `pytest backend/tests/test_llama_runtime.py` — Verify dynamic `n_ctx` calculation, subprocess lifecycle (spawn, health check, model swap, clean shutdown on sidecar exit), and benchmark endpoint response.

### PR 1.3: Grammar-Locked Local Tool Calling, MCP Client & Loop Circuit Breaker (`SPEC-29`)
- **Why:** Today 30/41 catalog models claim `supports_tools: True`, yet `call_model()` is never passed `tools`, and small local models fail or loop infinitely when asked to call tools without grammar constraints.
- **Files to Create / Modify:**
  - [ ] **NEW:** `backend/services/tool_call_guard.py`:
    - `schema_to_gbnf(tools_schema)`: Compiles the active tool definitions into a strict GBNF grammar / JSON schema constraint passed to `llama-server` / `llama-cpp-python` (`response_format={"type": "json_object", "schema": ...}`).
    - `parse_and_repair_tool_call(raw_text, tools_schema)`: Strips markdown fences, fixes trailing commas/single quotes, validates against Pydantic/JSON schema, and triggers at most **1 structured repair retry** on invalid output.
    - `ToolLoopCircuitBreaker`: Tracks `(tool_name, canonical_args_hash)` per turn; breaks out after 3 identical calls or 8 total calls in a turn and forces a final text synthesis turn.
  - [ ] `backend/services/local_model_service.py`, `backend/routers/ai_chat.py`, & `backend/services/workspace/agent_runner.py` — Wire the multi-turn local tool-execution loop through `tool_call_guard` so local GGUF models can call **MCP servers**, **Knowledge Base search**, **Web Researcher**, and **File tools** in both Chat and Crews.
- **Verification / Tests:**
  - [ ] `pytest backend/tests/test_local_tool_calling.py` — Unit + integration tests proving: (1) malformed JSON tool output is repaired or retried once, (2) a repeating tool call trips the circuit breaker at call #3 and returns a final answer, and (3) a local model completes a 2-step MCP/RAG tool turn end-to-end.

### PR 1.4: Multimodal Vision (`mmproj`) Support for Local GGUF Models
- **Why:** 6 catalog models claim `supports_vision: True` (`model_catalog.py`), but no multimodal projector (`mmproj`) is downloaded or passed to the model.
- **Files to Modify:**
  - [ ] `backend/services/model_catalog.py` — Add `mmproj_repo` and `mmproj_filename` fields to the vision catalog entries (Qwen 2.5/3 VL, Gemma 3/4, Llama 3.2 Vision).
  - [ ] `backend/services/model_manager.py` — Automatically download the paired `mmproj-*.gguf` file alongside the main `.gguf` when downloading a vision model.
  - [ ] `backend/services/local_model_service.py` & `backend/routers/ai_chat.py` — Pass `--mmproj <path>` when loading a vision model and forward base64 image attachments in OpenAI vision content array format.
  - [ ] `frontend/src/routes/chat.tsx` — Enable image drag-and-drop / paste attachment button when a vision-capable local or cloud model is selected.
- **Verification / Tests:**
  - [ ] `pytest backend/tests/test_local_vision.py` — Verify downloader fetches paired `mmproj` file and `local_model_service` formats multimodal messages properly.

### PR 1.5: Glass-Box Privacy Shield & Airplane Lock (`SPEC-28`)
- **Why:** Users in 2027 don't trust "we don't collect telemetry" claims after other local tools were caught phoning home. Proving zero egress visually inside the app is a massive trust moat for both Lite and Solo.
- **Files to Create / Modify:**
  - [ ] **NEW:** `backend/services/net_guard.py` — Central outbound HTTP interceptor/client wrapper used by `model_manager.py`, `cloud_provider_service.py`, `channel_service.py`, and `mcp` clients.
    - Logs every non-loopback request into a ring buffer (`timestamp`, `host`, `method`, `purpose`, `bytes_sent`, `blocked`).
    - Enforces `airplane_lock: bool`: when enabled, raises `EgressBlockedError` before any DNS/socket connection outside `127.0.0.1` / `localhost`.
  - [ ] **NEW:** `backend/routers/privacy.py` — `GET /api/v1/privacy/ledger`, `POST /api/v1/privacy/airplane-lock`, `GET /api/v1/privacy/manifest`.
  - [ ] **NEW:** `frontend/src/components/privacy/privacy-shield.tsx` — Persistent status-bar shield badge (`🛡️ 0 External Connections` in green, or `✈️ Airplane Lock Active`) that opens the live Network Activity & Privacy Manifest drawer.
- **Verification / Tests:**
  - [ ] `pytest backend/tests/test_privacy_shield.py` — Assert that local chat + local folder RAG + local crew run logs `0` external requests, and that enabling Airplane Lock blocks cloud/channel calls with a clean error message.

### PR 1.6: Living Model Catalog — OTA Manifest Sync, Live HuggingFace Search & GGUF Header Inspector (`SPEC-34`)
- **Why:** Today `LOCAL_MODEL_CATALOG` (`backend/services/model_catalog.py`) is a static Python list compiled inside the desktop installer—users never see new models unless they reinstall the app. Worse, `CustomModelInput` (`routes/models.tsx:300`) forces users to manually type exact `.gguf` filenames, and `local_model_seeder.py:158` (`_unknown_gguf_to_model_doc`) hardcodes custom models to `context_window: 4096` and `supports_function_calling: False`.
- **4-Layer Solution:**
  1. **Over-the-Air (OTA) Curated Catalog Sync (No App Update Required):**
     - [ ] Extract `LOCAL_MODEL_CATALOG` baseline to `backend/catalog/models.json` (bundled for 100% offline/Airplane mode) and host the live canonical file in the repo's GitHub raw/releases CDN.
     - [ ] Add `POST /api/v1/local-models/catalog/refresh` in `backend/services/model_catalog.py`: fetches remote `models.json` with ETag caching into `~/.contextuai-solo/data/catalog_cache.json`, validates schema, and merges new models (`is_new: True` badge) over the bundled catalog. Respects Airplane Lock (`SPEC-28`).
  2. **Live HuggingFace Hub Search + Trending Feed + Auto-Quant File Picker:**
     - [ ] **NEW:** `backend/services/hf_hub_discovery.py` — Queries HuggingFace API (`https://huggingface.co/api/models?filter=gguf&sort=trending|downloads|lastModified&search=...`), with a "Verified Quantizers" filter (`unsloth`, `bartowski`, `Qwen`, `ggml-org`, `lmstudio-community`).
     - [ ] Add `GET /api/v1/local-models/hf-repo-files?repo_id=<org/repo>`: fetches the repo's `.gguf` file tree + byte sizes, passes every `.gguf` quant variant through `model_fit_engine.py` (`SPEC-27`), and auto-highlights the best quant for the user's GPU/RAM—replacing the manual filename text box in `routes/models.tsx:300` with a 1-click dropdown.
  3. **GGUF Binary Header Inspector (Zero-Config Metadata for Any Model):**
     - [ ] **NEW:** `backend/services/gguf_inspector.py` — Pure-Python reader that parses the first 64KB of any local `.gguf` file (or via HTTP `Range` header before download) to extract `general.architecture`, `<arch>.context_length`, `tokenizer.chat_template` (auto-detecting tool-calling support if `<tool_call>` / `tools` is present in the Jinja template), quantization, and paired `mmproj` vision files.
     - [ ] Wire `gguf_inspector.py` into `local_model_seeder.py::_unknown_gguf_to_model_doc()` so *any* downloaded or imported `.gguf` gets its real 32K–256K context window and tool-calling capabilities enabled automatically.
  4. **Automated GitHub Action "Catalog Radar":**
     - [ ] **NEW:** `.github/workflows/catalog-radar.yml` — Weekly scheduled workflow that `HEAD`-checks every catalog URL (catching gated/moved repos automatically) and opens a PR when top quantizers publish new trending GGUF families.
- **Verification / Tests:**
  - [ ] `pytest backend/tests/test_living_catalog.py` — Verify OTA JSON merge + offline fallback, HF repo `.gguf` sibling resolution + fit badge annotation, and GGUF binary header extraction of `context_length` and `chat_template`.

---

## TRACK 2: Build & Ship the Lite Edition (*"Vesper"* / *"Lumen"* by ContextuAI) (Weeks 6–8)

> **Goal:** Package the upgraded local engine into an ultra-clean, fast, attractive standalone desktop app for running GGUF models, local Folder RAG, `/v1` IDE autocomplete, and local MCP tools—with a 1-click bridge to unlock full ContextuAI Solo.

### PR 2.1: Edition Configuration & The 4-Tab Lite UI Shell (`SPEC-33`)
- **Files to Create / Modify:**
  - [ ] **NEW:** `frontend/src/config/edition.ts` — Reads `import.meta.env.VITE_APP_EDITION` (`"lite" | "solo"`, plus a localStorage override `contextuai.edition.unlocked` when a user upgrades to Solo in-place). Exports brand metadata (`appName`: `"Vesper"` / `"Lumen"`, `tagline`, allowed routes, feature flags).
  - [ ] `backend/settings.py` — Add `EDITION: str = os.getenv("CONTEXTUAI_EDITION", "solo")`. In `"lite"` mode, skip background pollers (`RedditPoller`, scheduled automations) and skip seeding the 113-agent markdown library on first boot for instant <1s startup.
  - [ ] **NEW:** `frontend/src/components/navigation/desktop-sidebar-lite.tsx` — Clean 4-item sidebar:
    1. **Chat & Folder RAG (`/chat`)** — Fast local chat + model preload indicator (`● Ready` / `48 tok/s`) + 1-click **"Attach Local Folder"** (inline wrapper around `personal_docs_service.py` so users can drop any folder and chat with citations immediately) + up to 3 local MCP servers.
    2. **Model Studio (`/models`)** — Hardware X-Ray header, *"Best for Your Machine"* 1-click card, curated GGUF catalog with fit badges, custom `.gguf` drag-and-drop importer, and 1-click speed benchmark.
    3. **Local Server (`/server`)** — New developer-focused control panel for `http://localhost:18741/v1` and MCP Server mode:
       - Live request stream (method, model, prompt tokens, completion tokens, `tok/s`, latency).
       - Toggle for Fill-in-the-Middle (`/v1/completions` FIM) code autocomplete.
       - One-click copy config snippets for **Cursor, Continue.dev, Claude Code, Aider, and OpenAI Python/TS SDKs**.
    4. **Privacy Shield & Settings (`/privacy`, `/settings`)** — Live network egress monitor, Airplane Lock switch, GPU runtime selector (`CUDA` / `Vulkan` / `Metal` / `CPU`), and HuggingFace token input.
  - [ ] **NEW:** `frontend/src/routes/local-server.tsx` — The `/server` route described above (available in both Lite and Solo).
- **Verification / Tests:**
  - [ ] Playwright E2E test `frontend/tests/e2e/lite-edition.spec.ts` — Verifies the 4-tab navigation, Hardware X-Ray card, Local Server inspector page, and Privacy Shield drawer when `VITE_APP_EDITION=lite`.

### PR 2.2: Seamless "Graduate to ContextuAI Solo" In-App Unlock Flow
- **Why:** Lite's strategic purpose is to win massive top-of-funnel adoption among local AI users and convert power users into ContextuAI Solo (and Enterprise).
- **Files to Create / Modify:**
  - [ ] **NEW:** `frontend/src/components/shell/upgrade-to-solo-modal.tsx` — Triggered from a subtle `"⚡ Unlock Agent Crews & 96 Business Agents"` card at the bottom of the Lite sidebar:
    - Shows what unlocks: **96 Business Agents**, **Multi-Agent Crews**, **10 Social & Distribution Channels (Telegram, Reddit, Discord, LinkedIn, X)**, **Human Approvals Queue**, and **Coder Mode**.
    - Explains that all downloaded GGUF models, chats, and indexed folders stay right where they are (`~/.contextuai-solo/`).
    - Clicking **"Switch to ContextuAI Solo"** calls `POST /api/v1/desktop/unlock-solo` (seeds the 96-agent library & blueprints into SQLite and flips the UI shell to full Solo mode immediately without reinstalling).
- **Verification / Tests:**
  - [ ] E2E test verifying that clicking "Switch to ContextuAI Solo" seeds the agent library, switches the sidebar from the 4-tab Lite layout to the 11-tab Solo layout, and preserves all installed GGUF models.

### PR 2.3: Lite Tauri Build Config, Code Signing & Release Pipeline
- **Files to Create / Modify:**
  - [ ] **NEW:** `frontend/src-tauri/tauri.lite.conf.json` — Separate Tauri configuration for the Lite build (`productName`, window title, bundle identifier, icons) invoked via `npm run tauri build -- --config src-tauri/tauri.lite.conf.json`.
  - [ ] **NEW:** `LICENSE-LITE` — Pure **MIT** (or **Apache-2.0**) license covering the Lite build target so it can be posted to `r/LocalLLaMA`, `r/selfhosted`, Hacker News (`Show HN`), Winget, and Homebrew without Commons Clause friction.
  - [ ] **NEW:** `.github/workflows/release-lite.yml` — Automated cross-platform build producing signed installers for Windows, macOS (Universal/arm64), and Linux alongside `release.yml`.

---

## TRACK 3: ContextuAI Solo 2027 Workforce Upgrades (Weeks 9–14 — Post-Lite Launch)

> **Goal:** With the local GGUF + tool-calling engine rock-solid, complete Solo's evolution *"From Agents to Colleagues"* (`ROADMAP-2026H2-2027.md`).

### PR 3.1: Wire Unified Memory Auto-Recall & Auto-Extraction (`SPEC-14` PR-B & PR-C)
- **Why:** `memory_service.py` (PR-A) already implements semantic search and `format_memory_block()`, but nothing in `ai_chat.py` or `agent_runner.py` calls it yet.
- **Files to Modify:**
  - [ ] `backend/routers/ai_chat.py` & `backend/services/workspace/agent_runner.py` — When `memory_settings.enabled` and the surface toggle (`chat_enabled` / `crews_enabled`) are true, query `memory_service.search(prompt, scope=...)` and prepend `format_memory_block()` to the system prompt.
  - [ ] `backend/services/memory_extractor.py` — Background post-turn extraction of durable user facts/preferences (`confidence >= threshold`), with a toast/review queue in `/memory` for low-confidence facts.
- **Verification / Tests:**
  - [ ] `pytest backend/tests/test_memory_recall.py` — Save a fact ("Our standard SaaS pricing is $49/seat"), ask a question in a fresh chat session, and assert the fact is injected into the prompt and cited.

### PR 3.2: Crew Dry-Run Mode (`SPEC-10`) & KB Freshness Badges (`SPEC-11`)
- **Files to Modify:**
  - [ ] `backend/services/crew_orchestrator.py` & `backend/routers/crews.py` — Add `dry_run: bool = False` to crew execution; when `True`, execute all agents and capture outbound channel payloads into a preview result without posting to live Telegram/Reddit/LinkedIn APIs.
  - [ ] `frontend/src/components/crews/crew-builder.tsx` — Add **"Dry Run Test"** button in Step 7 (Review & Create) and on the Crew detail page.
  - [ ] `backend/services/personal_docs_service.py` & `frontend/src/routes/knowledge.tsx` — Add quick mtime diff check (`"Synced 2h ago"` vs `"⚠ Stale — 4 files changed"`) and 1-clickKB auto-suggest banner in Chat when a prompt cosine-matches a KB centroid.

### PR 3.3: Hybrid RAG (SQLite FTS5 + Dense Vectors) & Structure-Aware Chunking (`SPEC-30`)
- **Files to Modify:**
  - [ ] `backend/services/rag_service.py` — Add a SQLite FTS5 virtual table (`kb_chunks_fts`) alongside the existing 384-dim MiniLM dense embeddings; combine BM25 rank + cosine similarity via Reciprocal Rank Fusion (RRF) so exact part numbers, names, and tax codes never miss.
  - [ ] Improve PDF/DOCX/Markdown chunker to respect headings and markdown tables, strip repeated headers/footers, and return a `"Retrieved Chunks"` diagnostic drawer in Chat citations.

### PR 3.4: Pulse Proactive Morning Briefing (`SPEC-16`) & Digital Workers (`SPEC-18`)
- **Files to Create / Modify:**
  - [ ] **NEW:** `backend/services/pulse_service.py` & `frontend/src/routes/pulse.tsx` — Aggregates overnight channel messages, folder-mapping changes, and scheduled crew outputs into a single morning **Pulse Card Stack** (*"3 items need approval, 2 tasks completed, 1 trend detected"*).
  - [ ] **NEW:** `backend/services/digital_worker_service.py` & `frontend/src/routes/workers.tsx` — Packages an agent team + KB + channel binding + schedule into 5 pre-built **Digital Workers** (*Social Media Manager, Research Analyst, Customer Support Rep, Content Studio, Bookkeeper-Lite*) with a 3-question onboarding interview and KPI card.

---

## Summary Checklist for Founder Approval (Solo & Lite Repo)

| Phase | PRs | Est. Time | Deliverable |
|---|---|---|---|
| **Track 0: Baseline & Security** | PR 0.1 – PR 0.3 | ~1 Week | Working downloader, ungated Gemma, HF Token, custom `.gguf` import, Sidecar Auth/CORS lockdown, `/v1` lock fix, `pytest` in CI |
| **Track 1: Next-Gen Local Engine** | PR 1.1 – PR 1.6 | ~4 Weeks | Hardware X-Ray + Fit Badges (`SPEC-27`), Managed `llama-server` GPU binaries (CUDA/Vulkan/Metal), Dynamic Context, Grammar-Locked Tool Calling (`SPEC-29`), Vision `mmproj`, Privacy Shield (`SPEC-28`), Living Catalog + Live HF Search + GGUF Inspector (`SPEC-34`) |
| **Track 2: Lite Edition Launch** | PR 2.1 – PR 2.3 | ~2.5 Weeks | **Vesper / Lumen** 4-tab Lite build target, `/server` live inspector, 1-click "Graduate to Solo" unlock, MIT license, multi-OS release workflow |
| **Track 3: Solo 2027 Workforce** | PR 3.1 – PR 3.4 | ~4 Weeks | Memory Auto-Recall (`SPEC-14`), Crew Dry-Run (`SPEC-10`), Hybrid FTS5 RAG (`SPEC-30`), Pulse Briefing (`SPEC-16`), Digital Workers (`SPEC-18`) |
