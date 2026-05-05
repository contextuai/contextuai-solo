# Solo Revision: Consolidation + Automations + Coder Mode

**Status:** Draft for review
**Created:** 2026-05-05
**Author:** Nagendra Rao Jogi (with Claude)
**Scope:** App-shell + IA refactor + new product mode. Roughly 7 PRs over ~6–8 weeks.

---

## 1. Problem statement

ContextuAI Solo today ships 10 sidebar surfaces with **four overlapping nouns** (Agents, Personas, Crews, Workspace) that confuse new users. Phase 3 successfully unified Connections + Distributions on the channel side; the same collapse hasn't happened on the agent side.

Separately, Solo today has **no low-friction authoring path**. Crews require a 7-step wizard. Chat is conversational only — no way to fire `"@researcher pull stats then @writer turn it into a blog post"` and have it run.

Separately again, Solo has **no software-building surface**. The category demand (Codex, Claude Desktop Code, Cursor, Bolt, Lovable, Replit Agent) is proven but every option is cloud-hosted and subscription-priced. Solo is uniquely positioned to ship a **local, free, business-user-friendly** equivalent.

This spec consolidates the four nouns, adds a natural-language **Automations** surface, and introduces a second app mode — **Coder** — selected via a top-center toggle.

---

## 2. Goals

- **Reduce concept count.** From {Agents, Personas, Crews, Workspace} → {Crews, Automations}. Agents become a library/picker, Personas become an agent-type tag, Workspace folds into Crews → Runs.
- **Add a natural-language fast path.** `@mention`-driven Automations with PDF/PPTX/file/email/webhook/channel outputs.
- **Introduce Coder as a co-equal product surface** via app-shell mode toggle. Solo + Solo Coder, one install, all local.
- **Sharpen the wedge.** "Build software, automations, agents, knowledge — all locally, free forever — vs $20/mo per cloud tool."

## 3. Non-goals

- Multi-mode beyond two (no third mode in v1).
- Solo Coder as a Cursor/IDE replacement. No LSP, no debugger, no file-tree-as-primary-rail, no multi-tab editor.
- Backwards-compatible URLs for retired routes beyond one release cycle of redirects.
- Cloud sync between machines (Solo stays local-only).
- Mobile companion app.

## 4. Mental model after the change

- **Solo mode** — your AI assistant. Chat, Knowledge, Automations, Crews, Approvals, Distributions, Settings.
- **Coder mode** — your AI software builder. Projects, Running, Templates, Models, Settings.
- **Toggle** — top-center segmented control in the title bar. `Cmd/Ctrl+Shift+M`. Last mode persists.
- **Shared substrate** — one FastAPI sidecar, one local-model engine, one agent library, one KB system. Both modes read from the same backend.

---

## 5. Sidebar after the change

### Solo mode (10 → 8)

| Today (10) | After (8) |
|---|---|
| Chat | Chat |
| Knowledge | Knowledge |
| Agents | *folded into Crew/Automation pickers* |
| Personas | *folded into Agents — surfaced as **tabs** by kind in the picker* |
| Crews | Crews *(tabbed: Crews / Projects / Runs)* |
| Workspace | *folded into Crews → Projects + Runs tabs* |
| Approvals | Approvals |
| Distributions | Distributions |
| Models | Models *(stays in sidebar — daily-use surface)* |
| Settings | Settings |
| — | **Automations** ⭐ NEW |

### Coder mode (5, all new)

- **Projects** — list of code projects (folder + chat history + run state)
- **Running** — live process list across projects
- **Templates** — starter scaffolds (Web App, Telegram Bot, CLI Tool, …)
- **Models** — local + cloud model picker (Coder-tuned defaults)
- **Settings** — Coder-specific (allowlist, network policy, default model)

---

## 6. Feature specs

### 6.1 App-shell mode toggle (PR 5)

**UI**
- Segmented pill control, ~140px wide, anchored top-center of the Tauri title bar.
- Two segments: `Solo` / `Coder`. Active segment fills with primary color.
- Click → 150ms cross-fade between mode roots. State preserved per mode.
- `Cmd+Shift+M` (macOS) / `Ctrl+Shift+M` (Windows/Linux) toggles modes.
- Last mode persists in localStorage (`solo.app.mode`).
- Window title updates: `ContextuAI Solo` ↔ `Solo Coder — <project-name>`.

