# SPEC-27 — Hardware-Aware Model Picker ("Can my machine run this?")

- **Links:** MARKET-PAINS-2026 P-1, P-5 · relates to SPEC-15 (GPU), SPEC-08 (HF token), Model Hub catalog
- **Priority:** P0 · **Effort:** M
- **Review status:** ⬜ pending review
- **Type:** gap-driven product spec (sourced from community pain research, not internal audit)
- **Why ours is different:** every other local tool makes the user guess; we already curate the catalog, so we can answer "what should *I* run" definitively. This is the highest-frequency pain in all four research streams and the cheapest moat we have.

## 1. Problem

The #1 onboarding friction across r/LocalLLaMA, r/selfhosted, and HN: people can't tell what their machine can run, can't decode quant labels (Q4_K_M vs Q5_K_M vs Q8_0), download something too big, get an OOM or 2-5 tok/s, and conclude the model — or the app — is "broken." Many won't even download without knowing specs first. The universally-requested fix is a single **"best model for this computer"** action.

Solo is uniquely positioned: the catalog is already curated (41 GGUF models). We only need to add hardware awareness on top of it.

## 2. v1 Scope

1. **Hardware probe (first run + on demand).** Detect: CPU cores, total + available RAM, GPU vendor/model, VRAM, and platform. Windows-first (most-tested). Store a `hardware_profile` (with a manual "re-scan" in Settings). No network calls — purely local introspection.
2. **Per-model fit badges in Model Hub.** For every catalog entry + quant, compute a verdict against the profile and show it *before* download:
   - ✅ **Runs great** (fits in VRAM, or comfortable on CPU/RAM) — with an **estimated tok/s** range.
   - ⚠️ **Runs slow** (CPU-only or partial offload; will work but expect N tok/s).
   - 🚫 **Won't fit** (needs more RAM/VRAM than available) — say exactly what's short ("needs ~14 GB, you have 8 GB").
3. **"Best for your machine" one-click.** A prominent recommendation that picks the strongest model + quant that lands in the ✅ band for the detected hardware, with a one-line rationale. This is the headline feature.
4. **Quant, in plain language.** Replace/annotate raw quant suffixes with human labels ("smaller & faster" ↔ "larger & smarter") and a tooltip; auto-select the best-fitting quant for a chosen model rather than making the user choose.
5. **Pre-download guardrail.** If a user picks a 🚫 model anyway, a clear confirm ("this is larger than your machine can hold; it'll be very slow or fail to load — continue?") instead of a silent failure later.
6. **Correct runtime config baked in (P-5 fix).** Each catalog entry carries its correct chat template + EOS token; `n_ctx` is auto-sized to the model's real window *and* the hardware budget, with a visible note if capped — never a silent 2048-style truncation.

## 3. Architecture sketch

- **Catalog metadata:** extend `services/model_catalog.py` entries with per-quant `params_b`, `file_size_bytes`, `min_ram_gb`, `min_vram_gb`, `context_window`, `chat_template_id`, `eos`. (Sizes are already known from HF HEAD requests used by the downloader — can be backfilled.)
- **Probe:** a `services/hardware.py` module. CPU/RAM via `psutil`; GPU/VRAM via vendor probes (NVML for NVIDIA, platform APIs / `wmi` on Windows, Metal on macOS) with graceful "unknown GPU → assume CPU" fallback. Cache to the DB; never block UI on it.
- **Fit engine:** a pure function `classify(model_quant, hardware_profile) -> {verdict, est_tps_range, reason}`. Keep it deterministic and unit-testable; tok/s estimate is a coarse heuristic (model size, quant, mem bandwidth class, CPU vs GPU) — label it an estimate, never a promise.
- **UI:** badges + "Best for your machine" card in the Model Hub; a small hardware summary in Settings with re-scan.
- **Ledger:** emit a SPEC-24 event on probe + on recommendation shown/accepted (additive, day one).

## 4. Enterprise port

Same fit engine, server-side: an admin curates which models are offered per hardware tier; the probe runs on the inference host. The "best for this box" logic helps ops right-size deployments. Catalog metadata schema is shared.

## 5. Acceptance criteria

- On a fresh install, Model Hub shows a fit badge on every model within ~1s of opening, with no network call for the probe.
- A machine with 8 GB RAM / no dGPU shows 🚫 on a 13B-Q5 with the exact shortfall, ⚠️/✅ on small models, and a working "Best for your machine" pick that actually loads and runs.
- A machine with a 24 GB GPU surfaces a meaningfully larger ✅ recommendation than the 8 GB machine.
- Estimated tok/s is within a sane order of magnitude of measured tok/s on at least 3 reference machines (validate against SPEC-15 benchmark if available).
- Picking a 🚫 model triggers the confirm dialog, not a silent later failure.
- No model in the catalog ever emits never-ending output or gibberish from a wrong template/EOS on a smoke-test prompt.

## 6. Out of scope (v1)

- Live re-benchmarking every model (SPEC-15 owns in-app benchmarking; reuse its numbers if present).
- Non-catalog/custom HF models get a best-effort estimate from file size only, clearly marked lower-confidence.
- Multi-GPU split tuning (note it, don't auto-tune in v1).

## 7. Open questions

- Tok/s heuristic vs. a tiny one-time micro-benchmark at first run — heuristic is simpler and offline; a 5-second micro-bench would be far more accurate. (Proposed: ship heuristic in v1, add opt-in micro-bench in v1.1 / via SPEC-15.)
- Do we surface the raw quant suffix at all, or hide it entirely behind plain labels for non-experts while keeping it in an "advanced" view? (Proposed: plain by default, raw on hover/advanced.)
- GPU probe dependency footprint on Windows (NVML/wmi) vs. PyInstaller bundle size — verify before committing the dep.
