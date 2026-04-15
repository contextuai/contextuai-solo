# gstack-Inspired Features for ContextuAI Solo

Features identified from [garrytan/gstack](https://github.com/garrytan/gstack) that can enhance ContextuAI Solo's agent execution, learning, and UX.

---

## P0 — Foundational (Do First)

### 1. Structured Completion Statuses & Escalation

**Problem**: Agents run with `max_turns=30` but report only success/fail. No nuance, no escalation when stuck.

**Solution**: Add structured terminal statuses to every agent and crew run.

**Statuses**:
- `DONE` — completed successfully
- `DONE_WITH_CONCERNS` — completed but flagged issues (e.g., low confidence output, partial results)
- `BLOCKED` — cannot proceed, needs external input or missing dependency
- `NEEDS_INPUT` — requires user decision before continuing

**Escalation Rules**:
- If an agent fails on the same subtask 3 times, stop and surface to user (3-strike rule)
- If an agent produces empty output, mark as `DONE_WITH_CONCERNS` with a note
- If a checkpoint times out, mark run as `BLOCKED` (not silently failed)

**Files to modify**:
- `backend/services/workspace/agent_runner.py` — add status reporting
- `backend/services/workspace/orchestrator.py` — handle escalation logic
- `backend/services/crew_orchestrator.py` — same for crew runs
- `backend/models/` — add `CompletionStatus` enum
- `frontend/src/components/workspace/project-results.tsx` — render status badges
- `frontend/src/components/crews/crew-run-progress.tsx` — render status badges

---

### 2. Workspace Learnings System

**Problem**: Agents don't learn from past runs. The same mistakes repeat. Crew memory is per-crew only.

**Solution**: Add a workspace-level learning system that persists across all agent and crew runs within a workspace.

**Design**:
- Storage: New `workspace_learnings` collection in SQLite
- Schema per learning:
  - `id`, `workspace_id`, `skill` (agent name), `type` (operational | pitfall | pattern | preference)
  - `key` (short identifier for dedup), `insight` (the learning)
  - `confidence` (1-10), `source` (observed | inferred | user-stated)
  - `created_at`, `updated_at`, `files[]` (related file paths)
- Dedup: latest entry wins per `key + type` pair
- Confidence decay: -1 point per 30 days for observed/inferred learnings
- Max 200 learnings per workspace
- User-stated learnings never decay

**Post-Run Reflection**:
After every agent/crew run, add a reflection step:
1. Extract what succeeded vs. failed
2. Note any unexpected behaviors or outputs
3. Log as learnings with appropriate confidence

**Surfacing**:
Before each agent execution, query relevant learnings (by agent category, workspace, recent file paths) and inject as context: "Prior learnings for this workspace: ..."

**Files to create/modify**:
- `backend/services/workspace/learning_service.py` — new service
- `backend/repositories/learning_repository.py` — new repository
- `backend/services/workspace/agent_runner.py` — inject learnings + post-run reflection
- `backend/services/crew_orchestrator.py` — inject learnings + post-run reflection
- `backend/routers/workspace.py` — API endpoints for viewing/managing learnings
- `frontend/src/components/workspace/` — learnings viewer UI

---

## P1 — Quality Improvements (Do Second)

### 3. Adaptive Agent Dispatch

**Problem**: In crews, all configured agents always run regardless of relevance. Wastes tokens and time.

**Solution**: Track agent usefulness and conditionally skip low-value agents.

**Design**:
- After each agent run in a crew, score its output (empty = 0, generic/short = 1-3, substantive = 4-7, critical = 8-10)
- Store per-agent effectiveness score in crew memory
- If an agent scores 0 in 5+ consecutive runs for a crew, flag it as candidate for removal
- In autonomous mode, the coordinator can use effectiveness history to prioritize which agents to invoke
- UI: show effectiveness badges on agent cards in crew detail view

**Files to modify**:
- `backend/services/crew_orchestrator.py` — add scoring after each agent run
- `backend/services/crew_memory_service.py` — store effectiveness data
- `frontend/src/components/crews/crew-detail` — show effectiveness stats

---

### 4. Structured Question UX for Checkpoints

**Problem**: Checkpoints pause the agent but don't provide structured context for the user's decision.

**Solution**: Standardize checkpoint questions using gstack's AskUserQuestion format.

**Format**:
1. **Re-ground**: "You're running [agent name] in [project name] on branch [X]"
2. **Simplify**: Plain English summary of what's happening and why input is needed
3. **Recommend**: Suggested option with confidence/completeness score
4. **Options**: Lettered choices (A, B, C...) with clear consequences

**Implementation**:
- Add a `structured_question` field to the checkpoint model
- Build a `format_checkpoint_question()` utility that agents call when creating checkpoints
- Frontend renders structured questions with clickable option buttons

**Files to modify**:
- `backend/services/workspace/checkpoint_service.py` — add structured question support
- `backend/models/` — update checkpoint model
- `frontend/src/components/workspace/` — checkpoint UI with option buttons

---

### 5. Scope Drift Detection

**Problem**: No way to verify that agents actually delivered what was asked.

**Solution**: After a build/crew run, compare the original task description against the actual outputs.

**Design**:
- Extract key deliverables from the original prompt/task description
- After run completion, use a lightweight LLM pass to classify each deliverable as: DONE, PARTIAL, NOT DONE, CHANGED
- Surface as a completion scorecard in the results view
- Flag runs where >30% of deliverables are NOT DONE or CHANGED

**Files to modify**:
- `backend/services/workspace/orchestrator.py` — add post-run scope check
- `backend/services/crew_orchestrator.py` — same for crews
- `frontend/src/components/workspace/project-results.tsx` — render scorecard

---

## P2 — New Capabilities (Do Later)

### 6. Browser Automation Tool

**Problem**: Agents can fetch web pages but can't interact with them (click, fill forms, navigate multi-page flows).

**Solution**: Add a Playwright-based browse tool to the agent tool registry.

**Capabilities** (v1 — keep it simple):
- `browse_goto(url)` — navigate to URL
- `browse_click(selector)` — click an element
- `browse_fill(selector, text)` — fill a form field
- `browse_extract(selector?)` — extract text content (full page or scoped)
- `browse_screenshot()` — capture current page as image
- `browse_links()` — list all links on page

**Architecture**:
- Single headless Chromium instance managed by the backend
- Launched on first use, auto-shutdown after 5 min idle
- Trust boundary: wrap all extracted content with markers to prevent prompt injection
- Tool registered in `ToolRegistry` under a new `BrowserTools` class

**Files to create/modify**:
- `backend/services/tools/browser_tools.py` — new tool class
- `backend/services/browser_service.py` — Playwright lifecycle management
- `backend/services/tools/tool_registry.py` — register BrowserTools
- `requirements.txt` — add playwright dependency

---

### 7. Design-to-Code Pipeline

**Problem**: Solo has design agents but no structured way to go from a visual mockup to implementation-ready specs.

**Solution**: Add a design extraction tool that uses vision models to convert screenshots/mockups into structured design specs.

**Flow**:
1. User uploads a mockup/screenshot
2. Vision model extracts: color palette, typography, spacing, layout structure, component hierarchy
3. Output: structured JSON spec
4. Spec injected as context for frontend/design agents in a workspace project

**Files to create/modify**:
- `backend/services/design_extraction_service.py` — vision-based extraction
- `backend/routers/design.py` — API endpoint for extraction
- `frontend/src/components/workspace/` — design spec viewer/editor

---

## Not Adopting

| gstack Feature | Reason |
|---|---|
| Git worktree manager | Solo agents don't do heavy git workflows |
| Multi-session awareness | Solo is single-user, single-window |
| Chrome extension | Different UX paradigm (desktop app) |
| Supabase telemetry | Solo is local-first |
| Pair-agent cross-sharing | Too niche for current users |
| Skill template generation pipeline | Solo uses markdown agent library, not skill templates |
