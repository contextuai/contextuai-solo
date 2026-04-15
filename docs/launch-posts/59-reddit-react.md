# Reddit — r/reactjs

**Target:** React developers

---

**Title:** Built a desktop AI app with React 19 + TypeScript + Tauri v2 — SSE streaming, 93+ agents, dark mode system

**Body:**

Sharing my React architecture for **ContextuAI Solo**, a desktop AI assistant running inside Tauri v2.

**Frontend stack:**
- React 19 + TypeScript strict mode
- Vite (dev server on port 1420)
- Tailwind CSS with custom design tokens
- `@/` path alias → `./src/`

**Interesting patterns:**

**1. Dual transport layer (`lib/transport.ts`):**
```
Tauri mode: React → Tauri IPC (api_request command) → HTTP to Python sidecar
Dev mode: React → direct HTTP fetch to http://127.0.0.1:18741/api/v1
```
One `transport.ts` handles both. In production, requests go through Rust IPC. In dev, they hit the backend directly. The React components don't know the difference.

**2. SSE streaming for AI chat:**
Streaming always goes over HTTP (not IPC) because Tauri IPC isn't designed for long-lived connections. `streamRequest()` in `transport.ts` handles SSE consumption with `AbortSignal` for cancelling mid-stream.

**3. camelCase/snake_case bridge:**
Backend returns camelCase (`messageType`, `messageId`), frontend types use snake_case (`message_type`, `message_id`). `normalizeMessage()` in `lib/api/chat-client.ts` handles the translation.

**4. Dark mode with custom tokens:**
Tailwind `class` strategy with custom color tokens: `primary` (orange), `secondary` (sky blue), `dark` (zinc). `cn()` utility for conditional classes.

**5. Multi-step wizards:**
Crew builder is a 5-step wizard (details → execution mode → agent team → connections → review). Persona creator is a 2-step wizard (type selection grid → configuration).

**Component count:** 100+ components across `routes/`, `components/ui/`, and feature-specific directories.

Open source: https://github.com/contextuai/contextuai-solo

Happy to discuss any of these patterns.
