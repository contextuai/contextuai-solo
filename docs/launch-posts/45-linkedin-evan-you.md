# LinkedIn — Evan You / Frontend DX

**Target:** Comment on Evan You's LinkedIn posts about frontend tools, DX, or open-source

---

The frontend DX for desktop apps has quietly become excellent.

Built ContextuAI Solo with:
- **Vite** — sub-second HMR even inside a Tauri desktop shell
- **React 19** — concurrent features for smooth streaming UI
- **TypeScript strict mode** — caught dozens of runtime bugs at compile time
- **Tailwind CSS** — custom design tokens (primary/secondary/dark) with class-based dark mode
- **Path aliases** (`@/` → `./src/`) — clean imports across 100+ components

The Vite + Tauri dev experience deserves more attention. Hot reload works flawlessly — edit a component, see it update in the desktop window instantly. No Electron dev server lag.

SSE streaming for real-time AI chat with AbortController for mid-stream cancellation. The frontend handles 35+ local AI models and 93+ business agents with a responsive, native-feeling UI.

~80MB installed. The entire frontend builds in seconds.

Open source: https://github.com/contextuai/contextuai-solo