**Routing**
- Top-level routes namespaced: `/solo/*` and `/coder/*`.
- Mode-router at `App.tsx` reads the persisted mode and lazy-loads the corresponding bundle.
- Each mode owns its own React Router instance.

**File layout (frontend)**
```
frontend/src/
├── shell/
│   ├── ModeToggle.tsx
│   ├── ModeProvider.tsx
│   └── window-title.ts
├── solo/
│   ├── App.tsx                     ← what's at App.tsx today
│   └── routes/                     ← existing routes move here
├── coder/
│   ├── App.tsx
│   └── routes/
│       ├── projects.tsx
│       ├── project.tsx
│       ├── running.tsx
│       └── templates.tsx
└── App.tsx                         ← thin mode-router shell
```

**Native menu**
- File menu adapts per mode. Solo: New Chat / New Crew / Import KB. Coder: New Project / Open Folder / Run.

**Acceptance**
- Toggle visible top-center in both modes.
- Cmd/Ctrl+Shift+M switches modes on macOS and Windows.
- Window title updates within 100ms of mode change.
- Refreshing the app restores the last-used mode.
- Coder mode shows a "Coming soon" splash if PR 6 hasn't shipped yet — toggle still works.

---

### 6.2 Automations (PR 1)

**Concept**
A new sidebar surface in Solo mode. Single textarea where user writes natural-language workflows using `@agent` mentions, picks output actions, hits Run.

**Authoring UI** (`/solo/automations`)
```
┌──────────────────────────────────────────────────┐
│ New Automation                              [×]  │
├──────────────────────────────────────────────────┤
│ Name: [Weekly LinkedIn post                  ]   │
│                                                   │
│ Prompt:                                           │
│ ┌──────────────────────────────────────────────┐ │
│ │ @market-researcher pull AI startup funding   │ │
│ │ for last 30 days, then @blog-writer turn it  │ │
│ │ into a 600-word post, then @editor proof it. │ │
│ └──────────────────────────────────────────────┘ │
│                                                   │
│ Detected: market-researcher, blog-writer, editor │
│ Mode: ◉ Sequential  ○ Parallel  ○ Smart          │
│                                                   │
│ Output to:                                        │
│  ☑ Generate PDF                                   │
│  ☐ Generate PPTX                                  │
│  ☑ Distribute → LinkedIn (configured)             │
│  ☐ Webhook                                        │
│                                                   │
│ Trigger: ◉ Manual ○ Scheduled (cron)              │
│                                                   │
│ [Validate]  [Save Draft]  [Run]                   │
└──────────────────────────────────────────────────┘
```

**Backend (port from `C:\Users\nagen\Projects\contextuai\backend`)**
- `services/automation_engine.py` — orchestrator, ports the existing implementation, replaces Bedrock/Cognito-specific bits with Solo's local-model service.
- `services/automation_executor.py` — step runner.
- `services/automation_output_service.py` — PDF (reportlab/weasyprint), PPTX (python-pptx), file save, email, webhook.
- `services/automation_parser.py` — `@mention` extraction. Use regex first; optional Claude Agent SDK / local-model pass for execution-mode inference.
- `repositories/automation_repository.py`, `repositories/automation_execution_repository.py`.
- `routers/automations.py` — CRUD + `/run` + `/validate` + `/executions` + `/executions/{id}/stream` (SSE).
- `models/automation_models.py` — adapt enterprise version; drop `user_id` (single-user).

**Frontend**
- `solo/routes/automations.tsx` — list + builder + run history
- `solo/components/automations/automation-builder.tsx`
- `solo/components/automations/output-action-picker.tsx` — reads from `/api/v1/connections` (Distributions aggregator).
- `solo/lib/api/automations-client.ts`

**Save-as-Crew bridge**
- "Promote to Crew" button on any Automation → creates a Crew with the same agents, output bindings (as `connection_bindings[]` outbound), and the Automation's prompt as Step 1 system prompt.

