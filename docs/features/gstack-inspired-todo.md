# gstack-Inspired Features — TODO Tracker

Reference: [gstack-inspired-features.md](./gstack-inspired-features.md)

---

## P0 — Foundational

### 1. Structured Completion Statuses & Escalation
- [ ] Define `CompletionStatus` enum (DONE, DONE_WITH_CONCERNS, BLOCKED, NEEDS_INPUT)
- [ ] Add status field to agent run and crew run models
- [ ] Update `AgentRunner` to report structured status on completion
- [ ] Add 3-strike escalation logic (3 failures on same subtask → stop)
- [ ] Update `WorkspaceOrchestrator` to handle new statuses (pause on BLOCKED, surface NEEDS_INPUT)
- [ ] Update `CrewOrchestrator` to handle new statuses
- [ ] Add empty-output detection → auto-mark DONE_WITH_CONCERNS
- [ ] Add status badges to project results UI
- [ ] Add status badges to crew run progress UI
- [ ] Write backend tests for escalation logic

### 2. Workspace Learnings System
- [ ] Create `workspace_learnings` SQLite collection schema
- [ ] Create `LearningRepository` with CRUD + query by workspace/agent/type
- [ ] Create `LearningService` with dedup (key+type), confidence decay, max cap (200)
- [ ] Add post-run reflection to `AgentRunner` (extract successes, failures, surprises)
- [ ] Add post-run reflection to `CrewOrchestrator`
- [ ] Inject relevant learnings into agent context before execution
- [ ] Add API endpoints: GET/POST/DELETE learnings per workspace
- [ ] Build learnings viewer component in workspace UI
- [ ] Add confidence decay job (run on app startup, prune decayed learnings)
- [ ] Write backend tests for learning service

---

## P1 — Quality Improvements

### 3. Adaptive Agent Dispatch
- [ ] Define output scoring criteria (empty=0, generic=1-3, substantive=4-7, critical=8-10)
- [ ] Add scoring step after each agent run in `CrewOrchestrator`
- [ ] Store per-agent effectiveness in crew memory
- [ ] Add skip logic: flag agents with 0 score in 5+ consecutive runs
- [ ] Surface skip suggestions in crew detail UI
- [ ] In autonomous mode, pass effectiveness history to coordinator prompt
- [ ] Write tests for scoring and skip logic

### 4. Structured Question UX for Checkpoints
- [ ] Define `StructuredQuestion` model (context, summary, recommendation, options[])
- [ ] Add `structured_question` field to checkpoint model
- [ ] Create `format_checkpoint_question()` utility
- [ ] Update checkpoint creation in agent runner to use structured format
- [ ] Build structured question renderer in frontend (option buttons, context card)
- [ ] Write tests for question formatting

### 5. Scope Drift Detection
- [ ] Create `ScopeDriftService` that extracts deliverables from task description
- [ ] Add post-run scope check using lightweight LLM pass
- [ ] Define deliverable statuses: DONE, PARTIAL, NOT_DONE, CHANGED
- [ ] Add scope scorecard to project run results
- [ ] Add scope scorecard to crew run results
- [ ] Flag runs where >30% deliverables are NOT_DONE or CHANGED
- [ ] Write tests for deliverable extraction and classification

---

## P2 — New Capabilities

### 6. Browser Automation Tool
- [ ] Add `playwright` to backend requirements
- [ ] Create `BrowserService` (Chromium lifecycle: launch on first use, 5-min idle shutdown)
- [ ] Create `BrowserTools` class with v1 commands (goto, click, fill, extract, screenshot, links)
- [ ] Add content trust boundary wrapper for extracted page content
- [ ] Register `BrowserTools` in `ToolRegistry`
- [ ] Add browser persona type to seed data
- [ ] Write integration tests with test pages
- [ ] Document browser tool capabilities in agent library

### 7. Design-to-Code Pipeline
- [ ] Create `DesignExtractionService` using vision model API
- [ ] Define extraction output schema (colors, typography, spacing, layout, components)
- [ ] Add API endpoint: POST /api/v1/design/extract (accepts image upload)
- [ ] Build design spec viewer/editor component
- [ ] Integrate spec injection into workspace agent context
- [ ] Write tests for extraction service

---

## Progress Summary

| Feature | Status | Priority |
|---|---|---|
| Structured Completion Statuses | Not Started | P0 |
| Workspace Learnings System | Not Started | P0 |
| Adaptive Agent Dispatch | Not Started | P1 |
| Structured Question UX | Not Started | P1 |
| Scope Drift Detection | Not Started | P1 |
| Browser Automation Tool | Not Started | P2 |
| Design-to-Code Pipeline | Not Started | P2 |
