# ContextuAI Solo — Bundled Local AI Plan

## Overview

Add on-demand local AI to ContextuAI Solo. The installer stays small (~120 MB) by bundling llama-cpp-python bindings + the all-MiniLM-L6-v2 embedding model (~23 MB). Chat models (700 MB–2 GB) download on demand when the user picks "Local AI" in the wizard or settings.

Single installer. No tiers.

---

## What Gets Bundled vs Downloaded

| Component | In Installer | On Demand |
|-----------|-------------|-----------|
| Tauri shell + React frontend | Yes | — |
| FastAPI sidecar (PyInstaller) | Yes | — |
| llama-cpp-python bindings + DLLs | Yes (~20-40 MB) | — |
| all-MiniLM-L6-v2 embedding (ONNX) | Yes (~23 MB) | — |
| Chat model (GGUF) | — | User picks in wizard/settings |

---

## Chat Models (User Picks via Dropdown)

| Model | Download | RAM | Tool Calling | Quality | License |
|-------|----------|-----|--------------|---------|---------|
| Gemma 3 1B (Q4_K_M) | ~700 MB | ~2 GB | Limited | Basic chat | Apache 2.0 |
| Qwen 2.5 1.5B (Q4_K_M) | ~1 GB | ~3 GB | Yes | Good | Apache 2.0 |
| Qwen 2.5 3B (Q4_K_M) | ~2 GB | ~4 GB | Yes | Best at size | Apache 2.0 |

**Default: Qwen 2.5 1.5B** — best balance of quality, tool calling, and resources.

All GGUF Q4_K_M, CPU inference via llama-cpp-python.

---

## Embedding Model (Bundled Silently)

**all-MiniLM-L6-v2** (~23 MB, ONNX) — bundled in PyInstaller sidecar, lazy-loaded.

- 384-dim vectors, no user prompt needed
- Future use: RAG, agent memory, semantic search, chat history search

---

## Why llama-cpp-python (Not Embedded Ollama)

| Factor | llama-cpp-python | Embedded Ollama |
|--------|-----------------|-----------------|
| Size | ~20-40 MB | ~200 MB |
| Integration | In-process (same sidecar) | Separate process |
| Bundling | Standard pip package | Must bundle binary |

Runs inside the existing FastAPI sidecar — no extra process management.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Tauri Shell  (frontend/src-tauri/src/)               │
│  ├─ sidecar.rs — spawns backend, passes MODELS_DIR   │
│  └─ commands.rs — IPC handlers                        │
└────────────┬─────────────────────────────────────────┘
             │ spawns
             ▼
