# Crews

Crews are multi-agent teams that work together to accomplish complex tasks. You define the agents, choose how they collaborate, and optionally connect them to social platforms for automated posting.

![Crews](../screenshots/008-CrewHome.png)

---

## Getting Started

1. Navigate to **Crews** from the sidebar.
2. Click **Create Crew** to open the 5-step wizard.
3. Configure your crew's details, execution mode, agents, and connections.
4. Run the crew and monitor its progress in real-time.

## Crew List

The main page shows:

- **Stats cards** — Total Crews, Running, Completed, Failed
- **Crews tab** — all your crews with search and filters
- **Runs tab** — execution history across all crews

### Searching and Filtering

- **Search** — filter crews by name or description
- **Status filter** — All, Active, Paused, Archived
- **Execution mode filter** — All, Sequential, Parallel, Pipeline, Autonomous

## Creating a Crew

The crew builder is a 5-step wizard:

### Step 1: Crew Details

- **Crew name** (required) — give your crew a descriptive name
- **Description** — what this crew does (you can also click **"Use Blueprint"** to populate from a template)
- **AI Model** — select a specific model or leave on "Auto" for the default

### Step 2: Execution Mode

Choose how your agents collaborate:

| Mode | How it works | Best for |
|------|-------------|----------|
| **Sequential** | Agents run one after another. Each agent's output becomes the next agent's input. | Step-by-step workflows (research → write → review) |
| **Parallel** | All agents run at the same time, independently. | Independent tasks that don't depend on each other |
| **Pipeline** | Agents run in dependency-ordered stages. | Complex workflows with branching dependencies |
| **Autonomous** | A coordinator agent dynamically discovers and invokes specialist agents. | Open-ended tasks where you don't know the exact steps upfront |

**Autonomous mode** has extra safety settings:
- **Max Agent Invocations** (1–50, default 10) — limits how many agents the coordinator can call
- **Budget Limit** ($0.01–$100.00, default $1.00) — spending cap for the run

### Step 3: Agent Team

> Skipped in Autonomous mode — the coordinator discovers agents automatically.

Build your agent team:

- Click **Add Agent** to add a blank agent with name, role, and instructions.
- Click **Browse Library** to pick from the 81 pre-built agents.
- Reorder agents to control the execution sequence (for Sequential mode).
- Each agent needs a **name** and **instructions** at minimum.

#### Browsing the Agent Library

The library browser opens as a panel within the wizard:

- Search agents by name or description
- Filter by category
- Click an agent to add it to your crew
- The agent's name, role, and instructions are pre-filled from the library

### Step 4: Connections

![Crew Approvals](../screenshots/013-CrewApprovals.png)

Optionally bind your crew to social channels:

- **Telegram** — send/receive via bot
- **Discord** — send/receive via bot
- **LinkedIn** — post updates
- **Twitter/X** — post tweets
- **Instagram** — post content
- **Facebook** — post updates

For each channel you can enable **"Require approval before sending"** — the crew will pause and wait for your approval before posting to that platform.

This step is optional — skip it if your crew doesn't need social integration.

### Step 5: Review

Review your full configuration:

- Crew name, description, execution mode, AI model
- Agent team list (for non-autonomous crews)
- Connected channels with approval settings
- Click **Create Crew** to finalize

## Running a Crew

1. Click the **Run** button on a crew card, or open the crew detail page and click **Run Crew**.
2. A progress modal appears showing real-time status.

### Run Progress

The progress modal displays:

- **Status** — Pending, Running, Completed, Failed, Cancelled
- **Progress bar** — completed steps vs. total steps
- **Duration** — how long the run has been active
- **Tokens used** — total token consumption
- **Cost** — estimated cost in USD
- **Step timeline** — each agent's step with status, duration, and expandable output
- **Cancel button** — stop a running execution

### Viewing Results

After a run completes:

- The final output is displayed in the progress modal
- Switch to the **Runs tab** on the crew list to see all past runs
- Each run shows status, duration, cost, and date

## Crew Cards

Each crew card shows:

- Crew name and description
- **Execution mode badge** (Sequential, Parallel, Pipeline, Autonomous)
- **Agent count** — how many agents are in the team
- **Status badge** — Active, Paused, Archived
- **Run button** — quick-start an execution

## Tips

- **Start with Sequential mode** — it's the easiest to understand and debug. Agent A's output feeds into Agent B.
- **Use Blueprints** in Step 1 to pre-fill your crew description with a proven workflow template.
- **Browse the library** instead of writing agent instructions from scratch — the pre-built agents have detailed, production-ready prompts.
- **Enable approval for social channels** until you trust the output quality — you don't want to auto-post something embarrassing.
- **Keep autonomous crews small** — set a low invocation limit (5–10) and budget ($1–$5) while you're learning how they behave.
- **Check the Runs tab** regularly to monitor costs and catch failures early.
