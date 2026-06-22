# Feature Recommendations — Brainstorming Doc

> Working document for planning the next wave of ContextuAI Solo features.
> We iterate on this until each item is either **Accepted** (ready to spec/implement),
> **Parked**, or **Rejected**. Nothing here is committed work until accepted.
>
> Status legend: 🟡 Proposed · 🔵 Discussing · 🟢 Accepted · ⏸️ Parked · ❌ Rejected
>
> Companion docs: `docs/planning/UNDERSTANDING.md` (system map), `docs/planning/GAPS.md` (findings register), `docs/planning/specs/SPEC-*.md` (implementation-ready specs for shaped items — see `docs/planning/README.md` for the review → implement workflow).

---

## A. Product Features (Solo)

### A1. Model Preload & Warmup 🟡
- **What:** "Preload" button per installed model + a "Ready" badge once loaded. Backend keeps 1–2 models warm in an LRU cache instead of loading on first message.
- **Why:** Large GGUF models take 5–15s to load on first use today; users perceive it as the app hanging. First impression of local AI is the worst moment of the product.
- **How (sketch):** `local_model_service` already holds one loaded model. Add `POST /api/v1/local-models/{id}/preload`, surface load state on the Models page and in the chat model dropdown (`● Ready` / `○ Cold`). Show estimated load time from file size.
- **Effort:** S–M · **Impact:** High (perceived speed)
- **Open questions:**
  - Keep 1 warm model (simple) or LRU of 2 (more RAM pressure on 8–16 GB machines)?
  - Auto-preload last-used model on app start?

### A2. Crew Dry-Run Mode 🟡
- **What:** "Dry run" button in step 7 (Review & Create) of the crew builder. Runs the crew against a sample input with all outbound connections disabled; shows the final output in a modal.
- **Why:** Today users publish a crew straight to Reddit/Telegram and debug in production — wasted tokens, channel spam, lost confidence.
- **How (sketch):** Reuse `run_headless()`-style execution with a `dry_run=True` flag that swaps Distribution adapters for a capture sink. Sample input: paste-your-own or pick a recent inbound message from the bound channel.
- **Effort:** M · **Impact:** High (trust + retention)
- **Open questions:**
  - Should dry-run also be available from the crew list (re-test after edits)?
  - Persist dry-run results as a `crew_runs` row with `kind="dry_run"`?

### A3. Crew Execution Insights 🟡
- **What:** Insights tab on the Crews page: runs/day heatmap (30 days), error rate per crew, trigger leaderboard (which keywords/hashtags fire most), rough token-cost estimate per crew.
- **Why:** Crews run in the background; users have zero visibility into what's working. Insights drive both engagement and crew tuning.
- **How (sketch):** Data largely exists in `crew_runs` + chat analytics capture. Aggregation endpoints + a recharts dashboard.
- **Effort:** M · **Impact:** Medium-High
- **Open questions:**
  - Tab inside Crews vs. dedicated `/insights` sidebar item (sidebar is intentionally 8 items — adding one is a real cost)?

### A4. KB Freshness: Staleness Badges + Auto-Suggest 🟡
- **What:** (a) "Synced 2h ago" / "⚠ stale — 5 changed files" badges on folder-mapped KBs, in both the Knowledge page and the chat KB dropdown. (b) Auto-suggest: score KBs against the typed prompt and offer "Use 'Tax Docs 2025' KB?" as a one-click banner.
- **Why:** Folder-mapped RAG is the product's biggest differentiator; silent staleness and manual KB selection are the two friction points that hide it.
- **How (sketch):** Staleness = compare folder mtimes vs. last `kb_index_jobs` run (cheap walk, already have the code). Auto-suggest = embed the prompt with the bundled MiniLM model, cosine-match against KB centroid vectors.
- **Effort:** S (badges) + M (auto-suggest) · **Impact:** High
- **Open questions:**
  - Auto-suggest opt-in or on by default? (It adds an embedding call per message.)
  - Split into two items if badges should ship first?

### A5. Crew Export / Import → Community Templates 🟡
- **What:** "Export Crew" → JSON (agents, triggers, bindings, approval config, secrets stripped). "Import Crew" → clone with new IDs. Phase 2: a `contextuai-crews` GitHub repo with a manifest the app reads to show a "Community Crews" tab.
- **Why:** Open-source flywheel — users become content creators; templates are the cheapest acquisition channel for an OSS desktop app.
- **How (sketch):** Serialize the crew document minus `connection_bindings` credentials (keep platform names as placeholders to re-bind on import). Version the schema.
- **Effort:** S (export/import) + M (community tab) · **Impact:** High strategically
- **Open questions:**
  - Re-bind flow on import: wizard step or "fix-up" banner on the imported crew?
  - Moderation story for community submissions (PR review only?).