┌──────────────────────────────────────────────────────┐
│  FastAPI Sidecar  (backend/)                          │
│                                                       │
│  routers/ai_chat.py  (existing, line ~383)            │
│  ├─ LocalModelService.is_local_model()  → NEW check  │
│  ├─ OllamaService.is_ollama_model()     → existing   │
│  └─ else → Bedrock/Strands agent        → existing   │
│                                                       │
│  services/local_model_service.py  (NEW)               │
│  ├─ llama-cpp-python GGUF inference                   │
│  ├─ Same call_model() interface as OllamaService      │
│  ├─ Streaming async generator (SSE chunks)            │
│  ├─ Tool calling via create_chat_completion(tools=..) │
│  └─ Thread pool executor for CPU-bound inference      │
│                                                       │
│  services/embedding_service.py  (NEW)                 │
│  ├─ all-MiniLM-L6-v2 ONNX (bundled)                 │
│  └─ embed(text) → 384-dim vector (internal only)     │
│                                                       │
│  routers/local_models.py  (NEW)                       │
│  ├─ GET  /available       → model catalog             │
│  ├─ GET  /downloaded      → downloaded .gguf list     │
│  ├─ GET  /status          → loaded model info + RAM   │
│  ├─ POST /download        → start HF download         │
│  ├─ GET  /download/progress → SSE progress stream     │
│  ├─ POST /load            → load model into RAM       │
│  ├─ POST /unload          → free RAM                  │
│  └─ DELETE /{model_id}    → delete .gguf file         │
└──────────────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────┐
│  ~/.contextuai-solo/models/                           │
│  ├─ chat/          (downloaded GGUFs)                 │
│  └─ embedding/     (bundled all-MiniLM-L6-v2)        │
└──────────────────────────────────────────────────────┘
```

---

## User Experience

### Wizard Step 2 — Provider Selection

The existing wizard (wizard.tsx, lines 32-109) shows provider cards: Anthropic, OpenAI, Google, Ollama, Bedrock. Add **"Local AI"** as a new provider card at the top.

```
┌──────────────────────────────────────────────────────┐
│  Step 2: Choose your AI provider                      │
│                                                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │  Local AI  ·  Free & Private                    │ │
│  │  Run AI on your computer. No API keys needed.   │ │
│  │                                                  │ │
│  │  Model:  [ Qwen 2.5 1.5B — 1 GB ▾ ]           │ │
│  │          ○ Gemma 3 1B — 700 MB (basic)          │ │
│  │          ● Qwen 2.5 1.5B — 1 GB (recommended)  │ │
│  │          ○ Qwen 2.5 3B — 2 GB (best quality)   │ │
│  │                                                  │ │
│  │  [ Download & Continue ]                         │ │
│  │                                                  │ │
│  │  ████████████░░░░░  67%  670 MB  ~2 min left    │ │
│  └─────────────────────────────────────────────────┘ │
│                                                       │
│  ── or use a cloud provider ──                        │
│                                                       │
│  [ Anthropic ] [ OpenAI ] [ Google ] [ Ollama ] ...   │
└──────────────────────────────────────────────────────┘
```

### Settings — Local Models Section

In settings.tsx AI Providers tab (~line 107), add a "Local Models" card:
- Show downloaded models with loaded/unloaded status
- Download more from dropdown
- Load / Unload / Delete buttons
- RAM usage display

### Chat — Auto-select Local Model

In chat.tsx (~line 63-75), if provider is "local", auto-select the local model and show a "Running locally" badge.

---

## Implementation Plan

### Phase 1: Backend — Local Inference

**1.1 — Create `backend/services/local_model_service.py`**

Follow the same pattern as `backend/services/ollama_service.py` (class at line 20, `call_model()` at line 50, `_stream_response()` at line 127):

```python
class LocalModelService:
    MODELS_DIR: str                    # from MODELS_DIR env var
    _llm: Llama | None = None         # loaded llama-cpp-python instance
    _loaded_model_id: str | None = None

    @staticmethod
    def is_local_model(model_config: dict) -> bool:
        """provider == 'local' or metadata.runtime == 'local'"""

    async def call_model(
        self, prompt, model_id, conversation_history,
        system_prompt, max_tokens, temperature, stream, tools
    ) -> dict | AsyncGenerator:
        """Same signature + return format as OllamaService.call_model()"""

    def _load_model(self, model_path: str) -> None:
        """Llama(model_path, n_ctx=4096, n_threads=os.cpu_count())"""

    def unload_model(self) -> None:
    def get_status(self) -> dict:
