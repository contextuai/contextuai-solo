# Community Launch Kit

> The "social is a pain" antidote: everything pre-written, one playbook, ~30 minutes of human time per post. Posts are drafts in YOUR voice — edit before posting, never paste blind. Created 2026-06-12.
>
> **Golden rule for Reddit/HN:** these communities reward *builders telling honest stories* and punish marketing. Every draft below is written dev-to-dev, leads with substance, and admits limitations. Keep it that way when you edit.

---

## 1. The plan in one paragraph

One **anchor post** per week for 4 weeks, each in a different community, each with a *different angle* (never the same text twice — cross-posting identical content gets flagged). You spend: 10 min personalizing the draft, 5 min posting at the right time, and 2–3 check-ins that day to answer every comment fast (first 2 hours decide a post's fate). Solo itself monitors mentions via your own Reddit watcher so you never miss a reply. That's the whole system.

## 2. Per-community rules of engagement (read once)

| Community | Self-promo rules (verify current rules before posting) | Best time (US) | What works |
|-----------|------------------------------------------------|----------------|------------|
| r/LocalLLaMA | Builder posts welcome if technical + open source. Flair: "Resources". Don't oversell benchmarks | Tue–Thu, 8–11am ET | Technical depth, GGUF specifics, honest perf numbers, screenshots |
| r/selfhosted | OSS projects welcome; "Release" flair; they HATE hidden SaaS dependencies — lead with "no cloud, no account" | Sat–Sun morning | Privacy, no-subscription, docker/compose mention, screenshots |
| r/SideProject | Very promo-tolerant; story > product | Any weekday evening | The journey, struggles, "solo dev" angle |
| r/opensource | Project must be genuinely open; mention license honestly (Apache-2.0 + Commons Clause — disclose the Commons Clause, they will check) | Weekday mornings | License clarity, contribution invites |
| Hacker News (Show HN) | Read the Show HN guidelines. Title format: "Show HN: X – Y". First comment from you = context + limitations. Never use marketing language | Weekday 8–10am ET | Architecture honesty, tradeoffs, responding to every technical question |
| X/Twitter | Thread with video > anything else | Tue–Thu 9–12 ET | 30–60s screen recording, tag no one in v1 (earn it first) |

**Universal rules:** answer every comment in the first 3 hours · never argue, concede valid criticism and file it as an issue ("good catch — tracked: <link>") · never post the same link from sock accounts · if a post flops, that's data, not failure — different angle next week.

## 2.5. Post Zero — your FIRST-EVER post (do this one first)

You've never posted about Solo. Don't open with the polished "look what I built" announcement — the research is unambiguous that the first post should be a **feedback request**, because (a) it's what the anti-promo communities reward, and (b) you genuinely want signal before you scale outreach. The single biggest lever is **you answering every comment fast and shipping a fix within 24-48h and saying so.** That one behavior outperformed every headline in the data.

**Where:** r/LocalLLaMA (flair: **Discussion** or **Resources**) is the best-matched home for a privacy-first local-agent tool. If you want a gentler first audience, post to a smaller well-matched sub first (e.g. r/SideProject or r/opensource) the day before, then r/LocalLLaMA — but r/LocalLLaMA is where your people are.

**Timing:** Tue-Thu, 8-11am ET. Be at your keyboard for the next 3 hours.

**Title (feedback-framed, benefit-first):**
> I built a local-first desktop app that runs multi-agent "crews" on GGUF models — looking for brutal feedback before I push it further

**Body:**
> Solo dev, first time posting this here. For the past year I've been building **ContextuAI Solo** — an open-source desktop app (Tauri + llama.cpp) where local models do actual work, not just chat: pre-built agents you can run as **crews** (multi-agent teams), local RAG over your own folders with citations, and channel watchers (Telegram/Discord/Reddit) that draft replies into an **approval queue** so nothing sends without you signing off. No account, no telemetry, offline after the model download.
>
> I'm posting because I want honest feedback from people who actually run models locally — not upvotes.
>
> **One concrete thing to try:** point it at a folder of your notes/docs, then ask a crew to summarize-and-draft something from them. That's the workflow I built it for; I want to know where it falls down on *your* messy real files.
>
> **Where I know it's weak (tell me what else):**
> - CPU-only inference today — GPU builds are next. (I'm building a "will this model even run on your machine" picker right now because I know that's the #1 pain here.)
> - Windows is the most-tested platform; Mac/Linux are rougher.
> - Installer isn't code-signed yet, so SmartScreen will complain.
> - Local 8B models are great for private/repetitive work but won't match Claude/GPT on hard reasoning — I'm not pretending otherwise.
>
> Repo: <link>. I'll be in the thread all day answering everything — and if you flag a real bug I'll try to ship a fix this week and reply to tell you. What would make this actually useful for your setup?

**Why this version works (per the research):** feedback-request framing survives self-promo rules · one testable scenario gives people a 30-second reason to engage · the honest-limitations list is exactly what skeptical local-AI crowds reward · the "I'll ship a fix this week" promise is the highest-converting behavior observed — **so you have to actually do it.**

**Before you hit post:**
- [ ] Repo has a README with **system requirements** and screenshots (the #1 "I won't even download it" objection is unanswered specs).
- [ ] You can be in-thread for 3 hours.
- [ ] Optional but high-value: get one credible person in the space (a model author, a known maintainer) to take a look first — a single credible nod gave RecurseChat instant legitimacy.
- [ ] Have a GitHub Issues link ready so you can convert every criticism into "good catch — tracked: <link>" live in the thread.

After Post Zero lands and you've learned from it, run the weekly anchor posts below.

---

## 3. Anchor posts (drafts — personalize before use)

### Week 1 — r/LocalLLaMA (flair: Resources)

**Title:** I built a desktop app that runs 96 business agents + multi-agent crews on local GGUF models (open source, Tauri + llama.cpp)

**Body:**
> Solo dev here. For the past year I've been building ContextuAI Solo — a desktop app where local models do actual business work, not just chat.
>
> What it does: 96 pre-built agents (marketing, finance, legal, HR…) that you can run individually or as **crews** — multi-agent teams with sequential/parallel/autonomous modes. Crews can watch your Telegram/Discord/Reddit, draft replies, and hold them in an approval queue until you sign off. There's a local RAG layer (map any folder, auto-indexed on schedule, citations in answers) and an OpenAI-compatible endpoint so the same model you chat with also serves Aider/Continue.
>
> Local stack: llama-cpp-python, 41 curated GGUF models in a one-click hub (Qwen 3.5 / DeepSeek R1 / Gemma / Phi-4, 0.5B→70B), embeddings via bundled MiniLM ONNX. SQLite for everything. No account, no telemetry, fully offline after model download.
>
> Honest limitations: CPU-only inference right now (GPU builds are on the roadmap), Windows is the most-tested platform, and the installer isn't code-signed yet so SmartScreen complains.
>
> Repo: <link> — would genuinely love feedback on the model catalog choices and what 8–16GB machines can realistically run for multi-agent work.

*(If the download-fix release has shipped, add: "Recent war story: model downloads kept failing on locked-down networks — turned out to be the HF Xet protocol + a stall-detector bug compounding. Wrote up the fix in <release notes link>." — r/LocalLLaMA loves debugging stories.)*

### Week 2 — r/selfhosted (flair: Release)

**Title:** ContextuAI Solo — self-hosted AI office: 96 agents, multi-agent crews, local RAG, social auto-reply with approval gates. No cloud, no account, no subscription.

**Body:**
> Everything runs on your machine: models (GGUF via llama.cpp), database (SQLite), embeddings (local ONNX). The only network calls are the one-time model download and whatever channels *you* connect.
>
> The bit r/selfhosted might like: crews can monitor inbound (Telegram bot, Discord bot, Reddit) and auto-draft replies — but nothing sends without hitting an approval queue first. You're the SRE *and* the editor-in-chief.
>
> Also ships an OpenAI-compatible API on localhost, so your other self-hosted tools can use the models you've already downloaded.
>
> Optional BYOK for cloud models if you want them; zero cloud otherwise. Apache 2.0 with Commons Clause (free to use/modify/self-host; can't be resold as a competing product — being upfront about that).
>
> Repo + install: <link>. Roadmap (memory layer, proactive briefings, browser operator — all local) is in the repo. Tell me what's missing for your setup.

### Week 3 — Show HN

**Title:** Show HN: ContextuAI Solo – 96 AI agents and multi-agent crews, running locally on your desktop

**First comment (post immediately after submitting):**
> Author here. Solo is a Tauri desktop app: React front, FastAPI sidecar, llama-cpp-python for local GGUF inference, SQLite behind a MongoDB-compatible adapter (the enterprise edition runs Mongo; the adapter lets one codebase serve both).
>
> The core idea: agents shouldn't just chat — they should produce work. So: crews (multi-agent pipelines with visible reasoning), channel triggers (inbound Telegram/Reddit → crew runs → approval queue → reply), folder-mapped local RAG with citations, and an OpenAI-compatible endpoint so the downloaded model also powers your IDE tools.
>
> Things I'd do differently / current warts: CPU-only inference (GPU is next), the Mongo-compat layer's update path needed a CAS rewrite (in progress), and unsigned installers trip SmartScreen.
>
> Happy to answer anything about Tauri sidecars, shipping llama.cpp to non-technical users, or why the approval queue turned out to be the most important feature in the app.

### Week 4 — r/SideProject

**Title:** I spent a year building "an AI team on your desktop" as a solo dev — 96 agents, local models, zero subscriptions. Here's what I learned.

**Body:** 3 short lessons (pick real ones — e.g., "the hardest bug was model downloads failing on corporate networks", "users don't want autonomy, they want drafts + an approve button", "open source is the only honest distribution channel for a privacy app") + screenshots + link. End with: "AMA about Tauri, llama.cpp packaging, or building against the big-AI current."

### X/Twitter thread (post alongside Week 1)

1/ Your laptop can run an AI *team* now. 96 agents. Multi-agent crews. 100% local. $0/month. 🧵
2/ [30–60s screen capture: Telegram message arrives → crew deliberates with visible thinking → draft lands in Approvals → tap approve → reply posts]
3/ Everything stays on your machine: GGUF models via llama.cpp, SQLite, local embeddings. No account. No telemetry.
4/ It also serves an OpenAI-compatible API — the model you chat with powers Aider/Continue in your IDE too.
5/ Open source. Roadmap: memory, proactive briefings, browser operator — all local. ⭐ <repo link>

## 4. Cadence & checklist (repeatable)

**Per post:** [ ] personalize draft (10 min) · [ ] screenshots/GIF current version · [ ] post at target time · [ ] reply to every comment for 3h · [ ] file good criticism as GitHub issues, link them in-thread · [ ] log outcome below.

**Ongoing (Solo does this for you — dogfood):** set up a Reddit **watcher/connection in your own app** for "ContextuAI" + competitor names across r/LocalLLaMA, r/selfhosted — drafted replies land in your Approvals queue. **You post manually** (bot-posting violates most subreddit rules and HN norms; Solo monitors and drafts, the human sends).

**Monthly after launch month:** one "what shipped" update post in GitHub Discussions + X; only return to a subreddit when there's genuinely new substance (Pulse and Operator mode are each a fresh r/LocalLLaMA post when they ship).

## 5. Outcome log

| Date | Where | Post | Result (upvotes/comments/stars delta) | Lesson |
|------|-------|------|----------------------------------------|--------|
| | | | | |
