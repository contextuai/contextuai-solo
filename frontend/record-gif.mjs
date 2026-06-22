/**
 * Record a marketing demo GIF of ContextuAI Solo.
 * Navigates through key features with smooth transitions.
 * Outputs directly to the marketing site as solo-demo.gif.
 *
 * Prerequisites:
 *   1. Backend running on port 18741
 *   2. Frontend running on port 1420
 *   3. ffmpeg installed (for webm → gif conversion)
 *
 * Usage:  node record-gif.mjs
 */
import { chromium } from "playwright";
import { execFileSync } from "child_process";
import fs from "fs";
import path from "path";

const BASE = "http://localhost:1420";
const TEMP_DIR = "C:/Users/nagen/Projects/3_CONTEXTUAI/contextuai-solo/frontend/.gif-temp";
const OUT_GIF = "C:/Users/nagen/Projects/3_CONTEXTUAI/contextuai-marketing-site/public/images/solo/solo-demo.gif";

async function safeClick(locator, timeout = 3000) {
  try { await locator.click({ timeout }); return true; } catch { return false; }
}

async function run() {
  fs.mkdirSync(TEMP_DIR, { recursive: true });

  console.log("\n🎬 Recording ContextuAI Solo demo GIF...\n");

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    colorScheme: "dark",
    recordVideo: {
      dir: TEMP_DIR,
      size: { width: 1280, height: 800 },
    },
  });

  const page = await context.newPage();

  // Bypass wizard
  await page.goto(BASE, { waitUntil: "networkidle", timeout: 20000 });
  await page.waitForTimeout(1000);
  await page.evaluate(() => {
    localStorage.setItem("setup-wizard-completed", "true");
    localStorage.setItem("theme", "dark");
  });

  const wizardVisible = await page.locator('text=What\'s your name').isVisible().catch(() => false);
  if (wizardVisible) {
    await page.fill('input[placeholder="Sarah"]', 'Demo User');
    await safeClick(page.locator('button:has-text("Get Started")'));
    await page.waitForTimeout(800);
    for (let i = 0; i < 5; i++) {
      const btn = page.locator('button:has-text("Next"), button:has-text("Skip"), button:has-text("Continue"), button:has-text("Finish")').first();
      if (await btn.isVisible().catch(() => false)) { await btn.click(); await page.waitForTimeout(800); }
      else break;
    }
  }

  // Reseed for clean state
  try {
    await page.evaluate(() => fetch('http://127.0.0.1:18741/api/v1/desktop/reseed', { method: 'POST' }));
    await page.waitForTimeout(2000);
  } catch {}

  // Helper: navigate via URL
  async function goTo(route, label) {
    console.log(`  📸 ${label}`);
    await page.goto(`${BASE}${route}`, { waitUntil: "networkidle", timeout: 12000 });
    await page.waitForTimeout(1800);
  }

  // ═══ SCENE 1: Chat (3s) ═══
  await goTo("/", "Chat");
  await page.waitForTimeout(1500);

  // ═══ SCENE 2: Agents (3s) ═══
  await goTo("/agents", "Agents");
  await page.mouse.wheel(0, 300);
  await page.waitForTimeout(1500);

  // ═══ SCENE 3: Crews (3s) ═══
  await goTo("/crews", "Crews");
  await page.waitForTimeout(1500);

  // ═══ SCENE 4: Crew Builder — open and show step 1 (3s) ═══
  console.log("  📸 Crew Builder");
  await safeClick(page.locator('button:has-text("New Crew")'));
  await page.waitForTimeout(2000);
  await page.keyboard.press("Escape");
  await page.waitForTimeout(800);

  // ═══ SCENE 5: Knowledge Base (2.5s) ═══
  await goTo("/knowledge", "Knowledge Base");
  await page.waitForTimeout(1000);

  // ═══ SCENE 6: Automations (2.5s) ═══
  await goTo("/automations", "Automations");
  await page.waitForTimeout(1000);

  // ═══ SCENE 7: Connections (3s) ═══
  await goTo("/connections", "Connections");
  await page.mouse.wheel(0, 200);
  await page.waitForTimeout(1500);

  // ═══ SCENE 8: Model Hub (3s) ═══
  await goTo("/models", "Model Hub");
  await page.mouse.wheel(0, 300);
  await page.waitForTimeout(1500);

  // ═══ SCENE 9: Blueprints (2.5s) ═══
  await goTo("/blueprints", "Blueprints");
  await page.waitForTimeout(1000);

  // ═══ SCENE 10: Coder Mode (3s) ═══
  await goTo("/coder/projects", "Coder Mode");
  await page.waitForTimeout(1500);

  // ═══ SCENE 11: Settings — AI Providers (2.5s) ═══
  await goTo("/settings", "Settings");
  await safeClick(page.locator('button:has-text("AI Providers"), [role="tab"]:has-text("AI Providers")').first());
  await page.waitForTimeout(1500);

  // ═══ SCENE 12: Back to Chat — final (2s) ═══
  await goTo("/", "Chat (final)");
  await page.waitForTimeout(1500);

  // Save video
  console.log("\n  Saving recording...");
  await page.close();

  const video = page.video();
  let webmPath;
  if (video) {
    webmPath = await video.path();
    console.log(`  WebM saved: ${webmPath}`);
  }

  await context.close();
  await browser.close();

  if (!webmPath) {
    console.log("ERROR: No video recorded.");
    return;
  }

  // Convert WebM → GIF using ffmpeg (two-pass with palette for quality)
  console.log("\n  Converting to GIF (two-pass with palette)...");
  const palette = path.join(TEMP_DIR, "palette.png");

  try {
    // Pass 1: generate palette
    execFileSync("ffmpeg", [
      "-y", "-i", webmPath,
      "-vf", "fps=8,scale=960:-1:flags=lanczos,palettegen=max_colors=128:stats_mode=diff",
      palette
    ], { stdio: "pipe" });

    // Pass 2: render GIF with palette
    execFileSync("ffmpeg", [
      "-y", "-i", webmPath, "-i", palette,
      "-lavfi", "fps=8,scale=960:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3",
      OUT_GIF
    ], { stdio: "pipe" });

    const stats = fs.statSync(OUT_GIF);
    const sizeMB = (stats.size / 1024 / 1024).toFixed(1);
    console.log(`\n✅ GIF saved: ${OUT_GIF}`);
    console.log(`   Size: ${sizeMB} MB\n`);
  } catch (e) {
    console.log("FFmpeg conversion failed:", e.message);
    console.log("WebM file available at:", webmPath);
  }

  // Cleanup temp
  try {
    fs.rmSync(TEMP_DIR, { recursive: true, force: true });
  } catch {}
}

run().catch(console.error);