```

- CPU inference in `loop.run_in_executor()` (thread pool)
- Stream chunks match OllamaService format: `{"chunk": text, "model_id": id, "is_final": bool, "status": "streaming"|"complete"}`
- Tool calling via `create_chat_completion(tools=...)`

**1.2 — Create `backend/services/embedding_service.py`**

```python
class EmbeddingService:
    _session: ort.InferenceSession | None = None

    def embed(self, text: str) -> list[float]:       # 384-dim
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
```

- ONNX path: `sys._MEIPASS/models/embedding/` (PyInstaller) or `MODELS_DIR/embedding/`
- Internal service only — no API endpoint yet

**1.3 — Create `backend/routers/local_models.py`**

Hardcoded model catalog (no DB):

```python
AVAILABLE_MODELS = [
    {"id": "gemma-3-1b", "name": "Gemma 3 1B", "file": "gemma-3-1b-it-Q4_K_M.gguf",
     "hf_repo": "bartowski/gemma-3-1b-it-GGUF", "hf_file": "gemma-3-1b-it-Q4_K_M.gguf",
     "size_bytes": 734_003_200, "ram_gb": 2, "supports_tools": False, "tier": "basic"},
    {"id": "qwen2.5-1.5b", "name": "Qwen 2.5 1.5B", "file": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
     "hf_repo": "Qwen/Qwen2.5-1.5B-Instruct-GGUF", "hf_file": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
     "size_bytes": 1_073_741_824, "ram_gb": 3, "supports_tools": True, "tier": "recommended"},
    {"id": "qwen2.5-3b", "name": "Qwen 2.5 3B", "file": "qwen2.5-3b-instruct-q4_k_m.gguf",
     "hf_repo": "Qwen/Qwen2.5-3B-Instruct-GGUF", "hf_file": "qwen2.5-3b-instruct-q4_k_m.gguf",
     "size_bytes": 2_147_483_648, "ram_gb": 4, "supports_tools": True, "tier": "best"},
]
```

Download uses `huggingface_hub.hf_hub_download()` — built-in resume + progress callback. Progress stored in-memory dict, polled by SSE endpoint.

**1.4 — Modify `backend/routers/ai_chat.py` (line ~381-383)**

Insert local model check before the existing Ollama check:

```python
# Line ~381 — NEW: check local model BEFORE Ollama
from services.local_model_service import LocalModelService, local_model_service
if model_config and LocalModelService.is_local_model(model_config):
    logger.info(f"🖥️ ROUTING: Local model detected ({model_config.get('name')}), using LocalModelService")
    # ... same streaming/non-streaming pattern as Ollama block below

