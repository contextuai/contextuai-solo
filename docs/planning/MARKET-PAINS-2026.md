# Market Pain Points — Local AI Communities (mid-2026)

> Created 2026-06-16 from a 4-stream research sweep (r/LocalLLaMA + hardware, r/selfhosted + privacy, agents/RAG/automation, UX/onboarding + traction). **Pending review.**
>
> Purpose: ground the roadmap in what real people complain about, not what we assume is cool. Each pain is mapped to a Solo response (new spec, spec edit, or "we already do this — say so"). Sourcing caveat throughout: Reddit raw threads were largely not directly fetchable; many findings come from HN threads, GitHub issues, and 2026 aggregator write-ups that mirror the same community complaints. Treat aggregator-sourced items as directional. Strongest primary sources: Ollama GH #9890 / #2567, RecurseChat Show HN (#39532367), openai-agents GH #1544.

---

## The one-line read

Across every community, the pains cluster into four buckets, and three of them map to **moats we already half-own** (see ROADMAP differentiation section: ownership, zero-marginal-cost, staff+approvals):

1. **"I can't tell what will run / why it's slow / which model to pick."** (onboarding + hardware) — *we have a curated catalog; we're the best-positioned tool alive to fix this, and currently don't.*
2. **"Local doesn't actually mean private — my 'local' tools phone home."** (trust) — *we have zero telemetry but don't prove it.*
3. **"Agents work on Claude and break locally."** (reliability) — *we're agent-first; this hits us hardest.*
4. **"RAG over my own docs is disappointing."** (existing KB feature quality).

---

## Tier 1 — high frequency × high leverage (do these)

### P-1 · "Will it even run on my machine?"
**Evidence:** The single most-repeated friction in every stream. Users refuse to download before knowing specs (*"I don't want to download and find out it won't work in my computer"* — RecurseChat HN). The #1 beginner mistake on r/LocalLLaMA is *"choosing a model too large for available hardware, then blaming the model for being 'slow' or 'broken.'"* Quant suffixes (Q4_K_M / Q5_K_M / Q8_0, K_S vs K_M) are incomprehensible to non-experts; a whole 2026 cottage industry of explainer blogs exists just to answer "which quant?" CPU-only users get 2-5 tok/s and assume it's broken vs 50+ on GPU.
**The wish, verbatim across sources:** "a single 'best model for this computer' button."
**Solo response:** → **SPEC-27 (new, written)** — hardware detection + per-model fit badges + auto-quant + estimated tok/s, before any download.
**Why we win:** we already curate 41 GGUF models; adding hardware metadata + a detector turns our catalog into the thing every other tool lacks.

