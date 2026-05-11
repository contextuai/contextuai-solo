/**
 * ContextuAI Solo Desktop — Personal Docs (folder mapping) E2E
 *
 * Route: "/knowledge"
 * Backend: http://127.0.0.1:18741 (no auth, desktop mode)
 *
 * Creates a KB, points a folder mapping at a temp directory of test
 * files, and verifies they're indexed (visible in the Documents tab).
 *
 * The bundled all-MiniLM-L6-v2 ONNX model must be present locally for
 * ingest to succeed. Without it, the job will move to status="error"
 * and the assertion at the end will fail.
 */
import { mkdirSync, mkdtempSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";

import { expect, test } from "@playwright/test";

const KB_NAME = `E2E Folders KB ${Date.now()}`;

test.describe("Personal Docs — folder mapping", () => {
  test("DC-KB-FOLDER: add folder, files appear in Documents tab", async ({
    page,
  }) => {
    // Skipped on CI runners: Tauri file picker unavailable in Playwright,
    // plus the embedding-model dependency. Verified manually in the
    // Tauri build; re-enable once CI bundles the ONNX weights.
    test.skip(!!process.env.CI, "Tauri modal test, skipped on CI");
    test.setTimeout(180_000);

    // Author a temp folder of supported files
    const dir = mkdtempSync(join(tmpdir(), "ctxai-personal-"));
    writeFileSync(
      join(dir, "alpha.md"),
      "# Alpha\nThe quick brown fox jumps over the lazy dog.",
    );
    mkdirSync(join(dir, "sub"));
    writeFileSync(
      join(dir, "sub", "bravo.txt"),
      "Bravo content for retrieval testing.",
    );

    await page.goto("http://localhost:1420/knowledge");
    await page.waitForLoadState("networkidle");

    // 1. Create a fresh KB
    await page.getByRole("button", { name: /^New$/ }).click();
    await page.getByPlaceholder(/Personal IRS docs/).fill(KB_NAME);
    await page.getByRole("button", { name: /^Create$/ }).click();
    await expect(
      page.locator("button", { hasText: KB_NAME }),
    ).toBeVisible({ timeout: 10_000 });

    // 2. Open the Folders tab
    await page.getByRole("button", { name: /^Folders$/ }).click();
    await expect(page.getByText(/No folder mappings yet/)).toBeVisible();

    // 3. Add a folder via the dev-mode text input (Tauri picker is
    //    unavailable in Playwright, so the input is editable)
    await page.getByRole("button", { name: /Add folder/i }).click();
    await page.getByPlaceholder(/Documents.Notes|Documents\\Notes/).fill(dir);
    await page.getByRole("button", { name: /^Add$/ }).click();

    // 4. Wait for the indexing job to finish (or for the friction modal
    //    to require confirmation — we synthesise a small folder so the
    //    threshold is not tripped). Allow up to 60s for the embedding
    //    pipeline to spin up cold.
    await expect(
      page.getByText(/done|added|files/i),
    ).toBeVisible({ timeout: 60_000 });

    // 5. Close the modal and switch to the Documents tab
    await page.getByRole("button", { name: /^Close$/ }).click().catch(() => {});
    await page.getByRole("button", { name: /^Documents$/ }).click();

    // 6. Confirm both files were ingested
    await expect(page.getByText("alpha.md")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("bravo.txt")).toBeVisible({ timeout: 10_000 });
  });
});