# Line ~383 — existing Ollama check
from services.ollama_service import OllamaService, ollama_service
if model_config and OllamaService.is_ollama_model(model_config):
```

**1.5 — Modify `backend/app.py`**

- Register `local_models_router` (alongside existing routers at ~line 72)
- On startup (~line 270): scan `MODELS_DIR/chat/*.gguf`, seed matching model configs with `provider: "local"` into the models collection

**1.6 — Modify `backend/requirements.txt`**

```
llama-cpp-python>=0.3.0
onnxruntime>=1.17.0
huggingface-hub>=0.20.0
tokenizers>=0.15.0
```

### Phase 2: Frontend — Wizard & UI

**2.1 — Create `frontend/src/lib/api/local-models-client.ts`**

Uses the existing `apiRequest()` from `transport.ts`:

```typescript
export interface LocalModel {
  id: string; name: string; file: string;
  size_bytes: number; ram_gb: number;
  supports_tools: boolean; tier: "basic" | "recommended" | "best";
  downloaded: boolean; loaded: boolean;
}

export interface DownloadProgress {
  model_id: string; percent: number;
  bytes_downloaded: number; bytes_total: number;
  status: "downloading" | "verifying" | "complete" | "error";
}

export async function getAvailableModels(): Promise<LocalModel[]>
export async function getDownloadedModels(): Promise<LocalModel[]>
export async function getModelStatus(): Promise<{loaded_model: string | null, ram_mb: number}>
export async function startDownload(modelId: string): Promise<void>
export async function loadModel(modelId: string): Promise<void>
export async function unloadModel(): Promise<void>
export async function deleteModel(modelId: string): Promise<void>
```

**2.2 — Modify `frontend/src/routes/wizard.tsx`**

Add `local` to the providers array (line 32-109) at index 0:

```typescript
{ id: "local", name: "Local AI",
  description: "Free & private. Runs on your computer.",
  icon: Monitor, models: [],  // filled from GET /local-models/available
  requiresKey: false, color: "from-emerald-500 to-teal-500" }
```

When `selectedProvider === "local"`:
- Render dropdown with 3 model options (size + quality label)
- Pre-select "recommended" (Qwen 2.5 1.5B)
- "Download & Continue" → POST download → SSE progress bar → auto-load → advance wizard
- localStorage: `contextuai-solo-provider` = `"local"`, `contextuai-solo-model` = model_id

**2.3 — Modify `frontend/src/routes/settings.tsx`**

Add "Local Models" card in AI Providers tab (~line 107):
- Downloaded models list with Load/Unload/Delete
- Download additional models dropdown
- RAM usage display from GET /status

**2.4 — Modify `frontend/src/routes/chat.tsx`**

- Auto-select local model when provider is "local" (~line 63-75)
- "Running locally" badge next to model name

### Phase 3: Build Pipeline

**3.1 — Modify `backend/contextuai-solo-backend.spec`**

Add to hiddenimports (line 4):
```python
hiddenimports += ['llama_cpp', 'onnxruntime', 'huggingface_hub', 'tokenizers']
```

Add to datas (line 15):
```python
datas=[('../agent-library', 'agent-library'), ('../models/embedding/all-MiniLM-L6-v2', 'models/embedding/all-MiniLM-L6-v2')],
```

Add native library collection (after line 2):
```python
from PyInstaller.utils.hooks import collect_submodules, collect_dynamic_libs
binaries_extra = collect_dynamic_libs('llama_cpp') + collect_dynamic_libs('onnxruntime')
```

Then on line 14: `binaries=binaries_extra,`

**3.2 — Modify `frontend/src-tauri/src/sidecar.rs`**

Pass `MODELS_DIR` env var when spawning sidecar (after line 70):

```rust
let models_dir = app_handle
    .path()
    .app_data_dir()
    .map_err(|e| format!("Failed to get app data dir: {}", e))?
    .join("models");
std::fs::create_dir_all(&models_dir)
    .map_err(|e| format!("Failed to create models dir: {}", e))?;
cmd.env("MODELS_DIR", &models_dir);
```

Models live in `~/.contextuai-solo/models/` and survive app updates.

**3.3 — Modify `.gitignore`**

```
models/embedding/
models/chat/
*.gguf
```

### Phase 4: Testing & Polish

- [ ] E2E: wizard → Local AI → download mock → chat works
- [ ] E2E: switch local ↔ cloud mid-conversation
- [ ] E2E: settings → download model → load → works
- [ ] RAM detection: warn if system RAM < model requirement
- [ ] SHA-256 verification after download
- [ ] tok/s indicator in chat for local models
- [ ] Download resume (huggingface_hub handles natively)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| llama-cpp-python DLLs missing after PyInstaller | `collect_dynamic_libs('llama_cpp')`. Test build early. Fallback: ship .dll alongside sidecar |
| CPU speed 5-15 tok/s feels slow | Set expectations in UI. Streaming masks latency. "Add cloud key for faster responses" hint |
| 700 MB–2 GB download on slow connections | Progress bar + cancel. Resume support (huggingface_hub). Background option |
| High RAM usage (2-4 GB) | Detect available RAM. Recommend tier accordingly. Unload button |
| Small models fail complex tool calling | Simplified tool schemas for local. Fallback to plain chat |
| GGUF corruption | SHA-256 check post-download. Re-download in settings |
| Windows needs vcruntime140.dll | Ship with NSIS installer (standard) |

---

## HuggingFace Sources

| Model | Repo | File | Size |
|-------|------|------|------|
| Gemma 3 1B Q4 | `google/gemma-3-1b-it-qat-q4_0-gguf` | `gemma-3-1b-it-q4_0.gguf` | ~700 MB |
| Qwen 2.5 1.5B Q4 | `Qwen/Qwen2.5-1.5B-Instruct-GGUF` | `qwen2.5-1.5b-instruct-q4_k_m.gguf` | ~1 GB |
| Qwen 2.5 3B Q4 | `Qwen/Qwen2.5-3B-Instruct-GGUF` | `qwen2.5-3b-instruct-q4_k_m.gguf` | ~2 GB |
| all-MiniLM-L6-v2 | `sentence-transformers/all-MiniLM-L6-v2` | ONNX export | ~23 MB |

---

## Success Criteria

1. Single installer under ~120 MB
2. User picks "Local AI" in wizard → downloads model → chats within 5 minutes
3. Embedding model bundled silently — zero user interaction
4. No API keys or internet needed after model download
5. Tool calling works for Crews/Workspace with Qwen 2.5 1.5B+
6. Clean upgrade: add cloud API key anytime in settings
7. Multiple models downloadable, switchable in settings
