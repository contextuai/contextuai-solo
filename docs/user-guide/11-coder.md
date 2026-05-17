# 11. Solo Coder — Multi-Agent Mode

Solo Coder turns your project folder into a live coding environment. PR 16 adds **multi-agent support**: instead of a single assistant handling everything, your project gets a **Team** of specialised roles that collaborate on each request.

---

## What multi-agent Coder is

When you send a message in the Chat panel, the request flows through a configurable **workflow** of AI roles:

- **Coder** — writes the implementation
- **Reviewer** — checks code quality and suggests improvements
- **Security** — flags vulnerabilities and bad practices
- **UI/UX** — evaluates interface decisions
- **Docs** — writes or refines documentation
- **Tester** — generates test cases
- **Planner** — decomposes complex tasks before any code is written
- **Custom** — any specialist you define

Each role runs with its own model, system prompt, temperature, and token budget. Outputs from one role are passed to the next, so the Reviewer sees exactly what the Coder produced.

**When to use it**:
- You want an automatic second opinion on generated code (Coder → Reviewer)
- You need security review built into every change (add Security role)
- You're building UI and want design feedback alongside the code (add UI/UX role)
- You're starting a complex feature and want a plan before any code is written (add Planner role)

For simple one-off questions the Solo (single-role) preset is fastest.

---

## Workflow modes

Open a project and click the **Team** tab (right pane, next to Terminal).

| Mode | Behaviour |
|------|-----------|
| **Solo** | One role (typically Coder) handles the full request. Fastest. |
| **Sequential** | Roles run in order. Each role's output is passed to the next as context. |
| **Parallel** | All enabled roles run simultaneously. Outputs are collected side by side. |
| **Custom** | Advanced: roles are ordered by their `order` field; you control the pipeline. |

Change the mode by clicking the segmented control at the top of the Workflow section. The change saves immediately.

---

## The 4 presets

Click **Apply preset** to replace your current team with a curated configuration.

### Local Solo
- **Roles**: Coder (1 role)
- **Mode**: Solo
- **Best for**: Fast iteration on personal projects. Fully offline; no cloud API keys needed.

### Cloud Premium
- **Roles**: Planner → Coder → Reviewer → Security (4 roles)
- **Mode**: Sequential
- **Best for**: Production-grade work where quality matters more than speed. Requires cloud provider keys (Anthropic, OpenAI, or Google).

### Hybrid
- **Roles**: Coder (local) → Reviewer (cloud)
- **Mode**: Sequential
- **Best for**: Balancing cost and quality. The fast local model writes the code; a cloud model reviews it. Requires at least one cloud key.

### Custom
- **Roles**: Starts empty
- **Mode**: Custom
- **Best for**: Advanced users who want full control. Add roles manually and configure each one.

Applying a preset replaces all existing roles and sets the workflow mode. You can further customise after applying.

---

## Per-role model selection

Each role has its own **Model** dropdown. The picker groups models into:

- **Local — Downloaded**: GGUF models you've installed via the Model Hub. Free to use, runs on your CPU.
- **Local — Ollama**: Models served by a local Ollama instance. Shows a reachability indicator.
- **Cloud — Anthropic / OpenAI / Google / Bedrock**: Each provider group shows whether you have a saved API key. If no key is saved, a "Set up" link opens Settings → AI Providers.

Choosing a local model for the Coder role and a cloud model for the Reviewer role is a common hybrid setup.

---

## Cost and latency notes

The Team panel shows a rough estimate under the Workflow section:

- **All local roles**: "free (local)" — no API costs; latency depends on model size and your hardware.
- **All cloud roles**: "varies (~$0.001–0.05/turn)" — depends on the provider, model, and token count per role.
- **Mixed**: Shows a blended estimate (e.g. "~$0.010/turn · 2 local + 1 cloud").

These are heuristic estimates, not exact billing amounts. Check your cloud provider's dashboard for actual usage.

**Latency**: Sequential mode adds latency proportional to the number of roles (each waits for the previous). Parallel mode runs faster but uses more concurrent API calls.

---

## Preview card

While you're typing a message, a **preview card** appears above the input showing the planned workflow:

```
Coder → Reviewer → Security · sequential
```

This is computed by calling `/run/preview` with your draft text (debounced 500 ms). It reflects the current enabled roles and workflow mode. The card disappears when you send.

---

## Role card controls

Each role card in the Team tab offers:

| Control | Description |
|---------|-------------|
| **Drag handle** (left) | Drag cards up/down to reorder. Order is persisted immediately. |
| **Name** (inline edit) | Click the name to edit. Saves on blur. |
| **Enabled toggle** (right) | Disable a role without deleting it. Disabled roles are skipped during runs. |
| **Kebab menu** | Delete or Duplicate the role. |
| **Model** | Provider-aware dropdown (see above). |
| **System prompt** | Click "System prompt" to expand a textarea. Monospace, 10 rows. |
| **Temperature** | Slider 0–1, step 0.05. Lower = more deterministic. |
| **Max tokens** | Slider 256–8192, step 256. Sets the output length cap for this role. |

Changes debounce 400 ms then sync to the backend. A "Saving…" / "Saved" indicator appears in the card header.

---

## Chat with the team

The Chat panel (left side of the project detail view) sends messages through your team rather than a single model. Each role's response appears as a **separate bubble** with a coloured badge:

| Role | Badge colour |
|------|-------------|
| Coder | Orange (primary) |
| Reviewer | Sky blue |
| Security | Rose |
| UI/UX | Violet |
| Docs | Emerald |
| Tester | Amber |
| Planner | Indigo |
| Custom | Neutral |

Each bubble shows the role name, model, and token count. The conversation history is passed to each subsequent role so context is preserved across turns.

If you haven't configured any roles, the backend falls back to a single Coder role automatically.