**Acceptance**
- User writes `@agent` prompt → validates → runs → sees step-by-step execution → gets PDF in `~/.contextuai-solo/files/`.
- Output picker shows configured Distributions inline; unconfigured ones show "Configure" link.
- Run history shows successful/failed runs with step traces.
- Automation can be promoted to a scheduled Crew with one click.

---

### 6.3 Personas → Agent types (PR 2)

**Schema migration** (`backend/migrations/0003_personas_to_agent_types.py`)
- Add `kind: "prompt" | "database" | "web" | "mcp" | "api" | "file"` to `workspace_agents` documents.
- For each existing persona record, create a corresponding `workspace_agents` document with `kind` set from the persona type, and copy credentials/config into agent fields.
- Idempotent, dry-run capable, version-marked.

**Frontend**
- Delete `solo/routes/personas.tsx` (after one Coming Soon release).
- Agent library picker (used in Crew builder, Automation builder) is **tabbed by kind**, not chip-filtered. Tab row: `Prompt | Database | Web | MCP | API | File`. Each tab is its own catalog with kind-specific empty state, kind-specific "Add new" CTA, and kind-specific columns (e.g., Database tab shows connection-string preview; Prompt tab shows the system-prompt opening line).
  - Rationale: a Postgres connection and a system-prompt agent are *categorically* different things, not two values of one filterable list. A tab makes the mode-of-operation visible; a filter chip flattens them into "just narrow this list."
  - Selected tab persists in localStorage per builder context.
- "Add Agent" flow opens directly into the active tab's kind (no separate kind-selector step needed — the tab IS the selector).

**Acceptance**
- Existing personas appear under the correct kind tab.
- Crews referencing an old persona ID still resolve (migration preserves IDs).
- `/solo/personas` redirects to `/solo/agents?kind=...` for one release; then 404s.
- Default tab on first open is `Prompt` (the most common case); subsequent opens restore the last-used tab.

---

### 6.4 Workspace → Crews Runs (PR 3)

**Schema migration** (`backend/migrations/0004_workspace_to_crew_runs.py`)
- Add `kind: "crew" | "project"` to `crews` documents (default `"crew"`).
- For each `workspace_projects` row, create a `crews` row with `kind="project"` and copy fields.
- For each `workspace_jobs` row, create a `crew_runs` row with `trigger_type="manual"` (default) and copy execution data.
- Idempotent, dry-run capable, version-marked.

**Frontend**
- Delete `solo/routes/workspace.tsx`.
- Crews page becomes **tabbed**: `Crews | Projects | Runs`. Three top-level tabs at the page header, not a filter chip.
  - Rationale: a Crew (recurring multi-agent automation, channel-bound, scheduled) and a Project (one-shot workspace job, manual trigger) have different mental models, different list columns, different empty states, different "New" CTAs. A filter chip suggests "same thing, narrowed"; a tab signals "different mode of this module."
  - `Runs` tab spans both kinds and shows a `kind` badge per row (Crew / Project) plus filters by status/date.
  - Selected tab persists in localStorage; deep-link via `/solo/crews?tab=projects`.
- Each tab gets its own toolbar: Crews tab has "New Crew" + blueprint picker; Projects tab has "New Project" + blueprint picker; Runs tab has filter controls only.

**Acceptance**
- All existing workspace projects appear under the Projects tab.
- All workspace jobs appear in the Runs tab with the correct kind badge.
- `/solo/workspace` redirects to `/solo/crews?tab=projects` for one release.
- Deep-linking each tab works (`?tab=crews|projects|runs`).

---

### 6.5 Dead-code cleanup, Models stays in sidebar (PR 4)

**Decision:** Models is a daily-use surface (download / sync / pick local GGUFs). Burying it inside Settings adds clicks for the most common path. Keep it in the sidebar.

**Frontend**
- Models stays at `/solo/models`, sidebar entry retained.
- Delete `frontend/src/routes/distribution.tsx`, `frontend/src/routes/schedule.tsx` (Phase 3 cleanup carryover).
- Delete `frontend/src/routes/agents.tsx` (replaced by tabbed picker inside Crew/Automation builders — see §6.3).
- Update navigation E2E test: **8 sidebar items** in Solo mode.

