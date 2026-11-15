# SPEC-33 — ContextuAI Lite Edition ("Vesper" / "Lumen") Build Target & 4-Tab Local Studio

- **Links:** [TODO-LITE-AND-SOLO-2027.md](../../../TODO-LITE-AND-SOLO-2027.md) · depends on SPEC-01 (sidecar auth), SPEC-15 (GPU runtime), SPEC-27 (hardware fit), SPEC-28 (verifiable privacy), SPEC-29 (local tool calling)
- **Priority:** P0 (2027 Launch Wedge) · **Effort:** M (2–3 weeks after Track 1 local engine lands)
- **Review status:** 🟡 pending founder review
- **Type:** product & build-target spec

---

## 1. Goal

Ship an attractive, ultra-fast, zero-config desktop application for running local GGUF models, local Folder RAG, `/v1` IDE completions (FIM), and grammar-locked local MCP tools—built from the `contextuai-solo` repository via an edition flag (`VITE_APP_EDITION=lite` / `CONTEXTUAI_EDITION=lite`), released under a permissive open-source license (MIT / Apache-2.0), with a 1-click in-app bridge to unlock full **ContextuAI Solo**.

## 2. Brand & Naming Options (Founder Decision Gate)

- **Option A (Recommended for Developer + Prosumer Polish):** **Vesper** *(by ContextuAI)* — *"Quiet, sovereign intelligence on your metal."*
- **Option B (Recommended for Glass-Box Privacy Positioning):** **Lumen** *(by ContextuAI)* — *"Glass-box local AI. Fast on your GPU, transparent to the byte."*
- **Option C (Hardware / Craft Angle):** **Kiln** or **Kestrel** *(by ContextuAI)* — *"Fire up local GGUF models at full GPU speed."*

## 3. Architecture: Single Repo, Dual Build Target

1. **Frontend Edition Config (`frontend/src/config/edition.ts`):**
   - Reads `import.meta.env.VITE_APP_EDITION` (`"lite" | "solo"`), overridable at runtime via `localStorage.getItem("contextuai.edition.unlocked") === "solo"` when the user clicks **"Switch to ContextuAI Solo"** inside the app.
2. **Backend Edition Config (`backend/settings.py`):**
   - Reads `CONTEXTUAI_EDITION` (`"lite" | "solo"`).
   - In `"lite"` mode:
     - Skips starting background social channel pollers (`RedditPoller`, scheduled automations).
     - Skips seeding the 113-agent markdown library and blueprints until the user triggers `POST /api/v1/desktop/unlock-solo`.
     - Uses the exact same `~/.contextuai-solo/models/` and `~/.contextuai-solo/data/contextuai.db` paths so upgrading to Solo requires **zero model re-downloads or DB migrations**.
3. **Tauri Build Config (`frontend/src-tauri/tauri.lite.conf.json`):**
   - Overrides `productName`, `identifier`, window title, and icon set for the Lite installer while sharing the Rust sidecar lifecycle manager.

## 4. The 4-Tab Lite UI Surface (`desktop-sidebar-lite.tsx`)

When running in Lite mode, the 11-item Solo sidebar is replaced by a focused 4-item navigation rail:

1. **Chat & Folder RAG (`/chat`):**
   - Streaming local chat with `<think>` collapsible blocks, vision image attachments (`mmproj`), and context-window usage pill (`SPEC-15`).
   - Inline **"Attach Local Folder"** button (wraps `personal_docs_service.py` for 1 active folder KB with cited `[1]`, `[2]` answers).
   - Up to 3 local MCP servers with grammar-locked tool calling (`SPEC-29`).
2. **Model Studio (`/models`):**
   - Hardware X-Ray header + **"Best Model for Your Machine"** 1-click recommendation card (`SPEC-27`).
   - Per-quant fit badges (`✅ Runs Fast in GPU · ~48 tok/s`, `⚠️ Partial Offload`, `🚫 Won't Fit`), plain-English quant slider, custom `.gguf` drag-and-drop importer, and 5-second speed benchmark.
3. **Local Server (`/server`):**
   - Dedicated developer control panel for `http://localhost:18741/v1` and MCP Server mode.
   - Live request inspector (model, prompt/completion tokens, `tok/s`, latency).
   - Fill-in-the-Middle (`/v1/completions` FIM) autocomplete toggle.
   - 1-click copy config snippets for **Cursor, Continue.dev, Claude Code, and Aider**.
4. **Privacy Shield & Settings (`/privacy`, `/settings`):**
   - Live outbound network activity ledger proving `0 external bytes` during local runs (`SPEC-28`).
   - Hard **Airplane Lock** toggle blocking all non-loopback sockets.
   - GPU backend selector (`CUDA` / `Vulkan` / `Metal` / `CPU`) and optional HuggingFace Token (`SPEC-08`).

## 5. In-App "Graduate to ContextuAI Solo" Flow

- A sleek bottom sidebar card (**"⚡ Unlock 96 Business Agents, Multi-Agent Crews & Social Auto-Reply"**) opens `upgrade-to-solo-modal.tsx`.
- Clicking **"Activate ContextuAI Solo"** calls `POST /api/v1/desktop/unlock-solo`, which seeds the 96-agent library and blueprints into SQLite, sets the edition state to `"solo"`, and swaps the sidebar to the full 11-item Solo workspace immediately—preserving all downloaded GGUF models, chats, and indexed folders.

## 6. Acceptance Criteria

- Building with `VITE_APP_EDITION=lite` launches into the 4-tab Lite shell in `<1.5s` with zero background social pollers running.
- Hardware X-Ray, Model Studio download/import, Folder RAG, `/v1` + FIM server, and Privacy Shield Airplane Lock all pass E2E verification.
- Clicking "Activate ContextuAI Solo" transitions the app to full Solo mode without re-downloading any GGUF models.