### A6. Batch Processing 🟡
- **What:** New `/batch` flow: pick an agent or crew + upload a CSV; each row interpolates into the prompt and runs; results export to CSV/PDF report.
- **Why:** "Process 100 things the same way" is the strongest bridge from hobby use to business value (lead lists, contract screening, content variants) and a natural enterprise upsell.
- **How (sketch):** Reuse the crew run queue with a `batch_id`; throttle concurrency for local models (serial) vs. cloud (parallel N). Progress via existing SSE patterns.
- **Effort:** L · **Impact:** High for business users
- **Open questions:**
  - MVP scope: agent-only (skip crews) to cut effort in half?
  - Cost guardrail: require explicit confirm with estimated token cost before run?

### A7. HF Token Setting (Model Hub) 🟡
- **What:** Optional HuggingFace token field in Settings → AI Providers; used by the Model Hub downloader for rate limits and gated models.
- **Why:** HF now rate-limits anonymous downloads (429s on shared IPs). The new downloader already honors `HF_TOKEN` env — a Settings field makes it usable by normal people. Direct follow-up to the download fix.
- **How (sketch):** Store like other provider keys (`cloud_provider_keys`), inject into `ModelManager._download_files` instead of/alongside the env var.
- **Effort:** S · **Impact:** Medium (kills the 429 failure class)
- **Open questions:** none — mostly mechanical. Candidate for first acceptance.

### A8. Quick-Reply Templates (Approvals Queue) 🟡
- **What:** User-defined templates (`Approved: {brief}`, `Need more info: {details}`) surfaced as a dropdown on items in the Approvals queue, with inline edit before send.
- **Why:** Approval turnaround is the human bottleneck in the human-in-the-loop story; 30s → 5s per item.
- **Effort:** S–M · **Impact:** Medium (high for heavy channel users)
- **Open questions:**
  - Per-crew templates or global?

---

## B. Platform Hardening (recommended before marketing push)

### B1. Sidecar Auth Token + CORS Lockdown 🟡
- **What:** Random per-session token generated in `sidecar.rs`, passed to the backend via env, required on every request. CORS restricted to Tauri/dev origins instead of `*`.
- **Why:** Today any local process or drive-by webpage can call `localhost:18741/v1/chat/completions` and spend the user's saved cloud API keys. This is the top security item.
- **Caveat:** The OpenAI-compat endpoint is *meant* to be used by external tools (Aider, Continue) — needs a deliberate exception: keep `/v1/*` open (or token-optional) while gating `/api/v1/*`.
- **Effort:** M · **Impact:** Critical security

### B2. Secrets at Rest 🟡
- **What:** Encrypt cloud provider keys + channel tokens (Windows DPAPI / OS keychain via Tauri plugin, or Fernet with a key stored in the OS credential store).
- **Effort:** M · **Impact:** High security

### B3. Sidecar Lifecycle Robustness 🟡
- **What:** Detect stale/orphaned backend on port 18741 at startup (health-check → kill or adopt), surface sidecar startup failure in the UI instead of a blank app.
- **Why:** Crash → orphan → next launch hangs. Second-most-reported class of "app is broken" after model downloads.
- **Effort:** M · **Impact:** High reliability

### B4. Atomic `update_one` in SQLite Adapter 🟡
- **What:** Single-statement `UPDATE ... SET data = json_patch/json_set(...)` or version-checked CAS retry, replacing read-modify-write.
- **Why:** Concurrent crew runs can clobber each other's state today.
- **Effort:** M · **Impact:** Medium (data integrity)

### B5. Always-On SSRF Blocklist 🟡
- **What:** Make the localhost/metadata-IP blocklist in `api_tools.py` unconditional (currently prod-only).
- **Effort:** XS · **Impact:** Medium. Candidate for first acceptance.

---

## C. Marketing Site (quick wins, separate repo)

| # | Item | Effort | Status |
|---|------|--------|--------|
| C1 | Reddit logo + blurb in channels grid on solo.html | XS | 🟡 |
| C2 | Link cookbook.html from navbar/footer (currently orphaned) | XS | 🟡 |
| C3 | Fix ~5 `href="#"` footer links; hide placeholder blog cards or write the posts | S | 🟡 |
| C4 | Persistent "Download Solo (Free)" navbar CTA | XS | 🟡 |
| C5 | Knowledge Base / folder-mapping landing page (top differentiator) | M | 🟡 |
| C6 | "For Developers" section: OpenAI-compat API with Cursor/Continue/Aider recipes | S | 🟡 |
| C7 | sitemap.xml + custom 404 + meta/alt-text audit | S | 🟡 |

---

## Decision Log

| Date | Item | Decision | Notes |
|------|------|----------|-------|
| 2026-06-12 | — | Doc created | Initial recommendations from codebase + site review |

---

## Parking Lot (raw ideas, not yet shaped)

- Coder → Solo round-trip: "Get Help" on a failed run → bug-analyzer chat → "Apply patch" back into the Coder project.
- Agent library search + tags + "suggested for you" (96 agents outgrow category tabs).
- Pin/favorite agents.
- Brand Voice marketing (built but unmarketed) — belongs with C5/C6 wave.