**Optional: Library hub** (`/solo/library`) — **deferred**
- Read-only aggregator (agents-by-kind, blueprints, RAG packs, crew templates, model catalog).
- Defer to a later PR. Browsing is currently solved by the tabbed pickers in §6.3 and §6.4; a separate hub adds a surface without clear payoff for v1.

**Acceptance**
- Solo sidebar shows exactly **8 items**: Chat, Knowledge, Automations, Crews, Approvals, Distributions, Models, Settings.
- `/solo/models` works as today.
- Old routes (`distribution`, `schedule`, `agents`) 404 cleanly (or redirect for one release).
- E2E navigation test asserts 8 items.

---

### 6.6 Coder MVP (PR 6)

**Concept**
A new top-level mode. Chat-driven software building inside a scoped folder, with one-click run and embedded preview. Audience: business users, prosumers, solo founders — not developers with VS Code open.

**Layout** (`/coder/projects/<id>`)
```
┌─────────────────────────────────────────────────────────────────┐
│ ◉ Solo  ○ Coder                         Solo Coder — telegram-bot│
├─────────────────────────────────────────────────────────────────┤
│ [Projects ▼]  [Run ▶] [Stop ■] [Open Folder] [...]              │
├──────────────────────────┬──────────────────────────────────────┤
│ Chat                      │  Preview                             │
│                           │  ┌────────────────────────────────┐ │
│ "build me a telegram bot  │  │ localhost:3000                  │ │
│  that posts daily crypto  │  │                                  │ │
│  prices at 9am"           │  │ <iframe of running app>          │ │
│                           │  │                                  │ │
│ ▶ scaffolded 4 files      │  └────────────────────────────────┘ │
│ ▶ ran npm install         │  Files (4) ▼                         │
│ ▶ ready to run            │  • bot.ts      [Edit] [Review]       │
│                           │  • cron.ts     [Edit] [Review]       │
│ ▼ Run output              │  • prices.ts   [Edit] [Review]       │
│ Bot listening on :3000    │  • package.json                      │
│                           │                                       │
│ [Type to keep building... ] │                                     │
└──────────────────────────┴──────────────────────────────────────┘
```

**Project model**
```python
class CoderProject(BaseModel):
    project_id: str
    name: str
    folder_path: str               # absolute, user-picked
    template_id: Optional[str]
    runtime: Literal["node", "python", "static", "auto"]
    created_at: str
    updated_at: str
    last_run_at: Optional[str]
    chat_thread_id: str            # links to existing chat infrastructure
    trusted: bool                  # false until user grants per-project trust
    network_policy: Literal["allow", "block"]
```

**Templates** (4 starters in v1)
1. **Web App** — Vite + React + TypeScript, hot reload at localhost:5173.
2. **Telegram Bot** — Node.js + grammy, reads token from `.env`.
3. **CLI Tool** — Python + click, `python main.py --help`.
4. **Static Site** — plain HTML/CSS/JS landing page, served by a tiny dev server (`python -m http.server` or `npx serve`) → :8080. Lowest-skill template; the "I just want a webpage" entry point.

Each template = folder under `coder-templates/<id>/` + `manifest.json` (name, description, runtime, init commands, initial chat prompt).

**File operations** (Tauri FS plugin)
- Scoped to `project.folder_path`.
- Diff-based file edits — model returns full new content; backend computes diff; UI shows old/new side-by-side; user clicks "Apply" or "Undo."
- No per-hunk approval (different reference frame from IDE pair-programmer).

**Run pane**
- Detects project type (`package.json` → node, `requirements.txt` → python, `index.html` → static).
- "Run" button picks the right command (`npm run dev`, `python main.py`, etc.).
- `tauri-plugin-shell` with allowlisted binaries, scoped CWD.
- Streams stdout/stderr into the run pane in realtime.
- Detects `localhost:PORT` in stdout → enables embedded preview iframe.