### P-2 · "Local doesn't actually mean private"
**Evidence:** The most trust-corrosive theme — not cloud AI, but discovering supposedly-local tools phone home: Ollama pings `registry.ollama.ai` on startup; LM Studio hits servers on search/download; **ComfyUI desktop shipped telemetry that kept sending even with the toggle OFF** (fixed 0.4.41); Open WebUI web-search silently calls external APIs. Long-running Ollama GH issue (#2567) demanding opt-in telemetry: *"Please... give us an option to opt out or better have this as an opt-in."* People want *verifiable* offline, not a promise.
**Solo response:** → **SPEC-28 (new, recommended)** — verifiable privacy: a network-activity panel showing zero/which outbound, an explicit "the only network calls we ever make are X" list, and a hard "airplane mode" egress lock (allowlist = model download + channels you connected). Emits SPEC-24 ledger events.
**Why we win:** Solo already has no telemetry. The moat is *proving* it. Cloud assistants structurally cannot match "your data verifiably never leaves this machine."

### P-3 · "Works on Claude, breaks locally" (agent reliability)
**Evidence:** The load-bearing agent complaint. Same agent code that runs clean on Claude API loops forever or emits invalid tool calls on Llama-3.1-8B (openai-agents GH #1544: *"keeps calling the tool over and over again without producing an output... Is this an issue or user error?"*). Small models *"fail to produce accurate parameters for tools... and have limited ability to fix mistakes."* Home Assistant's own docs concede smaller models *"may not reliably maintain a conversation when controlling Home Assistant is enabled."* 2026 sentiment has flipped from hype to "prove it": *"despite all the hype, agents didn't turn out to be reliable."*
**Solo response:** → **SPEC-29 (new, recommended)** — local tool-calling reliability layer: tolerant tool-call parser (salvage malformed JSON), loop detection (kill repeated identical calls), **grammar/GBNF-constrained decoding** via llama.cpp so small models emit schema-valid tool calls, and retry-with-repair. Feeds SPEC-23 (evals).
**Why we win:** we own our llama.cpp stack, so we can constrain decoding at the sampler level — frameworks bolted onto a cloud API can't. This is the difference between "agents that demo" and "agents that work" for our whole product.

---

## Tier 2 — strong; upgrades features we already have

### P-4 · "RAG collapses under real documents"
**Evidence:** Lab demos work; pointed at messy personal files it falls apart. *"Headers, footers, nav crumbs, and table debris dominate cosine space"*; top-1 hit rate drops to 52-63% with naive chunking. The biggest measured wins are **chunking (+35%) and embedding choice (+27%), dwarfing the LLM swap (+6%)** — users blame "the AI" but it's the ingestion pipeline. Disappointment is invisible-until-checked.
**Solo response:** → extend **SPEC-11** (KB) into a **SPEC-30 (recommended)** ingestion-quality pass: structure-aware chunking, strip boilerplate (headers/footers/nav), "show me exactly what was retrieved" diagnostic, per-source quality. Pairs with SPEC-23 retrieval evals.

### P-5 · Config-not-hardware breakage (gibberish / never-stops)
**Evidence:** GGUF models emit gibberish, loop, or never stop because of wrong chat template, missing EOS token, or bad rep-penalty — users misattribute to a bad download or weak GPU. Ollama's **silent 2048-token default context** (GH #9890) truncates models advertised at 131K *"without any error pointing at the cause"*; raising it can shard the model and *"never answers ever again."*
**Solo response:** → small additions to **SPEC-27 / catalog**: bake correct chat template + EOS per catalog entry (we curate, so we can guarantee it); auto-size `n_ctx` to model + hardware with a clear warning instead of a silent truncation. This is a chore-sized win with outsized trust payoff.

### P-6 · Maintenance treadmill / model churn
**Evidence:** *"The annoying part is keeping everything updated, new model drops every week and half don't work with whatever you're already running."* Decision paralysis across Ollama vs LM Studio vs llama.cpp vs vLLM, Open WebUI vs AnythingLLM.
**Solo response:** no new build — **positioning.** Our curated, tested, one-click catalog *is* the antidote to churn. Say it explicitly in README + posts: "we test the models so you don't chase broken weekly drops."

### P-7 · Capability-gap honesty + hybrid (validates the privacy router)
**Evidence:** Users expect local 8B to match GPT-5.2/Claude and feel let down; the mature take is hybrid — local for private/repetitive, cloud for hard reasoning. Enterprises say privacy is *less* of a blocker than expected; quality/cost decide. Tools that overpromise "ChatGPT but local" churn users.
**Solo response:** → confirms last turn's **privacy-router** idea: BYOK with **data classes** — content tagged local-only (KB, memory) physically cannot egress to a cloud key even when BYOK is on; routine reasoning can opt into Claude/GPT. Honest framing beats pretending 8B == Opus. Recommend folding into the BYOK/provider work (relates to SPEC-08).

---

## Tier 3 — table-stakes to verify (don't assume we have these)

Prosumers coming from ChatGPT treat these as baseline, and their absence reads as "sketchy" (RecurseChat HN):
- **Edit-a-prompt-and-regenerate** (rewinds the conversation from that point).
- **Conversation branching / threading.**
- **System prompts** (*"even more important than with ChatGPT 4"*).
- **Import ChatGPT history** (repeatedly called a favorite feature).
- **Full-text search across all chats** (*"ChatGPT doesn't support it"* on web — a real gap to beat).
- **Polish basics:** working feedback buttons, links open correctly, keyboard shortcuts, screen-reader labels — small breaks cost trust fast.

**Action:** audit current Solo against this list before spec'ing. Anything missing → a "chat table-stakes" cleanup spec. (Marked verify-don't-assert because Solo may already have several.)

---

## Recommended roadmap deltas (for review)

| ID | Title | Type | Priority | Kills pains | Status |
|----|-------|------|----------|-------------|--------|
| **SPEC-27** | Hardware-aware model picker ("can my machine run this?") | new | **P0** | P-1, P-5 | ✍️ written this pass |
| **SPEC-28** | Verifiable privacy (egress monitor + airplane lock) | new | P1 | P-2 | recommended |
| **SPEC-29** | Local tool-calling reliability layer | new | P1 | P-3 | recommended |
| **SPEC-30** | RAG ingestion quality (chunking/cleaning/diagnostics) | new (extends SPEC-11) | P1 | P-4 | recommended |
| SPEC-08 (edit) | add BYOK **data classes** / privacy router | edit | P1 | P-7 | recommended |
| catalog (chore) | per-model chat template + EOS + auto n_ctx | chore | P1 | P-5 | recommended |
| README/posts | curated-catalog-as-anti-churn positioning | positioning | — | P-6 | recommended |
| (audit) | chat table-stakes gap check | audit | P2 | Tier 3 | recommended |

**Cross-cutting:** SPEC-27/28/29 should emit SPEC-24 ledger events from day one (same rule as SPEC-14..21).

---

## Traction lessons → first post (see COMMUNITY-LAUNCH-KIT "Post Zero")

Observed tactics that actually worked for indie/local-AI launches:
1. **Frame the first post as a feedback request, not a pitch** — highest-leverage, best-aligned with anti-promo norms. One founder: personal story + *"brutal honesty"* → 9.9k views, 112 signups from one post.
2. **Founder responsiveness in-thread is the #1 lever** — reply to ~every comment fast, ship fixes in <24-48h and say so.
3. **Pick a well-matched community over a giant generic one**; lead with **one concrete, testable scenario**, benefit-first title.
4. **Seed credibility** (RecurseChat got a public nod from llama.cpp's author → instant legitimacy).
5. **Be honest about limitations** in the post itself — the skeptical crowds reward it.
6. **Don't be Mac-only** (we're Windows-tested — an advantage) and **be free/open** (we are).

Caveats: conversion numbers are single-anecdote/self-reported — expect lower. r/LocalLLaMA + r/selfhosted have strict self-promo rules; feedback-request + open-source + honest-limits framing is what survives.
