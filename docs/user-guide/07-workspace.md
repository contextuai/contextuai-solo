# Workspace

The Workspace is where you run multi-agent projects. Create a project, assign agents, execute it, and review the results — all in one place.

![Workspace](../screenshots/011-Workspace.png)

---

## Getting Started

1. Navigate to **Workspace** from the sidebar.
2. Click **New Project** to open the 3-step wizard.
3. Choose your agents, run the project, and review the compiled output.

## Project List

The main page shows all your projects as cards:

- **Project name** and description
- **Status badge** — Draft, Running, Completed, Failed
- **Status filters** — click a pill to show only projects with a specific status (All, Draft, Running, Completed, Failed)

Click any project card to view its results.

## Creating a Project

### Step 1: Project Details

- **Project name** (required) — describe what you want to accomplish
- **Description** — provide context and goals
- **AI Model** — choose a specific model or leave on "Auto"
- **Use Blueprint** — click to start from a pre-built workflow template

### Step 2: Agent Selection

- Browse the list of available agents from the 81-agent library
- **Search** to filter agents by name
- **Check** agents to add them to your project
- A **count badge** shows how many agents you've selected
- At least one agent is required to proceed

### Step 3: Review & Create

- Review your project name, description, selected agents, and AI model
- Click **Create** to finalize the project
- Use **Back** to return and make changes (your selections are preserved)

## Running a Project

After creating a project:

1. Open the project by clicking its card.
2. Click the **Execute** button.
3. The project status changes to **Running** — the assigned agents work through the task.
4. When complete, the status updates to **Completed** (or **Failed** if something went wrong).

Execution times vary depending on the model and number of agents. Local models may take longer (up to a few minutes).

## Viewing Results

The project results page has two tabs:

### Discussion Tab

Shows the step-by-step agent contributions — each agent's input, reasoning, and output in a threaded view. This is useful for understanding how the agents collaborated.

### Compiled Output Tab

Shows the final, consolidated result. This is the deliverable — the combined output of all agents' work. Use the **copy button** to grab the full text.

## Project Status

| Status | Meaning |
|--------|---------|
| **Draft** | Created but not yet executed |
| **Running** | Agents are currently working |
| **Completed** | All agents finished successfully |
| **Failed** | Execution encountered an error |

## Tips

- **Be specific in your project description** — the more context you provide, the better the agents perform.
- **Choose complementary agents** — pair a researcher with an analyst and a writer for comprehensive output.
- **Use blueprints** for common workflows instead of starting from scratch.
- **Check the Discussion tab** if the compiled output isn't what you expected — it helps you understand where things went off track.
- **Start with 2–3 agents** to keep things simple. Add more as you learn how they interact.
- **Local models work** for workspace projects, but expect longer execution times compared to cloud models.
