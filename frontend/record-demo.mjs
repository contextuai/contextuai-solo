/**
 * Record a ~2 minute marketing demo video of ContextuAI Solo.
 * Navigates through all major features with realistic interactions.
 * Output: docs/solo-demo.webm → docs/solo-demo.mp4
 */
import { chromium } from "playwright";

const BASE = "http://localhost:1420";
const OUT_WEBM = "C:/Users/nagen/Projects/contextuai-solo/docs/solo-demo.webm";
const OUT_MP4 = "C:/Users/nagen/Projects/contextuai-solo/docs/solo-demo.mp4";

/** Safe click — won't crash if element is missing or disabled */
async function safeClick(locator, timeout = 3000) {
  try {
    await locator.click({ timeout });
    return true;
  } catch {
    return false;
  }
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    colorScheme: "dark",
    recordVideo: {
      dir: "C:/Users/nagen/Projects/contextuai-solo/docs/",
      size: { width: 1920, height: 1080 },
    },
    storageState: {
      cookies: [],
      origins: [{
        origin: BASE,
        localStorage: [
          { name: "contextuai-solo-wizard", value: JSON.stringify({ completed: true, name: "Demo User" }) },
          { name: "contextuai-solo-ai-mode", value: "local" },
        ],
      }],
    },
  });

  const page = await context.newPage();

  // Helper: navigate via sidebar (close any modals first)
  async function navTo(label) {
    // Dismiss any open modals
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
    try {
      await page.locator("aside nav a", { hasText: label }).click({ timeout: 5000 });
      await page.waitForLoadState("networkidle");
    } catch {
      // If sidebar is obscured, go direct
      const routes = { Chat: "/", "Model Hub": "/models", Agents: "/agents", Crews: "/crews", Blueprints: "/blueprints", Workshop: "/workshop", Connections: "/connections", Personas: "/personas", Settings: "/settings" };
      await page.goto(`${BASE}${routes[label] || "/"}`, { waitUntil: "networkidle", timeout: 10000 });
    }
    await page.waitForTimeout(2000);
  }

  // ═════════════════════════════════════════════════════════════
  // SCENE 1: Chat — type and send a message (15s)
  // ═════════════════════════════════════════════════════════════
  console.log("Scene 1: Chat");
  await page.goto(BASE, { waitUntil: "networkidle", timeout: 15000 });
  await page.waitForTimeout(2500);

  const chatInput = page.locator('textarea[placeholder="Ask me anything..."]');
  try {
    await chatInput.click({ timeout: 3000 });
    await page.waitForTimeout(400);
    const msg = "What are 5 creative marketing strategies for a SaaS startup on a tight budget?";
    for (let i = 0; i < msg.length; i++) {
      await chatInput.fill(msg.slice(0, i + 1));
      await page.waitForTimeout(25);
    }
    await page.waitForTimeout(800);
    await chatInput.press("Enter");
    await page.waitForTimeout(12000); // wait for streaming
    await page.mouse.wheel(0, 300);
    await page.waitForTimeout(2000);
  } catch (e) {
    console.log("Chat input skipped:", e.message?.slice(0, 60));
    await page.waitForTimeout(3000);
  }

  // ═════════════════════════════════════════════════════════════
  // SCENE 2: Model Hub (12s)
  // ═════════════════════════════════════════════════════════════
  console.log("Scene 2: Model Hub");
  await navTo("Model Hub");
  await page.waitForTimeout(1500);
  await page.mouse.wheel(0, 400);
  await page.waitForTimeout(2000);
  await page.mouse.wheel(0, 400);
  await page.waitForTimeout(2000);
  await page.mouse.wheel(0, -800);
  await page.waitForTimeout(1500);
  await safeClick(page.locator("button", { hasText: "Coding" }));
  await page.waitForTimeout(1500);
  await safeClick(page.locator("button", { hasText: /^All$/ }));
  await page.waitForTimeout(1500);

  // ═════════════════════════════════════════════════════════════
  // SCENE 3: Agent Library (10s)
  // ═════════════════════════════════════════════════════════════
  console.log("Scene 3: Agents");
  await navTo("Agents");
  await page.waitForTimeout(1000);
  await page.mouse.wheel(0, 500);
  await page.waitForTimeout(2000);
  await page.mouse.wheel(0, 500);
  await page.waitForTimeout(2000);
  await page.mouse.wheel(0, -1000);
  await page.waitForTimeout(1500);

  // ═════════════════════════════════════════════════════════════
  // SCENE 4: Crews — show wizard (15s)
  // ═════════════════════════════════════════════════════════════
  console.log("Scene 4: Crews");
  await navTo("Crews");
  await page.waitForTimeout(1000);

  // Just show the crews page — don't open wizard (avoids modal traps)
  await page.waitForTimeout(2000);
  await page.mouse.wheel(0, 300);
  await page.waitForTimeout(2000);
  await page.mouse.wheel(0, -300);
  await page.waitForTimeout(1500);

  // ═════════════════════════════════════════════════════════════
  // SCENE 5: Blueprints (8s)
  // ═════════════════════════════════════════════════════════════
  console.log("Scene 5: Blueprints");
  await navTo("Blueprints");
  await page.waitForTimeout(1500);
  await page.mouse.wheel(0, 400);
  await page.waitForTimeout(2000);
  await page.mouse.wheel(0, -400);
  await page.waitForTimeout(1500);

  // ═════════════════════════════════════════════════════════════
  // SCENE 6: Workshop (8s)
  // ═════════════════════════════════════════════════════════════
  console.log("Scene 6: Workshop");
  await navTo("Workshop");
  await page.waitForTimeout(1500);
  const brainstormClicked = await safeClick(page.locator("button", { hasText: /new.*brainstorm|new.*project|start/i }).first());
  if (brainstormClicked) {
    await page.waitForTimeout(2500);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(1000);
  } else {
    await page.waitForTimeout(3000);
  }

  // ═════════════════════════════════════════════════════════════
  // SCENE 7: Connections (8s)
  // ═════════════════════════════════════════════════════════════
  console.log("Scene 7: Connections");
  await navTo("Connections");
  await page.waitForTimeout(1500);
  await page.mouse.wheel(0, 300);
  await page.waitForTimeout(2000);
  await page.mouse.wheel(0, -300);
  await page.waitForTimeout(1500);

  // ═════════════════════════════════════════════════════════════
  // SCENE 8: Personas — show wizard (10s)
  // ═════════════════════════════════════════════════════════════
  console.log("Scene 8: Personas");
  await navTo("Personas");
  await page.waitForTimeout(1000);
  const personaClicked = await safeClick(page.locator("button", { hasText: /create persona/i }).first());
  if (personaClicked) {
    await page.waitForTimeout(3000);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(1000);
  } else {
    await page.waitForTimeout(3000);
  }

  // ═════════════════════════════════════════════════════════════
  // SCENE 9: Settings (8s)
  // ═════════════════════════════════════════════════════════════
  console.log("Scene 9: Settings");
  await navTo("Settings");
  await page.waitForTimeout(1500);
  await page.mouse.wheel(0, 400);
  await page.waitForTimeout(2500);
  await page.mouse.wheel(0, -400);
  await page.waitForTimeout(1500);

  // ═════════════════════════════════════════════════════════════
  // SCENE 10: Back to Chat — final shot (3s)
  // ═════════════════════════════════════════════════════════════
  console.log("Scene 10: Final shot");
  await navTo("Chat");
  await page.waitForTimeout(3000);

  // ═════════════════════════════════════════════════════════════
  // DONE — save video
  // ═════════════════════════════════════════════════════════════
  console.log("Recording complete. Saving...");
  await page.close();

  const video = page.video();
  if (video) {
    const path = await video.path();
    console.log("Raw video at:", path);
    const fs = await import("fs");
    fs.copyFileSync(path, OUT_WEBM);
    console.log("Saved to:", OUT_WEBM);
  }

  await context.close();
  await browser.close();
  console.log("Done! Run ffmpeg to convert to MP4.");
}

run().catch(console.error);
