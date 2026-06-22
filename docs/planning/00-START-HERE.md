# 00 · Start Here — Reading Order

> For Nagendra. This folder has grown to ~35 files. Read them in *this* order, not file-name order — it goes context → strategy → specs-by-priority → future. Each line says **why** to read it and **what decision (if any) is waiting on you**. Time estimates assume a careful read. Everything is **pending your review**; nothing is committed or implemented.

## If you only have 20 minutes

1. **`MARKET-PAINS-2026.md`** — what the local-AI communities actually complain about, mapped to our responses. The freshest, most decision-dense doc. *(8 min)*
2. **`specs/SPEC-27-hardware-aware-model-picker.md`** — the #1 user pain, the one new P0. *(6 min)*
3. **`COMMUNITY-LAUNCH-KIT.md` → "Post Zero"** — your first-ever post, ready to personalize. *(5 min)*

Then come back for the rest.

---

## Full reading path

### Phase 1 — Orientation (understand the ground) · ~25 min
| # | File | Why read it | Decision waiting |
|---|------|-------------|------------------|
| 1 | `UNDERSTANDING.md` | The system map for all three repos. Every spec assumes this. Skim if you know the code cold. | — |
| 2 | `GAPS.md` | The findings register — every security/reliability/product/marketing issue found, with severity. This is "what's wrong today." | Confirm severities feel right |
| 3 | `MARKET-PAINS-2026.md` | **The new research.** What people actually want, ranked by frequency × how well we can fix it. Drives SPEC-27..30. | Which pains to formalize (most already done) |

### Phase 2 — Strategy (where we're going) · ~20 min
| # | File | Why read it | Decision waiting |
|---|------|-------------|------------------|
| 4 | `ROADMAP-2026H2-2027.md` | The 12-month "agents → colleagues" plan + the three-moats differentiation (ownership / zero-marginal-cost / staff+approvals). The narrative the specs serve. | Does the thesis hold? |

### Phase 3 — Specs you'd ship first (highest value, read closely) · ~40 min
*Read these in this order — it's priority + dependency order, not numeric.*
| # | File | Why first | Decision waiting |
|---|------|-----------|------------------|
| 5 | `specs/SPEC-27-hardware-aware-model-picker.md` | Kills the #1 onboarding pain; biggest visible win; we're uniquely placed to build it. | §7: hide raw quant labels? micro-benchmark in v1? |
| 6 | `specs/SPEC-01-...` (sidecar auth + CORS) | P0 security foundation; several roadmap features hard-depend on it. | §5: how to auth the `/v1/*` OpenAI-compat surface |
| 7 | `specs/SPEC-28-verifiable-privacy.md` | Turns our real (but invisible) "no telemetry" into a provable moat. | §5: **does the app check for updates?** — must answer before the privacy manifest ships |
| 8 | `specs/SPEC-29-local-tool-calling-reliability.md` | Fixes "works on Claude, breaks locally" — core to an agent-first product. | §7: does our llama-cpp version expose grammar sampling? |
| 9 | `specs/SPEC-30-rag-ingestion-quality.md` | Makes "chat with my docs" actually good (chunking beats a bigger model). Upgrades existing KB. | §7: bump default embedding model or keep opt-in? |

### Phase 4 — Remaining gap-fix specs (hardening) · ~45 min
Read when you want the full security/reliability picture. Order given is rough priority.
| # | File | One-liner |
|---|------|-----------|
| 10 | `specs/SPEC-03-...` sidecar lifecycle | P0 — orphan processes, port fallback, error UI. |
| 11 | `specs/SPEC-05-...` SSRF blocklist | P0 (small) — always-on egress guard for fetch paths. |
| 12 | `specs/SPEC-02-...` secrets at rest | P1 — encrypt stored keys (keyring + Fernet). |
| 13 | `specs/SPEC-08-hf-token-setting.md` | P1 — HF token in Settings **+ the new BYOK data-classes addendum** (private data can't silently go to cloud). |
| 14 | `specs/SPEC-12-...` Tauri CSP | P1 (small) — lock down the webview. |
| 15 | `specs/SPEC-04-...` atomic update_one | P1 — fix the non-atomic DB write. |
| 16 | `specs/SPEC-06-...` streaming durability | P1 — retry + dead-letter, Ollama abort parity. |
| 17 | `specs/SPEC-07-...` startup failure surfacing | P2 — stop silent seed/migration failures. |
| 18 | `specs/SPEC-09-...` model preload | P2. |
| 19 | `specs/SPEC-10-...` crew dry-run | P2 — decision: persist dry-runs as `crew_runs kind="dry_run"`. |
| 20 | `specs/SPEC-11-...` KB staleness badges | P2 — SPEC-30 extends this. |
| 21 | `specs/SPEC-13-...` marketing quick wins | P1 — site fixes. |

### Phase 5 — Roadmap specs (the future, bigger + less certain) · read at leisure
SPEC-14 → SPEC-26, in `specs/`. Order them by the ROADMAP quarters (Q3 2026 first):
`SPEC-14 memory` ⭐, `SPEC-15 GPU`, then `SPEC-16 Pulse` ⭐, `SPEC-17 watchers`, `SPEC-18 digital workers` ⭐, `SPEC-19 voice`, then `SPEC-20 operator` ⭐, `SPEC-21 MCP/A2A`, `SPEC-22 marketplace`, then `SPEC-23 evals` ⭐, `SPEC-24 governance` ⭐, `SPEC-25 mobile`, `SPEC-26 commerce (watch-list)`. ⭐ = quarter flagship; each needs a design doc before build.

### Phase 6 — Going public (when you're ready to post) · ~15 min
| File | Why |
|------|-----|
| `COMMUNITY-LAUNCH-KIT.md` | Start with **"Post Zero"** (your first-ever post, feedback-framed). Then the 4 weekly anchor posts, per-community rules, and the cadence checklist. The one prerequisite: README needs system requirements + screenshots before you post. |

---

## The decisions only you can make (collected)

These are the open questions blocking nothing else from being read, but blocking *implementation*. Pulled together so you can decide in one sitting:

1. **SPEC-01 §5** — how to authenticate the `/v1/*` OpenAI-compat endpoint (recommendation in-spec: Settings-visible API key, default on).
2. **SPEC-28 §5** — *does Solo check for updates on launch?* The privacy manifest's credibility hinges on this. (If yes → make it disclosed + toggleable; if no → say so as a selling point.)
3. **SPEC-29 §7** — does the pinned llama-cpp-python expose grammar sampling? (Gates the biggest reliability win; a verify task, not a preference.)
4. **SPEC-30 §7** — keep MiniLM as default embeddings or bump it (re-index cost).
5. **SPEC-08 addendum** — block vs. ask vs. strip when private data would hit a cloud model (proposed: ask once, remember per-conversation).
6. **SPEC-10** — persist crew dry-runs as `crew_runs kind="dry_run"`?
7. **SPEC-05** — confirm the LAN-allowed / loopback-blocked policy.

Tell me your calls on these and I can fold them into the specs so the implementing sub-agents have no ambiguity.
