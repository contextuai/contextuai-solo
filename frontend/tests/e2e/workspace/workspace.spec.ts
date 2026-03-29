/**
 * ContextuAI Solo Desktop — Workspace E2E Tests
 *
 * Route: "/workspace" (Workspace page)
 * Backend: http://127.0.0.1:18741 (no auth)
 * Frontend: http://localhost:1420 (Vite SPA)
 *
 * Tests cover full CRUD: create, read, execute, delete.
 */
import { test, expect } from "@playwright/test";
import { WorkspacePage } from "../fixtures/page-objects";

let workspace: WorkspacePage;

test.beforeEach(async ({ page }) => {
  workspace = new WorkspacePage(page);
  await workspace.goto();
  await page.waitForTimeout(1500);
});

// ==========================================================================
// Page Load & Layout
// ==========================================================================

test.describe("Page Load & Layout", () => {
  test("DC-WORKSPACE-01: view workspace page with correct heading", async ({ page }) => {
    await expect(page.locator("h1", { hasText: "Workspace" })).toBeVisible();

    const projectCount = await workspace.getProjectCount();
    const emptyVisible = await workspace.emptyState.isVisible().catch(() => false);

    expect(projectCount > 0 || emptyVisible).toBeTruthy();
  });

  test("DC-WORKSPACE-02: status filter pills are visible and interactive", async ({ page }) => {
    const filters = await workspace.statusFilters.all();
    expect(filters.length).toBeGreaterThanOrEqual(2);

    for (const filter of filters) {
      await filter.click();
      await page.waitForTimeout(300);
      await expect(page.locator("h1", { hasText: "Workspace" })).toBeVisible();
    }
  });

  test("DC-WORKSPACE-03: refresh button reloads projects", async ({ page }) => {
    await expect(workspace.refreshButton).toBeVisible();
    await workspace.refreshButton.click();
    await page.waitForTimeout(1000);
    await expect(page.locator("h1", { hasText: "Workspace" })).toBeVisible();
  });

  test("DC-WORKSPACE-04: empty state shows start your first project", async ({ page }) => {
    const projectCount = await workspace.getProjectCount();

    if (projectCount === 0) {
      await expect(workspace.emptyState).toBeVisible();

      const emptyStateBtn = page.locator("button").filter({ hasText: "New Project" }).first();
      await expect(emptyStateBtn).toBeVisible();
    } else {
      expect(projectCount).toBeGreaterThan(0);
    }
  });

  test("DC-WORKSPACE-05: new project button opens wizard", async ({ page }) => {
    const btn = page.locator("button", { hasText: "New Project" }).first();
    await expect(btn).toBeVisible();

    await btn.click();
    await page.waitForTimeout(500);

    await expect(workspace.projectNameInput).toBeVisible();
    await expect(workspace.stepIndicators.first()).toBeVisible();
  });
});

// ==========================================================================
// Wizard Flow
// ==========================================================================

