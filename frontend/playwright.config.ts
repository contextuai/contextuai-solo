import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for ContextuAI Solo desktop app E2E tests.
 *
 * Frontend: Vite + React SPA on http://localhost:1420
 * Backend:  FastAPI on http://127.0.0.1:18741
 * Auth:     Bypassed (static admin user, no login required)
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["html", { open: "never" }]],
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  globalSetup: "./tests/e2e/global-setup.ts",

  use: {
    baseURL: "http://localhost:1420",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
    storageState: {
      cookies: [],
      origins: [
        {
          origin: "http://localhost:1420",
          localStorage: [
            {
              name: "contextuai-solo-wizard",
              value: JSON.stringify({ completed: true, name: "Test User" }),
            },
          ],
        },
      ],
    },
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
