# ContextuAI Solo — Launch Playbook (Linear Flow)

> Work through this top-to-bottom. Each section is one sitting. Check items off as you go.

---

## DAY 0 — PREP (Before Launch Day)

### Accounts & Profiles

- [ ] **Hacker News** — create account at https://news.ycombinator.com/login, leave a few genuine comments on AI/open-source posts to build karma
- [ ] **Reddit** — ensure account has enough karma to post in r/LocalLLaMA, r/selfhosted, r/artificial, r/opensource
- [ ] **Twitter/X** — profile ready, pinned tweet slot available
- [ ] **LinkedIn** — profile updated with ContextuAI context
- [ ] **Dev.to / Hashnode** — account created, ready to publish blog post
- [ ] **Product Hunt** — optional, consider for a later launch

### Repository & Release

- [ ] Repo is **public** on GitHub
- [ ] **v1.0.0-beta.1** release is published (not draft) with all installers
- [ ] README has: download badges, install instructions, GIF preview, model recommendations
- [ ] `CONNECTIONS-GUIDE.md` is committed and linked from README
- [ ] `CONTRIBUTING.md` exists with contribution steps
- [ ] GitHub Issues templates set up (bug report, feature request)
- [ ] "good first issue" labels created for contributor onboarding
- [ ] Branch protection enforced on main

### Testing

- [ ] Windows installer tested — document SmartScreen bypass steps
- [ ] macOS DMG tested — right-click > Open works
- [ ] Linux .deb tested (or find someone with Ubuntu to test)
- [ ] First-run wizard completes successfully
- [ ] Local model download works (test Qwen 3 8B)
- [ ] Chat works with local model
- [ ] Agent library loads all 81 agents

### Content & Assets

- [ ] All 6 launch posts below reviewed and ready to copy-paste
- [ ] Promo video exported from PowerPoint (1080p, 2s/slide) or edited in CapCut
- [ ] At least 2-3 screenshots ready for Reddit/Twitter posts
- [ ] Deep Strategy Playbook PDF uploaded to release assets
- [ ] Blog post for Dev.to/Hashnode written from outline (see Day 3)

### Set Up Connections (Dogfooding)

Connect your accounts in **Settings > Connections**:

| Platform   | Flow        | Use Case                          |
|------------|-------------|-----------------------------------|
| Twitter/X  | Token paste | Thread posting, engagement replies |
| LinkedIn   | OAuth       | Professional post, comments        |
| Discord    | Token paste | Community announcements            |
| Telegram   | Token paste | Channel broadcast                  |
| Facebook   | OAuth       | Page post                          |
| Instagram  | OAuth       | Visual teaser (screenshot carousel)|

### Optional: Create a "Launch Campaign" Crew

**Crew settings:**
- **Name:** Launch Campaign — Solo Beta
- **Execution mode:** Sequential
- **Blueprint:** Content Creation Pipeline (or Marketing Campaign)

**Agent team (in order):**
1. **Content Strategist** — Reviews all 6 post drafts, checks messaging consistency
2. **Copywriter** — Adapts base copy per platform tone
3. **Social Media Manager** — Schedules posts, sets optimal posting times
4. **Community Manager** — Monitors replies, drafts engagement responses

### Launch Day Prep

- [ ] Block 3 hours for HN monitoring on Day 1 (respond to every comment)
- [ ] Have talking points ready (see Appendix A below)
- [ ] Keep a tab open on GitHub Issues — respond within 1 hour

---

## DAY 1 — LAUNCH (HN + Twitter + LinkedIn)

### 10:00 AM EST — Hacker News (Show HN)

- [ ] Post submitted
- [ ] Monitor and respond to every comment for 2-3 hours

**Title:** `Show HN: ContextuAI Solo – Open-source desktop AI with 93+ business agents, 35+ local models, runs on your laptop`

**Link:** `https://github.com/contextuai/contextuai-solo`

**Top-level comment:**

Hi HN,

I built ContextuAI Solo because I wanted AI agents for business tasks without sending sensitive data to the cloud.

It's a Tauri v2 desktop app (Rust shell + React frontend) with a FastAPI Python backend bundled as a sidecar process. The interesting technical decisions:

- **Why Tauri over Electron:** ~10x smaller bundle, native performance, Rust-level security. The app is ~80MB installed vs 500MB+ for a typical Electron app.

- **Why SQLite over a cloud DB:** The whole point is local-first. The backend was originally built on MongoDB — I wrote a compatibility layer (motor_compat.py) that translates MongoDB query operators ($set, $in, $regex, etc.) to SQL/JSON expressions. This let me port the entire backend without rewriting every query.

