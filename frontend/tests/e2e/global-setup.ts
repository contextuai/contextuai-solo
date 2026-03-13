/**
 * Global setup for ContextuAI Solo desktop E2E tests.
 *
 * Verifies that both the backend and frontend are running,
 * then triggers a reseed to ensure a clean data state.
 */

const BACKEND_URL = "http://127.0.0.1:18741";
const FRONTEND_URL = "http://localhost:1420";

async function checkService(url: string, label: string, retries = 3): Promise<void> {
  for (let i = 0; i < retries; i++) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(5000) });
      if (res.ok) return;
    } catch {
      // retry
    }
    if (i < retries - 1) {
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
  throw new Error(
    `${label} is not reachable at ${url}. ` +
      `Make sure it is running before executing E2E tests.`
  );
}

export default async function globalSetup(): Promise<void> {
  console.log("[global-setup] Verifying backend health...");
  await checkService(BACKEND_URL, "Backend");

  console.log("[global-setup] Verifying frontend is served...");
  await checkService(FRONTEND_URL, "Frontend");

  console.log("[global-setup] Triggering data reseed...");
  try {
    const res = await fetch(`${BACKEND_URL}/api/v1/desktop/reseed`, {
      method: "POST",
      signal: AbortSignal.timeout(15_000),
    });
    if (res.ok) {
      console.log("[global-setup] Reseed completed successfully.");
    } else {
      console.warn(
        `[global-setup] Reseed returned ${res.status}. Tests will run with existing data.`
      );
    }
  } catch (err) {
    console.warn("[global-setup] Reseed request failed:", err);
    console.warn("[global-setup] Tests will run with existing data.");
  }
}
