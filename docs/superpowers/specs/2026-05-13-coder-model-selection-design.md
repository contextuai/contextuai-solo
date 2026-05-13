# Coder mode — model selection & onboarding fixes

**Status**: spec, ready for implementation
**Date**: 2026-05-13
**Branch base**: `feat/phase-5-coder-multi-agent` (or current Coder rollout branch)

## Problem statement

Three issues block daily use of the new Coder multi-agent mode (Phase 5, PR 12–16):

1. **Coder toggle lands on Solo chat.** Clicking *Coder* in the top-bar leaves the user on `/` (the chat page). They never see Projects unless they click the sidebar manually.

2. **Chat fails with "Model not found in local catalog".** Two root causes:
   - **Dispatcher bug** (a real defect, fixed in PR 17): `services/model_dispatcher.py::_parse_provider()` doesn't strip the `local:` / `local-` prefix that `services/local_model_seeder.py` writes onto the `models._id` field. When `resolve_default_model()` returns `local:deepseek-r1-1.5b`, the dispatcher treats the entire string as a bare model name and the catalog lookup misses.
   - **Hardcoded preset model IDs that may not exist for the user** (real design issue): the four preset JSON files under `coder-role-presets/` ship model IDs like `qwen2.5-coder-7b`, `phi4-14b`, `gemma3-12b`, `deepseek-r1-7b`. If the user hasn't downloaded those specific models, every role fails. Even worse: the previous draft of the presets had typos that don't match the catalog at all (`phi-4-14b` vs real `phi4-14b`).

3. **No "how do I get an API key" guide.** Settings → AI Providers has a paste-key field per provider but no card-by-card onboarding. The Distributions page (`routes/connections.tsx`) has this pattern; AI Providers should mirror it.

## Design principles (non-negotiable)

These are corrections to assumptions from earlier PRs:

- **No silent model fallbacks.** If no model is picked for a role, that role cannot run. The UI must surface this clearly and disable the action — never substitute a "first installed model".
- **No hardcoded model IDs in presets.** Presets describe *roles* (kind, display name, system prompt, temperature, max tokens). Model assignment is the **user's choice**, made at project creation time from a dropdown of what they actually have installed (local) or have keys for (cloud).
- **Creating a project without picking a model is a user error and must be blocked at the dialog level.** No "create now, configure later" with broken defaults.

## Fix list

### 1. Default home for Coder mode → `/coder/projects`

`frontend/src/components/shell/mode-toggle.tsx` (and the keyboard shortcut in `App.tsx::ModeShortcutHandler`) currently only flips `mode` state via `useMode()`. They do not navigate.

**Implementation:** add a navigation effect in `App.tsx` (one effect, two entry points covered):

```tsx
function ModeRedirector() {
  const { mode } = useMode();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const onCoderRoute = location.pathname.startsWith("/coder/");
    if (mode === "coder" && !onCoderRoute) {
      navigate("/coder/projects", { replace: true });
    } else if (mode === "solo" && onCoderRoute) {
      navigate("/", { replace: true });
    }
  }, [mode]);  // intentionally not depending on location

  return null;
}
```

Mount inside `<BrowserRouter>` next to `ModeShortcutHandler`. Use `{ replace: true }` so the back-button history stays clean.

**Test (E2E):** click mode toggle → assert URL is `/coder/projects`. Toggle back → assert URL is `/`. Also press Cmd/Ctrl+Shift+M and verify the same.

### 2. Dispatcher: strip `local:` / `local-` prefix

**Already shipped in PR 17 branch** (`feat/coder-pr17-quickfixes`). One small change to `backend/services/model_dispatcher.py::_parse_provider()`:

```python
def _parse_provider(model_id: str) -> tuple[str, str]:
    for prefix in _KNOWN_PREFIXES:
        if model_id.startswith(f"{prefix}:"):
            return prefix, model_id[len(prefix) + 1:]
    if model_id.startswith("local:"):
        return "local", model_id[len("local:"):]
    if model_id.startswith("local-"):
        return "local", model_id[len("local-"):]
    return "local", model_id
```