- **Sidecar pattern:** The Python backend is bundled via PyInstaller into a standalone binary. Tauri's Rust shell spawns it on launch, health-checks it, and kills the process tree on exit. On Windows, this includes killing llama-cpp threads via taskkill /T.

- **Local inference:** llama-cpp-python runs 35+ GGUF models on CPU. The model hub includes DeepSeek R1 (7B–70B), Qwen 3.5 (up to 27B), Llama 3.1 8B, Phi-4 14B, Mistral Small 22B, and more. A regular 16GB laptop can comfortably run 8B–14B models. One-click download from HuggingFace. You can also drop any GGUF file into the models folder and it auto-registers.

The 93 agents are defined as markdown files with system prompts, organized by 13 business categories. They're auto-seeded into the local DB on first launch. You can also create your own custom agents.

Beta release — looking for feedback on the UX, agent quality, and which platforms/models people want supported next.

---

### 11:00 AM EST — Twitter/X Thread

- [ ] Thread posted
- [ ] Pin first tweet

**Tweet 1:**
I just open-sourced ContextuAI Solo — a desktop AI assistant with 93+ business agents that runs 100% on your PC.

No cloud. No subscriptions. Your data never leaves your machine.

Here's what it does 🧵👇

#opensource #AI #LocalAI #privacy

**Tweet 2:**
93 pre-built AI agents across 13 business categories:

- C-Suite strategy
- Marketing & sales
- Finance & operations
- HR & legal
- Product & research
- Creative
- Data analytics, IT security, and more

Plus create your own custom agents — define a name, system prompt, and model.

Chain them into multi-agent crews that run sequentially, in parallel, or autonomously.

**Tweet 3:**
35+ local AI models in the built-in Model Hub. No GPU required.

Top picks for a regular laptop:
- DeepSeek R1 7B / 14B — reasoning powerhouse
- Qwen 3.5 9B — latest and greatest
- Llama 3.1 8B — Meta's workhorse
- Phi-4 14B — Microsoft's best small model
- Mistral Small 22B — fits on 16GB RAM

One-click download from HuggingFace. Or connect Anthropic Claude / AWS Bedrock for more power.

#LocalLLM #HuggingFace #LLM #RunLocal #DeepSeek #Qwen #Llama

**Tweet 4:**
Built with modern tech:

- Tauri v2 (Rust) — 10x smaller than Electron
- React 19 + TypeScript
- FastAPI backend as a sidecar
- SQLite for local storage
- llama-cpp-python for inference

Full desktop app: Windows, macOS, and Linux installers.

#TauriApp #Rust #React #FastAPI #devtools

**Tweet 5:**
Who is this for?

- Consultants handling client data
- Solo entrepreneurs who want AI without $20/mo subscriptions
- Privacy-conscious professionals
- Anyone who wants AI agents that work offline

#solopreneur #consulting #dataprivacy #AIagents

**Tweet 6:**
It's open source and free forever.

GitHub: https://github.com/contextuai/contextuai-solo
Website: https://contextuai.com/solo

This is beta — looking for feedback, bug reports, and contributors.

Star ⭐ it if you think local-first AI matters.

#opensource #AI #LocalAI #privacy #buildinpublic #LLM #LocalLLM #AIagents #devtools #IndieHacker #selfhosted

---

### 12:00 PM EST — LinkedIn

- [ ] Post published

I just open-sourced a project I've been building: **ContextuAI Solo** — a desktop AI assistant designed for business professionals who care about data privacy.

**The problem:** Every AI tool today requires sending your sensitive business data — client strategies, financial plans, HR documents — to someone else's servers. For consultants, freelancers, and small business owners, that's often not acceptable.

**The solution:** An AI assistant that runs entirely on your desktop. No cloud dependency. No accounts. No data leaving your machine.

It comes with 93+ pre-built AI agents covering:
- Executive strategy and decision-making
- Marketing campaigns and content creation
- Financial analysis and operations
- HR, legal, and compliance
- Product development and research
- Data analytics, IT security, and more

You can also create your own custom agents with any system prompt and model.

It ships with a Model Hub of 35+ local AI models you can run on your CPU — no GPU needed. DeepSeek R1, Qwen 3.5, Llama 3.1, Phi-4, Mistral — all available with one-click download from HuggingFace. A regular 16GB laptop can run 8B–14B models comfortably. You can also connect cloud providers like Anthropic Claude when you need more capability.

The app is built with Tauri (Rust), React, and Python — resulting in a lightweight, fast desktop experience on Windows, macOS, and Linux.

