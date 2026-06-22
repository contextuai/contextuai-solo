# SPEC-19 — Voice Layer v1 (Local STT/TTS)

- **Links:** ROADMAP F-7 (Q4 2026) · MOONSHOT BL-6
- **Priority:** P2 · **Effort:** M
- **Review status:** ⬜ pending review
- **Type:** roadmap spec

## 1. Goal

Push-to-talk into chat and "read my Pulse aloud" — 100% local audio. No cloud STT/TTS, ever (that's the differentiator; say it in marketing).

## 2. v1 Scope

1. **STT** — whisper.cpp via `pywhispercpp` (or whisper GGUF through existing llama-infra if practical — investigate first; dedicated whisper.cpp binding is the safe default). Models (base/small/medium, multilingual) distributed through the existing Model Hub UI as a new "Audio" category — reuses the new downloader (resume/cancel/progress) for free.
2. **Push-to-talk UI** — mic button in chat input (hold-to-talk or tap-toggle): record (Tauri/webview `getUserMedia`), stream to backend, transcribe, drop text into the input for user confirmation (auto-send off by default).
3. **TTS** — Piper (ONNX voices, runs on the bundled onnxruntime) for Pulse read-out + "read this reply" on any message. 2–3 bundled-or-downloadable voices.
4. **Settings** — Voice tab: STT model picker, voice picker, input device, auto-send toggle.

## 3. Explicit non-goals (v1)

No wake word ("Hey Solo"), no full-duplex/realtime conversation mode, no voice cloning. These are v2 candidates only after usage data justifies them.

## 4. Enterprise port

Deferred — enterprise voice triggers compliance review (recording consent, retention). Solo-only for now; note in enterprise backlog.

## 5. Acceptance criteria

- On an 8 GB no-GPU machine: 10s utterance transcribes in < 3s with whisper-small-class accuracy; UI shows interim "transcribing…" state.
- Pulse read-out sounds acceptable (Piper quality) and is cancellable mid-playback.
- Zero network traffic during record→transcribe→speak (verifiable offline).
- Mic permission denied → graceful explanation, feature hides.

## 6. Open questions

- PyInstaller weight: whisper.cpp + Piper add native libs to the sidecar — measure installer delta; if > ~80 MB, make voice an optional downloadable component like GPU runtimes (SPEC-15 pattern).
- Streaming transcription (live words while talking) vs whole-clip — whole-clip is much simpler; is it good enough for v1?