test.describe("Wizard Flow", () => {
  test("DC-WORKSPACE-WIZ-01: wizard shows 3-step indicator", async () => {
    await workspace.openWizard();

    const count = await workspace.stepIndicators.count();
    expect(count).toBe(3);
  });

  test("DC-WORKSPACE-WIZ-02: step 1 shows project details with model selector", async ({ page }) => {
    await workspace.openWizard();

    await expect(workspace.projectNameInput).toBeVisible();
    await expect(workspace.descriptionInput).toBeVisible();
    await expect(workspace.useBlueprintButton).toBeVisible();

    // AI Model selector should be visible
    await expect(page.getByText("AI Model")).toBeVisible();
    await expect(workspace.modelSelect).toBeVisible();

    // Should have "Auto" default option
    const selectedValue = await workspace.modelSelect.inputValue();
    expect(selectedValue).toBe("");
  });

  test("DC-WORKSPACE-WIZ-03: next button requires name on step 1", async () => {
    await workspace.openWizard();

    await expect(workspace.nextButton).toBeDisabled();

    await workspace.projectNameInput.fill("Test Project");
    await expect(workspace.nextButton).toBeEnabled();
  });

  test("DC-WORKSPACE-WIZ-04: step 2 shows agent selection with search", async ({ page }) => {
    await workspace.openWizard();

    await workspace.projectNameInput.fill("Agent Test");
    await workspace.nextButton.click();
    await page.waitForTimeout(500);

    await expect(workspace.agentSearchInput).toBeVisible();
    await expect(page.locator("text=Select Agents").first()).toBeVisible();

    const agentCount = await workspace.agentItems.count();
    expect(agentCount).toBeGreaterThanOrEqual(1);
  });

  test("DC-WORKSPACE-WIZ-05: agent search filters the list", async ({ page }) => {
    await workspace.openWizard();
    await workspace.goToStep(2);
    await page.waitForTimeout(500);

    const initialCount = await workspace.agentItems.count();

    await workspace.searchAgents("zzz_no_agent_matches_this_zzz");
    await page.waitForTimeout(300);

    const filteredCount = await workspace.agentItems.count();

    if (initialCount > 0) {
      expect(filteredCount).toBeLessThan(initialCount);
    }

    if (filteredCount === 0) {
      await expect(page.getByText(/no agents match/i)).toBeVisible();
    }
  });

  test("DC-WORKSPACE-WIZ-06: next button on step 2 requires agent selection", async ({ page }) => {
    await workspace.openWizard();

    await workspace.projectNameInput.fill("Validation Test");
    await workspace.nextButton.click();
    await page.waitForTimeout(300);

    await expect(workspace.nextButton).toBeDisabled();

    const agentCount = await workspace.agentItems.count();
    if (agentCount > 0) {
      await workspace.agentItems.first().click();
      await page.waitForTimeout(200);
      await expect(workspace.nextButton).toBeEnabled();
    }
  });

  test("DC-WORKSPACE-WIZ-07: navigate through all steps to review", async ({ page }) => {
    await workspace.openWizard();

    // Step 1
    await workspace.projectNameInput.fill("Full Flow Test");
    await workspace.descriptionInput.fill("Testing the full wizard flow");
    await workspace.nextButton.click();
    await page.waitForTimeout(300);

    // Step 2
    await expect(workspace.agentSearchInput).toBeVisible();
    const agentCount = await workspace.agentItems.count();
    if (agentCount > 0) {
      await workspace.agentItems.first().click();
      await page.waitForTimeout(200);
    }
    await workspace.nextButton.click();
    await page.waitForTimeout(300);

    // Step 3: Review
    await expect(page.getByText("Full Flow Test")).toBeVisible();
    await expect(page.getByText("Testing the full wizard flow")).toBeVisible();
    await expect(page.getByText("AI Model")).toBeVisible();
    await expect(page.getByText("Auto (default model)")).toBeVisible();
    await expect(workspace.submitButton).toBeVisible();
  });

  test("DC-WORKSPACE-WIZ-08: back button navigates backwards and preserves state", async ({ page }) => {
    await workspace.openWizard();

    await workspace.projectNameInput.fill("Back Test");
    await workspace.nextButton.click();
    await page.waitForTimeout(300);

    await expect(workspace.agentSearchInput).toBeVisible();

    await workspace.backButton.click();
    await page.waitForTimeout(300);

    await expect(workspace.projectNameInput).toBeVisible();
    const nameValue = await workspace.projectNameInput.inputValue();
    expect(nameValue).toBe("Back Test");
  });

  test("DC-WORKSPACE-WIZ-09: cancel button closes the wizard", async () => {
    await workspace.openWizard();
    await expect(workspace.wizardDialog).toBeVisible();

    await workspace.cancelButton.click();

    await expect(workspace.wizardDialog).not.toBeVisible({ timeout: 3000 });
  });

  test("DC-WORKSPACE-WIZ-10: selected agents count badge updates", async ({ page }) => {
    await workspace.openWizard();
    await workspace.goToStep(2);

    const agentCount = await workspace.agentItems.count();
    if (agentCount === 0) {
      test.skip();
      return;
    }

    await workspace.agentItems.first().click();
    await page.waitForTimeout(200);

    await expect(page.getByText("1 selected")).toBeVisible();

    if (agentCount >= 2) {
      await workspace.agentItems.nth(1).click();
      await page.waitForTimeout(200);
      await expect(page.getByText("2 selected")).toBeVisible();
    }
  });
});

// ==========================================================================
// CRUD Operations (end-to-end)
// ==========================================================================