I've open-sourced it because I believe AI assistants should be accessible to everyone, not locked behind enterprise pricing.

If you're a professional who has been looking for AI tools that respect your data privacy, I'd love your feedback.

GitHub: https://github.com/contextuai/contextuai-solo
Website: https://contextuai.com/solo

#AI #OpenSource #Privacy #Entrepreneurship #Technology #LocalAI #DesktopApp #AIagents #DataPrivacy #Consulting #Freelancer #SmallBusiness #Tauri #React #Python #BuildInPublic

---

### Day 1 End-of-Day

- [ ] Respond to all HN comments
- [ ] Reply to Twitter engagement
- [ ] Reply to LinkedIn comments
- [ ] Check GitHub Issues — respond to any new ones
- [ ] Note bugs reported — fix overnight if possible

---

## DAY 2 — REDDIT PUSH

### 10:00 AM EST — r/LocalLLaMA

- [ ] Post submitted

**Title:** `I built an open-source desktop AI assistant with 93+ business agents that runs entirely on your PC — no cloud required`

**Body:**

Hey everyone,

I've been working on **ContextuAI Solo** — a desktop AI assistant designed for professionals who want AI agents without sending their data to the cloud. It runs 100% locally on your machine with a built-in Model Hub of 35+ GGUF models — DeepSeek R1, Qwen 3.5, Llama 3.1, Phi-4, Mistral, Gemma 3, and more. No API keys required to get started.

**What it does:**

- **93+ pre-built business agents** across 13 categories — C-suite strategy, marketing & sales, finance & operations, HR, legal, product, research, creative, data analytics, IT security, and more
- **Create your own custom agents** — define a name, system prompt, and model to build agents tailored to your workflow
- **Multi-agent crews** — chain agents together in sequential, parallel, pipeline, or autonomous execution modes
- **35+ local AI models** — DeepSeek R1 (7B–70B), Qwen 3.5 (up to 27B), Llama 3.1 8B, Phi-4 14B, Mistral Small 22B, Gemma 3 — one-click download, runs on CPU. A regular 16GB laptop handles 8B–14B models comfortably
- **Cloud providers optional** — also supports Anthropic Claude and AWS Bedrock if you want more power
- **Workflow blueprints** — 10 pre-built templates for strategy, content, marketing, product, and research workflows
- **Platform connections** — integrate with Telegram, Discord, LinkedIn, Twitter/X, Instagram, Facebook

**Privacy-first:**

All your data stays in a local SQLite database on your machine. No telemetry, no cloud sync, no accounts. The app doesn't phone home.

**Tech stack** (for those curious):

- Desktop shell: Tauri v2 (Rust) — ~10x smaller than Electron
- Frontend: React 19 + TypeScript + Tailwind CSS
- Backend: FastAPI (Python) running as a sidecar process
- Local inference: llama-cpp-python on CPU (35+ GGUF models)
- Database: SQLite with async I/O
- Installers: Windows (.msi/.exe), macOS (.dmg), Linux (.deb/.AppImage)

**Screenshots:** [see README on GitHub]

**Links:**

- GitHub: https://github.com/contextuai/contextuai-solo
- Website: https://contextuai.com/solo
- Download: Check the Releases page on GitHub

This is a beta release — I'm actively looking for feedback, bug reports, and contributors. If you run into issues, please open a GitHub issue.

What agents or features would you want to see added?

---

### 11:00 AM EST — r/selfhosted

- [ ] Post submitted (same content as r/LocalLLaMA above)

---

### 12:00 PM EST — r/opensource

- [ ] Post submitted

**Title:** `Open-sourced my desktop AI assistant — 93+ business agents (+ build your own), runs locally, no cloud dependency`

**Body:**

I just open-sourced **ContextuAI Solo**, a desktop AI assistant built for business professionals who want AI agents without the cloud dependency.

**The problem:** Most AI tools require you to send sensitive business data to third-party servers. If you're a consultant, freelancer, or small business owner working with client data, that's a non-starter.

**The solution:** A proper desktop app (not a web wrapper) with a Model Hub of 35+ local AI models — DeepSeek R1, Qwen 3.5, Llama 3.1, Phi-4, Mistral, Gemma 3 — running on your CPU. No GPU needed; a regular 16GB laptop handles 8B–14B models. It comes with 93+ pre-built agents covering strategy, marketing, finance, HR, legal, product, research, creative, data analytics, IT security, and more. Plus you can create your own custom agents.

You can also connect cloud providers (Anthropic, AWS Bedrock) for more capable models when privacy isn't a concern.

