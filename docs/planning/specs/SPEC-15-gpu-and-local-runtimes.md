# SPEC-15 — GPU Acceleration + Local-Runtime Plurality

- **Links:** ROADMAP F-2 (Q3 2026) · trend vector #5 (on-device AI on any GPU)
- **Priority:** P1 · **Effort:** M
- **Review status:** ⬜ pending review
- **Type:** roadmap spec

## 1. Goal

Stop leaving 5–20× inference speed on the table. Solo uses the user's GPU when present, and treats other local runtimes the user already has (Ollama, LM Studio, Windows Foundry Local) as first-class backends instead of competitors.

## 2. v1 Scope

1. **GPU builds of llama-cpp-python:** ship Vulkan (broadest: AMD/Intel/NVIDIA) and CUDA wheels as optional downloads — not in the base installer (keeps it ~500 MB). Settings → AI Providers → "Local acceleration" card: detect GPU (extend `model_manager._detect_gpu` beyond nvidia-smi: Vulkan enumeration, DXGI on Windows), offer one-click "Enable GPU acceleration" that downloads the matching runtime into the app data dir and hot-swaps the backend (sidecar restart acceptable).
2. **`n_gpu_layers` auto-config:** size layers to VRAM with a safety margin; fall back to CPU cleanly on OOM (llama.cpp errors must surface as a friendly "model too large for GPU, running on CPU" not a crash).
3. **In-app benchmark:** "Test this model" button → tok/s prompt+gen on a fixed prompt; show on the model card ("Your machine: 31 tok/s"). Stores results so the catalog can badge models as Fast/OK/Slow *for this machine* instead of generic speed tiers.
4. **Runtime plurality:** Ollama is already a provider; add **LM Studio** (OpenAI-compat on localhost:1234) and **Windows Foundry Local** (when detected) as auto-discovered providers in Settings — detect by probing their default ports, one-click add. Dispatcher treats them like Ollama.
5. **README/marketing truth update:** the "GPU: not used" claims in README/system requirements get updated when this ships.

## 3. Enterprise port

None (enterprise inference is Bedrock/Anthropic). The dispatcher cleanup benefits both codebases.

## 4. Acceptance criteria

- NVIDIA machine: enabling acceleration yields ≥ 3× tok/s on a 7–9B model vs CPU (benchmark shows before/after).
- AMD/Intel iGPU machine: Vulkan path works or degrades gracefully to CPU with a clear message.
- No GPU: card shows "no compatible GPU detected", nothing breaks; base installer size unchanged.
- A running Ollama or LM Studio instance is auto-discovered and its models appear in the picker within one Settings visit.

## 5. Open questions

- Wheel hosting: GitHub release assets vs PyPI pins? (Release assets keep installer slim and versions locked.)
- macOS: Metal is already default in llama.cpp builds — verify what the current mac build does before promising anything.
- Is sidecar-restart-on-toggle acceptable UX, or do we need in-process backend swap (much harder)?