**Trust & security**
- Project created in `untrusted` state.
- First run prompts: *"Allow Solo Coder to read, write, and run commands in `<folder>`?"*
- Granted = autonomous within the folder.
- Allowlist (default): `node`, `npm`, `npx`, `pnpm`, `bun`, `python`, `python3`, `pip`, `pipx`, `pytest`, `git`, `cargo`, `rustc`, `go`. Extensible via Settings.
- Network: on by default (npm install needs it). Settings → Coder → "Block outbound" toggle.
- Coder mode can be disabled entirely in Settings (kill switch).
- Capabilities config: extend `frontend/src-tauri/capabilities/` with a Coder-specific capability file.

**Coder-companion agents (NEW — none exist today)**
Per BL-2 in TODO, these need to be authored:
- `coder-companion/code-reviewer.md`
- `coder-companion/bug-analyzer.md`
- `coder-companion/test-writer.md`
- `coder-companion/doc-generator.md`
- `coder-companion/refactor-advisor.md`

These are Coder-mode agents (different `kind` — `kind="coder"`) and don't show up in Solo's library.

**Note:** the existing 12 `agent-library/engineering/` agents are *domain specialists* (Data Engineer, ML Engineer, Mobile Developer, etc.), **not** coding tooling agents. They can optionally surface in Coder mode as "advisor" personas the user can chat with about architecture decisions, but they are not the same as the coder-companion set.

**Backend**
- `routers/coder_projects.py` — CRUD + `/{id}/run` + `/{id}/stop` + `/{id}/files` + `/{id}/files/{path}` (read/write/diff).
- `routers/coder_run.py` — process lifecycle, stdout SSE stream.
- `services/coder_project_service.py` — project ops, trust state, allowlist enforcement.
- `services/coder_run_service.py` — wraps `tauri-plugin-shell` invocation via existing IPC bridge.
- `services/coder_template_service.py` — scaffolds template into folder.
- `repositories/coder_project_repository.py`, `coder_run_repository.py`.
- `models/coder_models.py`.

**Acceptance**
- User picks "Web App" template → folder picker → project scaffolds → chat opens with a starter prompt.
- "Build a counter component" → model edits files → user clicks Apply → Run → preview iframe shows the running app.
- "Diagnose this error" with build failure pasted → bug-analyzer agent responds with fix.
- Trust prompt appears once per project, not per command.
- Settings → Coder → "Disable Coder mode" hides the toggle and routes `/coder/*` to Solo.
- All four templates (Web App, Telegram Bot, CLI Tool, Static Site) work end-to-end on Windows + macOS.

---

### 6.7 Cross-mode handoffs (PR 7)

**Scope discipline:** every handoff added is a surface to maintain. Ship the high-leverage ones, skip the rest.

| From → To | Affordance | Status |
|---|---|---|
| Coder project → Solo | Project menu: *"Index as KB"* — registers the project folder as a KB folder source, reusing the existing Personal Docs pipeline (no new code path; just a one-click wrapper around the existing folder-mapping flow). | **Ship** — cheapest high-value handoff |
| Coder project → Solo | Project menu: *"Distribute artifact"* — push build output to the Distributions picker (LinkedIn, email, blog, Slack, etc.). | **Ship** |
| Solo Automation → Coder | New output action `run_coder_project` (invoke a Coder project headlessly, return artifacts). | **Ship** |
| Solo Crew → Coder | Crew step type "Run Coder project" — references a project by ID. | **Ship** |
| Coder error → Solo chat | "Diagnose with @bug-analyzer" — opens Solo chat with error pre-loaded and agent pre-selected. | **Ship** |
| Coder error → Solo Crew | "Send error to crew" → pick a Crew → trigger a one-shot run. | **Defer** — adds picker friction, no clear payoff over the chat bridge for v1. Revisit if users ask for it. The crew bridge already exists in the other direction (Crew step → Coder project), so the asymmetry is acceptable. |

**Backend**
- `services/coder_run_service.py::run_headless()` — runs a project without UI, captures artifacts.
- New `OutputActionType.RUN_CODER_PROJECT` in automation models.
- New crew step type `coder_project` in crew models.
- "Index as KB" reuses `services/personal_docs_service.py` — no new ingestion path. The Coder project menu just calls the existing folder-source create endpoint with the project folder.