**Key features:**
- 93+ business agents ready to use out of the box + create your own
- Multi-agent crews with 4 execution modes
- 35+ local AI models (DeepSeek R1, Qwen 3.5, Llama 3.1, Phi-4, Mistral, Gemma 3)
- 10 workflow blueprint templates
- Social platform connections (Telegram, Discord, LinkedIn, Twitter/X, Instagram, Facebook)
- Windows, macOS, and Linux installers

**Built with:** Tauri v2 + React 19 + FastAPI + SQLite

It's in beta — feedback and contributions welcome.

- GitHub: https://github.com/contextuai/contextuai-solo
- Website: https://contextuai.com/solo

---

### Day 2 End-of-Day

- [ ] Respond to all Reddit comments
- [ ] Cross-check: any Reddit feedback that needs a GitHub issue?
- [ ] Post update on Twitter if you fixed bugs from Day 1 feedback
- [ ] Check GitHub traffic insights — note which platforms drive stars

---

## DAY 3 — LONG TAIL (Reddit + Discord + Blog)

### 10:00 AM EST — r/artificial

- [ ] Post submitted (same content as r/opensource above)

---

### 11:00 AM EST — Discord Communities

- [ ] Post in relevant AI/open-source Discord servers (custom short message)

---

### 12:00 PM EST — Dev.to / Hashnode Blog Post

- [ ] Blog post published

**Title:** How I Built a Desktop AI Assistant with 93+ Agents and 35+ Local Models Using Tauri, React, and FastAPI

**Outline:**

### Introduction
- The problem with cloud-first AI tools
- Why local-first matters for business professionals

### Architecture Overview
- Three-layer desktop app: Tauri (Rust) > React SPA > FastAPI sidecar
- Why Tauri over Electron (bundle size, performance, security)
- The sidecar pattern: bundling Python with PyInstaller

### The MongoDB-to-SQLite Migration
- Why we moved from MongoDB to SQLite
- Building a compatibility layer that preserves the Motor API
- Translating MongoDB query operators to SQL/JSON

### Agent Library Design
- 93+ agents as markdown files + custom agent builder
- System prompts, model recommendations, tool configs
- Auto-seeding on first launch

### Local AI Inference
- llama-cpp-python for 35+ GGUF models on CPU (DeepSeek R1, Qwen 3.5, Llama 3.1, Phi-4, Mistral, Gemma 3)
- Model Hub with one-click download from HuggingFace
- Auto-registration of custom GGUF files dropped into models folder
- Async lock to prevent concurrent model access

### Multi-Agent Crews
- Sequential, parallel, pipeline, autonomous modes
- Workspace orchestration with job queues
- Checkpoint/resume for long-running workflows

### Lessons Learned
- Desktop app distribution is harder than web
- PyInstaller bundling challenges
- Cross-platform CI/CD with GitHub Actions

### Try It Yourself
- GitHub link, download instructions
- Call for contributors

---

### Day 3 End-of-Day

- [ ] Respond to r/artificial comments
- [ ] Respond to Discord engagement
- [ ] Share blog post link on Twitter and LinkedIn as a follow-up

---

## SOON — POST-LAUNCH (Week 1)

- [ ] Respond to every GitHub issue within 24 hours
- [ ] Post update threads on Reddit/Twitter when fixing bugs reported by community
- [ ] Check GitHub traffic insights daily — note which platforms drive stars
- [ ] Collect user feedback themes — prioritize top 3 for next release
- [ ] Prepare a "thank you" follow-up post for Reddit/Twitter after initial traction
- [ ] Screenshot the launch process if dogfooding through Solo (crew builder, agent copy, connections page, crew execution)
- [ ] Track launch metrics in a Workspace Project:
  - GitHub stars over 7 days
  - GitHub issues opened (bugs vs features)
  - Download count from Releases page
  - Top referring platforms
  - Community feedback themes

---

## APPENDIX A — Talking Points for Replies

Use these when responding to comments across platforms:

| Topic | Response |
|-------|----------|
| **Privacy** | "All data stays on your machine — SQLite, no telemetry, no cloud sync" |
| **Performance** | "35+ models in the Model Hub. A regular 16GB laptop runs DeepSeek R1 14B or Qwen 3.5 9B comfortably on CPU — no GPU needed" |
| **vs ChatGPT/Claude** | "Unlike ChatGPT/Claude web, your data never leaves your device" |
| **Pricing** | "Free and open source, forever. No enterprise upsell bait" |
| **Installation issues** | Link to GitHub Issues, respond within 1 hour |
| **Feature requests** | "Great idea — please open a GitHub Discussion so we can track it" |