test.describe("CRUD Operations", () => {
  test("DC-WORKSPACE-CRUD-01: create a project via wizard and verify it appears in list", async ({ page }) => {
    const projectName = await workspace.createProject({
      name: `CRUD Test ${Date.now()}`,
      description: "E2E test project for CRUD validation",
    });

    // Should navigate to results page or stay on list
    // Wait for navigation or dialog close
    await page.waitForTimeout(2000);

    // Go back to workspace list
    await page.goto("/workspace");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1500);

    // The project should appear in the list
    await expect(page.getByText(projectName)).toBeVisible({ timeout: 10000 });
  });

  test("DC-WORKSPACE-CRUD-02: create project and view its results page", async ({ page }) => {
    const projectName = await workspace.createProject({
      name: `Results Test ${Date.now()}`,
      description: "Testing results page navigation",
    });

    // After creation, should navigate to results view
    await page.waitForURL(/\/workspace\/.+/, { timeout: 15000 });

    // Results page should show project title
    await expect(page.getByText(projectName)).toBeVisible({ timeout: 10000 });

    // Should show status badge
    const statusBadge = page.locator("span.rounded-full").filter({
      hasText: /Draft|Running|Completed|Queued|Failed/i,
    });
    await expect(statusBadge.first()).toBeVisible({ timeout: 5000 });

    // Should have Discussion and Compiled Output tabs
    await expect(workspace.discussionTab).toBeVisible();
    await expect(workspace.compiledTab).toBeVisible();
  });

  test("DC-WORKSPACE-CRUD-03: view project details by clicking a card", async ({ page }) => {
    // First ensure there's at least one project
    const projectCount = await workspace.getProjectCount();
    if (projectCount === 0) {
      await workspace.createProject({
        name: `Detail View ${Date.now()}`,
      });
      await page.goto("/workspace");
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(1500);
    }

    // Click the first project card
    await workspace.openProject(0);

    // Should navigate to project detail
    await expect(page).toHaveURL(/\/workspace\/.+/);

    // Results page should show project info
    await expect(workspace.resultsTitle).toBeVisible();
    await expect(workspace.discussionTab).toBeVisible();
    await expect(workspace.compiledTab).toBeVisible();
  });

  test("DC-WORKSPACE-CRUD-04: switch between Discussion and Compiled Output tabs", async ({ page }) => {
    // Ensure a project exists
    const projectCount = await workspace.getProjectCount();
    if (projectCount === 0) {
      await workspace.createProject({ name: `Tab Test ${Date.now()}` });
      await page.goto("/workspace");
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(1500);
    }

    await workspace.openProject(0);

    // Click Compiled Output tab
    await workspace.compiledTab.click();
    await page.waitForTimeout(300);

    // Should show compiled output content area
    await expect(
      page.getByText(/compiled output|execute the project/i).first()
    ).toBeVisible();

    // Click Discussion tab
    await workspace.discussionTab.click();
    await page.waitForTimeout(300);

    // Should show discussion content area
    await expect(
      page.getByText(/contributions|agents are working|execute the project/i).first()
    ).toBeVisible();
  });

  test("DC-WORKSPACE-CRUD-05: delete a project via API and confirm removal from list", async ({ page }) => {
    // Create a project first
    const projectName = `Delete Test ${Date.now()}`;
    await workspace.createProject({
      name: projectName,
      description: "This project will be deleted",
    });

    // Go back to list
    await page.goto("/workspace");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1500);

    // Verify it exists
    await expect(page.getByText(projectName)).toBeVisible({ timeout: 10000 });

    // Get the project ID from the API
    const response = await page.request.get(
      "http://127.0.0.1:18741/api/v1/workspace/projects?limit=50"
    );
    const data = await response.json();
    const project = data.projects?.find(
      (p: { name?: string; title?: string }) =>
        p.name === projectName || p.title === projectName
    );
    expect(project).toBeTruthy();

    // Delete via API
    await workspace.deleteProjectViaApi(project.project_id);

    // Refresh the page
    await workspace.refreshButton.click();
    await page.waitForTimeout(2000);

    // Project should no longer be visible
    await expect(page.getByText(projectName)).not.toBeVisible({ timeout: 5000 });
  });

  test("DC-WORKSPACE-CRUD-06: create project with specific model selection shows in review", async ({ page }) => {
    await workspace.openWizard();

    // Step 1: Fill details
    await workspace.projectNameInput.fill("Model Selection Test");

    // Check if there are model options beyond "Auto"
    const modelOptions = await workspace.modelSelect.locator("option").all();
    if (modelOptions.length <= 1) {
      // Only "Auto" option available, skip model-specific test
      test.skip();
      return;
    }

    // Select the first non-auto model
    const secondOption = modelOptions[1];
    const modelValue = await secondOption.getAttribute("value");
    const modelText = await secondOption.textContent();
    await workspace.modelSelect.selectOption(modelValue!);

    // Go to step 2
    await workspace.nextButton.click();
    await page.waitForTimeout(500);

    // Select an agent
    const agentCount = await workspace.agentItems.count();
    if (agentCount > 0) {
      await workspace.agentItems.first().click();
      await page.waitForTimeout(200);
    }

    // Go to step 3 (Review)
    await workspace.nextButton.click();
    await page.waitForTimeout(300);

    // Review should show the selected model
    const modelName = modelText?.split(" · ")[0]?.trim();
    if (modelName) {
      await expect(page.getByText(modelName)).toBeVisible();
    }
  });
});