Add a unit test in `backend/tests/test_model_dispatcher.py`:
- `_parse_provider("local:qwen2.5-7b") == ("local", "qwen2.5-7b")`
- `_parse_provider("local-qwen2.5-7b") == ("local", "qwen2.5-7b")`
- Stream-chat round-trip with `model_id="local:qwen2.5-1.5b"` returns events (mock the llama call).

### 3. Presets: drop hardcoded model IDs

Edit all four files under `coder-role-presets/` so each role's `model_id` becomes either:

- **empty string `""`** (preferred — simplest sentinel), or
- **null**, or
- **omitted entirely** from the JSON

Pick one form and use it consistently. The preset becomes a *role template*, not a *model configuration*. Example after the change:

```json
{
  "role_kind": "reviewer",
  "display_name": "Code Reviewer",
  "system_prompt": "You are a senior engineer conducting a thorough code review...",
  "model_id": "",
  "temperature": 0.3,
  "max_tokens": 2048,
  "enabled": true,
  "order": 2
}
```

Update `backend/services/coder_role_preset_service.py::apply_preset()`:
- When applying a preset, write the role rows with `model_id = ""`.
- The Pydantic validator on `CoderAgentRoleCreate.model_id` must allow empty strings as a sentinel (currently it likely doesn't — adjust).
- Persist the unconfigured state truthfully.

Update `backend/services/coder_workflow_service.py`:
- Before running any role, validate that every enabled role has a non-empty `model_id`.
- If any enabled role has `model_id == ""`, **fail fast** with an SSE `error` event:
  - `{"type": "error", "error": "Role 'Code Reviewer' has no model selected. Open the Team panel and pick one."}`
- Do NOT fall back to `__DEFAULT__` for unconfigured roles. (The `__DEFAULT__` sentinel can stay for the explicit "Custom (blank)" preset, where the *user* puts it there knowingly.)

**Test:**
- `test_coder_role_presets.py`: after `apply_preset`, every role's `model_id` is `""`.
- `test_coder_workflow_*.py`: running a workflow with an unconfigured role emits the error event and stops; no model call is made.

### 4. NewProjectDialog: pick models at create time

Currently `frontend/src/components/coder/new-project-dialog.tsx` has 2 steps (template, name+folder). Add a **Step 3 — "Team & models"**.

**Layout:**

```
Step 3 — Team & models

Workflow:  ( Solo )( Sequential )( Parallel )( Custom )    ← segmented control

Apply preset:  [ Pick one ▾ ]    ← optional. Picking one fills the role list.

Roles (each must have a model selected before you can create):

  1. Coder
     Model: [ Pick a model ▾ ]                  ← grouped picker (Local installed / Cloud configured)
     Enabled: [ ON ]
     ↳ Show system prompt (collapsible, editable)

  2. Reviewer
     Model: [ Pick a model ▾ ]
     ...

  [ + Add role ]

  ☐ Use the same model for all roles  ← shortcut: once checked, picking a model in any row applies to all
```

**Hard rules:**
- The **Create Project** button is disabled until every *enabled* role has a non-empty `model_id`.
- The model picker (`components/coder/model-picker.tsx`, already exists from PR 16) only shows:
  - Local models the user has actually downloaded (queried from `GET /v1/models`).
  - Cloud models for providers the user has saved keys for (queried from `GET /api/v1/cloud-providers`).
  - Ollama models if Ollama is reachable.
  - Providers with no key show a disabled group with a "Set up →" link to `/settings?tab=ai-providers`.
- If the user has **zero usable models** (no local installed, no cloud keys), the dialog shows a blocking banner: "Download a local model or save a cloud API key before creating a project," with two buttons: *Go to Model Hub* and *Go to AI Providers*.

**Create flow:**
1. Submit the project (POST `/api/v1/coder/projects` as today).
2. If the user picked a preset, call `POST /api/v1/coder/projects/{id}/roles/apply-preset` with that preset_id.
3. For each role, send the user-picked `model_id` via `PUT /api/v1/coder/projects/{id}/roles/{role_id}` so the empty sentinel gets replaced.
4. Set `workflow_mode` via `PUT /api/v1/coder/projects/{id}/workflow`.
5. Navigate to `/coder/projects/{id}`.

**Test (E2E):**
- `team-panel.spec.ts` already covers post-creation editing. Add `new-project-dialog.spec.ts`:
  - Open New Project dialog, step through, verify Create is disabled until every role has a model.
  - Apply "Local Solo" preset, see 6 role cards, pick a model on each → Create unlocks.
  - "Use same model for all" toggles → picking a model on one row populates all.

### 5. AI Providers onboarding — Distributions-style cards

Update `frontend/src/routes/settings.tsx` (the AI Providers tab) to mirror the card pattern in `frontend/src/routes/connections.tsx`.

**For each provider** (Anthropic, OpenAI, Google Gemini, AWS Bedrock, Ollama), render a card with:

1. **Header**: provider logo + name + status badge (✓ key saved / ⚠ not configured).
2. **"Get your API key"** — collapsible step list. Numbered, copy-pasteable:
   - **Anthropic**: (1) Sign up at console.anthropic.com (2) Top up credits ($5 minimum) (3) Settings → API Keys → Create Key (4) Copy the key starting with `sk-ant-…` and paste below.
   - **OpenAI**: (1) Sign up at platform.openai.com (2) Add a payment method (3) Dashboard → API keys → Create new secret key (4) Copy the key starting with `sk-…`.
   - **Google Gemini**: (1) Visit aistudio.google.com/apikey (2) Click "Create API key" (3) Pick a Google Cloud project (or create one) (4) Copy the key. Free tier available.
   - **AWS Bedrock**: (1) Sign in to AWS Console (2) Bedrock → Model access → request access to Claude / Llama (3) IAM → Create user with `AmazonBedrockFullAccess` (4) Generate access key + secret (5) Note the region (e.g. `us-east-1`).
   - **Ollama**: (1) Install Ollama from ollama.com (2) Run `ollama pull qwen2.5-coder:7b` (3) Confirm `ollama serve` is reachable at `http://localhost:11434`. No API key.
3. **Cost estimate copy**: one line, e.g. "Claude Sonnet ~$3 per million input tokens, $15 per million output." (Pull current rates manually; update copy when prices change.)
4. **Key paste field** (masked input) + **Save** + **Test connection** buttons. These already exist in some form — reuse the existing settings logic, just restyled into a card.
5. **External link button**: opens the provider's dashboard in a new tab.

**Implementation notes:**
- Define a `PROVIDER_GUIDES` constant array of `{id, name, logo, steps[], cost_copy, dashboard_url}` in `frontend/src/data/provider-guides.ts`.
- Reuse the existing `<Card>`, `<Button>`, `<Input>` primitives. Don't introduce a new design system.
- The "Test connection" button already calls `POST /api/v1/cloud-providers/{provider_id}/test` — keep that wiring.

**Test (E2E):** add `settings-ai-providers.spec.ts`:
- Open Settings → AI Providers, assert one card per provider with a setup-steps section.
- Click "Get your API key" on Anthropic, assert at least 3 numbered steps appear.
- Paste a dummy key, click Save, assert the status badge flips to "key saved".

## Implementation order (recommended PRs)

| PR | Scope | Branch | Est. LOC | Risk |
|---|---|---|---|---|
| 17 | Quick fixes: dispatcher `local:` prefix + mode-toggle navigation + preset cleanup (strip hardcoded model_ids) + tests | `feat/coder-pr17-quickfixes` | ~120 | low |
| 18 | NewProjectDialog Step 3: workflow + preset + per-role model picker + create-flow PUTs | `feat/coder-pr18-project-models` | ~450 | medium |
| 19 | Settings AI Providers cards: per-provider onboarding steps + restyle | `feat/coder-pr19-provider-onboarding` | ~350 | low |

PR 17 unblocks chat today. PR 18 + PR 19 are independent of each other and can be cut in parallel.

## Acceptance criteria

A reviewer should be able to:

1. Click the **Coder** toggle → land directly on Projects, not Chat.
2. Click **New Project** → step through dialog → be **blocked from clicking Create** until every enabled role has a model selected from a real dropdown of what's available.
3. Open Settings → AI Providers → see step-by-step onboarding for Anthropic / OpenAI / Google / Bedrock / Ollama with paste-key + Test buttons inline.
4. Send a chat in a fresh project → roles stream in order using the picked models → **no `Model not found` errors**.
5. If a role has no model picked (data hand-edit, migration edge case), the chat fails fast with a clear "Open the Team panel and pick a model" error — never silently substitutes a fallback.

## Non-goals for this batch

- Cost meter live calculation (out of scope; PR 17 keeps the placeholder hint).
- Model recommendations engine ("we suggest Qwen-Coder for this role"). Future PR.
- Custom role creation in the new project dialog (PR 16's Team panel already covers post-create role tweaking).
- Migrating existing projects with hardcoded model_ids — the dispatcher fix means their chats start working again as soon as a real model is picked in the Team panel.

## Open questions

- **Empty `model_id` sentinel: empty string vs null vs omitted field?** Recommendation: empty string. Easiest Pydantic validation (`min_length=0` allowed, `min_length=1` blocks at run-time). Document it in `models/coder_models.py`.
- **Should the "Custom" preset still ship the `__DEFAULT__` sentinel for its single role?** Recommendation: keep `__DEFAULT__` only in the custom preset — that's the one place where it's the *user's intent* to use whatever default is configured. Everywhere else, no default.
- **Where does the "default model preference" UI live?** Currently `default_model_service.py` reads from a `settings._id == "default_model_id"` row, but there's no UI to set it. Out of scope for this batch; surface it later as a Settings field.

## File touch list (rough)

```
backend/
  services/model_dispatcher.py            # PR 17: _parse_provider prefix handling
  services/coder_role_preset_service.py   # PR 17: apply_preset writes empty model_id
  services/coder_workflow_service.py      # PR 17: fail-fast on empty model_id
  models/coder_models.py                  # PR 17: allow empty model_id in CoderAgentRole*
  tests/test_model_dispatcher.py          # PR 17: local: prefix coverage
  tests/test_coder_role_presets.py        # PR 17: assert empty model_id post-apply
  tests/test_coder_workflow_*.py          # PR 17: assert error on empty model_id

coder-role-presets/
  local-solo.json                         # PR 17: model_id="" on every role
  cloud-premium.json                      # PR 17: same
  hybrid.json                             # PR 17: same
  custom.json                             # PR 17: keep __DEFAULT__ (single role, user intent)

frontend/
  src/App.tsx                             # PR 17: ModeRedirector
  src/components/coder/new-project-dialog.tsx  # PR 18: Step 3, model pickers, gating
  src/components/coder/model-picker.tsx   # PR 18: reuse from PR 16
  src/lib/api/coder-workflow-client.ts    # PR 18: any new fields for create-with-models
  src/routes/settings.tsx                 # PR 19: AI Providers tab restyle
  src/data/provider-guides.ts             # PR 19: new file with PROVIDER_GUIDES
  tests/e2e/coder/new-project-dialog.spec.ts  # PR 18
  tests/e2e/settings-ai-providers.spec.ts     # PR 19
```

## How a fresh chat / agent should pick this up

If a new session lands cold:

1. Read this spec end to end before touching code.
2. Confirm the current branch state with `git log --oneline main..HEAD` — PR 12–16 must already be merged into `feat/phase-5-coder-multi-agent` (commit `525049a` is the tip).
3. Start with PR 17 (small, no UX surprises). Verify backend tests still pass.
4. PR 18 + PR 19 can be cut by the `frontend-engineer` subagent in parallel — they touch disjoint files.
5. Do not push to GitHub. The user runs all releases via the `/prod-release` skill.

## What we are explicitly NOT doing

- Adding any "best model for this role" recommendation engine.
- Auto-downloading a default model on first launch.
- Inferring a model from the project's runtime (e.g. "this is a Python project, pick Qwen-Coder"). Future work.
- Silently mapping an unavailable preset model to "the closest one we have." Every role's model is the user's deliberate choice.
