/**
 * ContextuAI Solo Desktop — Navigation E2E Tests
 *
 * Tests the desktop sidebar navigation across all pages.
 * Frontend: http://localhost:1420 (Vite SPA)
 */
import { test, expect } from "@playwright/test";
import { NavigationPage } from "../fixtures/page-objects";

let nav: NavigationPage;

test.beforeEach(async ({ page }) => {
  nav = new NavigationPage(page);
  await nav.goto();
});

// DC-NAV-01: Sidebar shows all navigation items
test("DC-NAV-01: sidebar shows all navigation items", async () => {
  await expect(nav.sidebar).toBeVisible();

  const labels = await nav.getNavLabels();
  const expectedItems = ["Chat", "Model Hub", "Personas", "Agents", "Crews", "Blueprints", "Workspace", "Distributions", "Approvals", "Settings"];

  for (const item of expectedItems) {
    expect(labels).toContain(item);
  }

  expect(labels.length).toBe(10);
});

// DC-NAV-02: Navigate to each page and verify heading
test("DC-NAV-02: navigate to each page and verify heading", async ({ page }) => {
  const routes: { label: string; heading: string }[] = [
    { label: "Chat", heading: "Start a conversation" },
    { label: "Model Hub", heading: "Model Hub" },
    { label: "Personas", heading: "Personas" },
    { label: "Agents", heading: "Agent Library" },
    { label: "Crews", heading: "Crews" },
    { label: "Blueprints", heading: "Blueprints" },
    { label: "Workspace", heading: "Workspace" },
    { label: "Distributions", heading: "Distributions" },
    { label: "Approvals", heading: "Approval Queue" },
    { label: "Settings", heading: "Settings" },
  ];

  for (const route of routes) {
    await nav.navigateTo(route.label);
    await page.waitForTimeout(500);

    const headingEl = page.locator(`text=${route.heading}`).first();
    await expect(headingEl).toBeVisible({ timeout: 5000 });
  }
});

// DC-NAV-03: Active page is highlighted in sidebar
test("DC-NAV-03: active page is highlighted in sidebar", async ({ page }) => {
  await nav.navigateTo("Personas");
  await page.waitForTimeout(300);

  const personasLink = page.locator("aside nav a", { hasText: "Personas" });
  const classes = await personasLink.getAttribute("class");
  expect(classes).toContain("primary");

  await nav.navigateTo("Settings");
  await page.waitForTimeout(300);

  const settingsLink = page.locator("aside nav a", { hasText: "Settings" });
  const settingsClasses = await settingsLink.getAttribute("class");
  expect(settingsClasses).toContain("primary");

  // Personas should no longer be active
  const personasClassesAfter = await personasLink.getAttribute("class");
  expect(personasClassesAfter).not.toContain("bg-primary");
});

// DC-NAV-04: Sidebar collapse/expand toggle works
test("DC-NAV-04: sidebar collapse/expand toggle works", async ({ page }) => {
  await expect(nav.sidebar).toBeVisible();

  // Verify logo text visible when expanded
  await expect(page.locator("aside", { hasText: "Solo" })).toBeVisible();

  // Collapse
  await nav.collapseToggle.click();
  await page.waitForTimeout(500);

  const sidebar = nav.sidebar;
  const box = await sidebar.boundingBox();
  expect(box).toBeTruthy();
  expect(box!.width).toBeLessThan(100);

  // Labels should be hidden
  const labels = await nav.getNavLabels();
  expect(labels.length).toBe(0);

  // Expand
  await nav.collapseToggle.click();
  await page.waitForTimeout(500);

  const expandedBox = await sidebar.boundingBox();
  expect(expandedBox!.width).toBeGreaterThan(100);

  const expandedLabels = await nav.getNavLabels();
  expect(expandedLabels.length).toBe(10);
});

// DC-NAV-05: Page transitions are smooth (no flash)
test("DC-NAV-05: page transitions are smooth", async ({ page }) => {
  const routes = ["Personas", "Agents", "Crews", "Blueprints", "Workspace", "Distributions", "Approvals", "Settings", "Chat"];

  for (const route of routes) {
    await nav.navigateTo(route);
    await page.waitForTimeout(300);

    // Sidebar should remain visible throughout (SPA navigation)
    await expect(nav.sidebar).toBeVisible();

    // No error messages
    const hasError = await page
      .locator("text=/Something went wrong|Error|Unhandled/i")
      .isVisible()
      .catch(() => false);
    expect(hasError).toBeFalsy();
  }
});
