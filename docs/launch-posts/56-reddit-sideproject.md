# Reddit — r/SideProject

**Target:** Indie builders and side project makers

---

**Title:** My side project: a desktop AI assistant with 93+ business agents that runs entirely on your laptop — just open-sourced it

**Body:**

Been working on **ContextuAI Solo** for the past several months. Just open-sourced it.

**What it is:** A desktop app with 93+ AI business agents and 35+ local models. Everything runs on your machine — no cloud, no subscriptions.

**Why I built it:** I'm a solo founder and I was tired of paying $20/mo each for ChatGPT, Claude, and other tools. I also didn't love sending client data to third-party servers. So I built my own.

**The journey:**
- Started as a cloud app with MongoDB
- Pivoted to local-first desktop app
- Wrote a MongoDB-to-SQLite compatibility layer instead of rewriting 5000 lines of backend code
- Built the whole thing with Claude Code (Anthropic's AI coding tool)
- Shipped Windows, macOS, and Linux installers

**What I learned:**
1. Desktop app distribution is WAY harder than web
2. PyInstaller bundling has quirks on every platform
3. Cross-platform CI/CD with GitHub Actions requires patience
4. Claude Code can genuinely replace a small engineering team for a solo developer

**Features:**
- 93+ pre-built business agents (strategy, marketing, finance, ops, HR, legal, product, research)
- Create your own custom agents
- Multi-agent crews with 4 execution modes
- 35+ GGUF models on CPU — no GPU needed
- ~80MB installed (Tauri v2, not Electron)

GitHub: https://github.com/contextuai/contextuai-solo

Happy to answer questions about the tech stack, the build process, or using Claude Code for a project this size.