**Frontend**
- Project menu items + corresponding handoff modals.
- Automation builder gets the new output type.
- Crew builder Step 3 gets the new step type.

**Acceptance**
- Solo Automation can be configured to run a Coder project as one of its steps; output artifacts flow back into the Automation result.
- "Index as KB" creates a KB folder source pointing at the project folder; subsequent chats can RAG against project code.
- Error → chat works; error → crew is intentionally not present (deferred per scope discipline above).

---

## 7. Migration plan

| Migration | What | When |
|---|---|---|
| `0003_personas_to_agent_types.py` | Persona docs → workspace_agents with `kind` field | PR 2 |
| `0004_workspace_to_crew_runs.py` | workspace_projects/jobs → crews/crew_runs with `kind` | PR 3 |

Both follow the `0002_unify_connections.py` pattern: idempotent, `MIGRATE_DRY_RUN=1` capable, version-marked in a migrations tracking collection.

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Mode toggle invites "what about a third mode?" | Hard line in this spec: two modes only for v1. |
| Local code-model quality lags Codex | Recommend Qwen 2.5 Coder 32B / DeepSeek R1 14B; allow cloud opt-in (Anthropic/Bedrock) when user provides keys; honest UI labels. |
| Tauri shell exec is a real security surface | Per-project trust grant, allowlist, scoped paths, kill switch, default-block-network toggle. Document threat model. |
| Coder MVP scope creep into IDE territory | Hard non-goals listed in §3. Pointer to OpenAI-compat router + VS Code for users wanting that path. |
| Confusion vs enterprise ContextuAI repo | Marketing line: Solo Coder = "build your own software locally for free." Enterprise = engineering team platform. Different audiences, different repos. |
| Migration miswires old personas/workspace projects | Dry-run mode that emits diff JSON before real run. Surface unmigrated items in a startup banner. |
| Authoring 5 new coder-companion agents is content work | Treat as part of PR 6 scope; review-quality bar matches the 96 business agents. |
| `/coder/*` routes break if Coder PR slips | PR 5 ships shell with "Coming soon" splash; toggle works regardless. |

## 9. PR sequence

| PR | Scope | Effort | Risk |
|---|---|---|---|
| 1 | Automations MVP | 1 wk | Low |
| 2 | Personas → Agent types | 3 days | Medium |
| 3 | Workspace → Crews Runs | 3 days | Medium |
| 4 | Models → Settings, dead-code cleanup, optional Library hub | 2 days | Low |
| 5 | App-shell mode toggle (Coder = "Coming soon" splash) | 1 wk | Medium |
| 6 | Coder MVP — Projects, Run, Preview, 3 templates, 5 companion agents | 2–3 wks | High |
| 7 | Cross-mode handoffs | 4 days | Medium |

Total: roughly **6–8 weeks** end-to-end, parallelizable in places.

## 10. Open questions

### Decided 2026-05-05
- **Models stays in sidebar** — daily-use surface, not buried in Settings. Sidebar count revised 10 → 8 (not 7).
- **Library hub deferred** — tabbed pickers in §6.3 / §6.4 cover discoverability for v1.
- **Mode toggle top-center** — confirmed, no change.
- **Personas / Workspace tabs, not filter chips** — categorical differences in mental model warrant tabs.
- **4 starter templates in v1** — added Static Site as the lowest-skill entry point.
- **Error → Crew handoff deferred** — error → chat ships, error → crew skipped. Risk of feature overload acknowledged.

### Still open
1. **Coder templates beyond the initial 4** — which order next? Discord Bot, Data Dashboard, Scheduled Script, REST API are candidates.
2. **Cross-mode integration in PR 6 vs PR 7** — fold the cheapest handoff (KB indexing of a Coder project) into PR 6 so Coder doesn't ship feeling isolated?
3. **Marketing positioning** — Solo + Solo Coder as two cards on the marketing site, or one product with a mode toggle? Naming affects install/onboarding copy.

---

*This spec lives in `docs/superpowers/specs/`. Track work in `TODO.md` under Phase 4. Each PR gets its own implementation plan in `docs/superpowers/plans/` once approved.*
