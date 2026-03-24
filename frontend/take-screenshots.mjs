/**
 * Take marketing screenshots of ContextuAI Solo.
 * Completes setup wizard first, then captures each page.
 */
import { chromium } from 'playwright';
import fs from 'fs';

const BASE = 'http://localhost:1420';
const OUT = 'C:/Users/nagen/Projects/contextuai-solo/frontend/tests/e2e/screenshots/2026-03-23';

async function run() {
  fs.mkdirSync(OUT, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    colorScheme: 'dark',
  });

  const page = await context.newPage();

  // Step 1: Complete setup wizard
  console.log('Completing setup wizard...');
  await page.goto(BASE, { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(1500);

  // Check if wizard is showing
  const wizardVisible = await page.locator('text=What\'s your name').isVisible().catch(() => false);
  if (wizardVisible) {
    // Fill name and click Get Started
    await page.fill('input[placeholder="Sarah"]', 'Demo User');
    await page.click('text=Get Started');
    await page.waitForTimeout(1000);

    // Step 2: may have more wizard steps — try to skip through
    const nextBtn = page.locator('button:has-text("Next"), button:has-text("Get Started"), button:has-text("Skip"), button:has-text("Continue"), button:has-text("Finish")');
    for (let i = 0; i < 5; i++) {
      const visible = await nextBtn.first().isVisible().catch(() => false);
      if (visible) {
        await nextBtn.first().click();
        await page.waitForTimeout(1000);
      } else {
        break;
      }
    }
    console.log('Wizard completed');
  }

  // Set localStorage flags to bypass wizard on subsequent navigations
  await page.evaluate(() => {
    localStorage.setItem('setup-wizard-completed', 'true');
    localStorage.setItem('theme', 'dark');
  });

  await page.waitForTimeout(1000);

  // Step 2: Take screenshots of each page
  const shots = [
    { name: 'chat-main', url: '/' },
    { name: 'personas', url: '/personas' },
    { name: 'agents', url: '/agents' },
    { name: 'crews', url: '/crews' },
    { name: 'connections', url: '/connections' },
    { name: 'settings', url: '/settings' },
  ];

  for (const shot of shots) {
    console.log(`Taking: ${shot.name} (${shot.url})`);
    await page.goto(`${BASE}${shot.url}`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);
    await page.screenshot({
      path: `${OUT}/${shot.name}.png`,
      fullPage: false,
    });
    console.log(`  Saved: ${shot.name}.png`);
  }

  await browser.close();
  console.log('Done!');
}

run();