// ==========================================================================
// Execution (run project with local model)
// ==========================================================================

test.describe("Execution", () => {
  // Use a longer timeout for execution tests — local model inference can be slow
  test.setTimeout(180_000);

  test.skip(!!process.env.CI, "Requires a downloaded local model — skipped in CI");

  test("DC-WORKSPACE-EXEC-01: create project with Gemma model, execute, and verify execution completes", async ({ page }) => {
    const API = "http://127.0.0.1:18741/api/v1";
    const projectName = `Exec Test ${Date.now()}`;

    // 1. Get one agent ID
    const agentsResp = await page.request.get(`${API}/workspace/agents?page_size=5`);
    const agentsData = await agentsResp.json();
    const firstAgent = agentsData.agents?.[0];
    expect(firstAgent).toBeTruthy();

    // 2. Create project via API with local Gemma model
    const createResp = await page.request.post(`${API}/workspace/projects`, {
      data: {
        title: projectName,
        description: "Summarize the benefits of remote work in 2 sentences.",
        project_type: "workshop",
        selected_agents: [firstAgent.agent_id],
        model_id: "local:gemma3-1b",
      },
    });
    expect(createResp.status()).toBe(201);
    const createData = await createResp.json();
    const projectId = createData.project?.project_id;
    expect(projectId).toBeTruthy();

    // 3. Execute the project
    const execResp = await page.request.post(
      `${API}/workspace/projects/${projectId}/execute`
    );
    expect(execResp.status()).toBe(201);
    const execData = await execResp.json();
    expect(execData.execution_id || execData.success).toBeTruthy();

    // 4. Poll execution status until completed or failed (up to 120s)
    //    We check execution status (not project status) because the
    //    orchestrator background task updates execution directly.
    let finalStatus = "running";
    for (let i = 0; i < 60; i++) {
      await page.waitForTimeout(2000);

      // Check execution status
      const execStatusResp = await page.request.get(
        `${API}/workspace/projects/${projectId}/execution/latest`
      );
      if (execStatusResp.ok()) {
        const execStatusData = await execStatusResp.json();
        const execution = execStatusData.execution ?? execStatusData;
        finalStatus = execution.status ?? "unknown";
        if (finalStatus === "completed" || finalStatus === "failed") break;
      }

      // Also check project status as fallback
      const projResp = await page.request.get(`${API}/workspace/projects/${projectId}`);
      const projData = await projResp.json();
      const projStatus = projData.project?.status ?? projData.status;
      if (projStatus === "completed" || projStatus === "failed") {
        finalStatus = projStatus;
        break;
      }
    }
    expect(finalStatus).toBe("completed");

    // 5. Navigate to results page and verify UI
    await page.goto(`/workspace/${projectId}`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);

    await expect(page.getByText(projectName)).toBeVisible({ timeout: 10000 });

    // Should show Discussion and Compiled Output tabs
    await expect(workspace.discussionTab).toBeVisible();
    await expect(workspace.compiledTab).toBeVisible();

    // 6. Cleanup
    await page.request.delete(`${API}/workspace/projects/${projectId}`);
  });
});

// ==========================================================================
// Negative Workflows
// ==========================================================================

test.describe("Negative Workflows", () => {
  test("DC-WORKSPACE-NEG-01: filter with no results shows appropriate state", async ({ page }) => {
    await workspace.filterByStatus("Failed");

    await expect(page.locator("h1", { hasText: "Workspace" })).toBeVisible();
  });

  test("DC-WORKSPACE-NEG-02: navigating to invalid project ID shows error", async ({ page }) => {
    await page.goto("/workspace/nonexistent-project-id-12345");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);

    // Should show error state or "Failed to load project"
    const errorVisible = await page
      .getByText(/failed to load|error|not found/i)
      .first()
      .isVisible()
      .catch(() => false);

    const backButton = page.getByRole("button", { name: /back/i }).first();
    const backVisible = await backButton.isVisible().catch(() => false);

    // Should show either an error or a back button (not crash)
    expect(errorVisible || backVisible).toBeTruthy();
  });
});
