import { type Page, expect, test } from "@playwright/test";

// Next injects its own role=alert route announcer; target only app alerts.
const alertOf = (page: Page) => page.locator('[role="alert"]:not(#__next-route-announcer__)');

test.describe("SIGNAL end-to-end smoke", () => {
  test("overview shows live analytics from the seeded workspace", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("telling");
    await expect(page.getByText("Avg engagement rate")).toBeVisible();
    await expect(page.getByText("720").first()).toBeVisible();
    await expect(page.getByRole("list", { name: "The SIGNAL loop" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "What the history says" })).toBeVisible();
    await expect(page.getByText(/hit rate vs \d+% baseline/).first()).toBeVisible();
  });

  test("memory → filter → autopsy", async ({ page }) => {
    await page.goto("/memory");
    await expect(page.getByText(/Post archetypes/)).toBeVisible();
    await page.getByLabel("Platform").selectOption("LinkedIn");
    const rows = page.locator("tbody tr");
    await expect(rows.first()).toBeVisible();
    await rows.first().getByRole("link").click();
    await expect(page).toHaveURL(/\/memory\/\d+$/);
    await expect(page.getByRole("heading", { name: "Against the benchmark" })).toBeVisible();
    await expect(page.getByRole("heading", { name: /What history associates/ })).toBeVisible();
    await expect(page.getByText(/Did the model see it coming/)).toBeVisible();
    await expect(page.getByRole("link", { name: /Iterate in the Lab/ })).toBeVisible();
  });

  test("memory empty state when a search matches nothing", async ({ page }) => {
    await page.goto("/memory");
    await page.getByLabel("Search captions").fill("zzzzqqqq");
    await expect(page.getByText("No posts match these filters")).toBeVisible();
    await page.getByRole("button", { name: "Clear filters" }).click();
    await expect(page.locator("tbody tr").first()).toBeVisible();
  });

  test("lab predicts, validates, and creates an experiment from a suggestion", async ({ page }) => {
    await page.goto("/lab");
    await expect(page.getByText("Estimated engagement rate")).toBeVisible();
    await expect(page.getByText(/Chance of a top-quartile post/)).toBeVisible();
    const before = await page.locator(".display.num").first().innerText();

    await page.getByLabel("Platform").selectOption("TikTok");
    await expect(page.locator(".display.num").first()).not.toHaveText(before, { timeout: 20_000 });

    await page.getByRole("textbox", { name: "Caption", exact: true }).fill("");
    await expect(alertOf(page).filter({ hasText: "Add a caption" })).toBeVisible();
    await page.getByRole("textbox", { name: "Caption", exact: true }).fill("Why do most teams ignore reading engagement data? Save this. #data");
    await expect(page.getByText("Changes worth testing")).toBeVisible();

    const testButtons = page.getByRole("button", { name: "Test it" });
    if (await testButtons.count()) {
      await testButtons.first().click();
      await page.getByRole("button", { name: "Create experiment" }).click();
      await expect(page).toHaveURL(/\/experiments\/\d+$/);
      await expect(page.getByText("Did the model call it?")).toHaveCount(0); // no observations yet
      await expect(page.getByText("Collecting data")).toBeVisible();
    }
  });

  test("experiment detail: completed verdict, and logging validates input", async ({ page }) => {
    await page.goto("/experiments");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("One change");
    await page.getByRole("link", { name: /Numbered-list hook vs bold-claim/ }).click();
    await expect(page.getByText("Adopt variant").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "The comparison" })).toBeVisible();
    await expect(page.getByText(/not randomised/i).first()).toBeVisible();

    await page.goto("/experiments");
    await page.getByRole("link", { name: /Question hook vs story hook/ }).click();
    await expect(page.getByText("Collecting data").first()).toBeVisible();
    await expect(page.getByRole("button", { name: /Conclude/ })).toBeDisabled();
    await page.getByLabel("Impressions").fill("100");
    await page.getByLabel("Engagements").fill("500");
    await expect(alertOf(page).filter({ hasText: "can't exceed" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Add" })).toBeDisabled();
    await page.getByLabel("Engagements").fill("12");
    await page.getByRole("button", { name: "Add" }).click();
    await expect(page.getByText("Logged posts")).toBeVisible();
    await expect(page.getByRole("cell", { name: "12.00%" })).toBeVisible();
  });

  test("learning timeline lists recorded learnings", async ({ page }) => {
    await page.goto("/learning");
    await expect(page.getByText(/outperformed|no reliable difference/).first()).toBeVisible();
  });

  test("explore: pivot, drivers, segments, registry", async ({ page }) => {
    await page.goto("/explore");
    await expect(page.getByRole("heading", { name: "OLAP pivot" })).toBeVisible();
    await expect(page.locator("table tbody tr").first()).toBeVisible();
    await page.getByLabel("Rows", { exact: true }).selectOption("topic");
    await page.getByLabel("Pivot columns").selectOption("platform");
    await expect(page.getByRole("columnheader", { name: "LinkedIn" })).toBeVisible();

    await page.getByRole("tab", { name: "Drivers" }).click();
    await expect(page.getByText("Which attributes carry signal?")).toBeVisible();
    await expect(page.getByText(/Benjamini/).first()).toBeVisible();

    await page.getByRole("tab", { name: "Segments" }).click();
    await expect(page.getByText("Post archetypes").first()).toBeVisible();

    await page.getByRole("tab", { name: "Models & data" }).click();
    await expect(page.getByText("Multiple linear regression").first()).toBeVisible();
    await expect(page.getByText("Apriori").first()).toBeVisible();
    await expect(page.getByText("Bring your own data")).toBeVisible();
  });

  test("AI interpretation cites evidence and stays hedged", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Interpret this" }).click();
    await expect(page.getByText(/Deterministic reading|evidence-validated/)).toBeVisible();
    await page.getByRole("button", { name: /^E\d+$/ }).first().click();
    await expect(page.getByText(/historical associations/).first()).toBeVisible();
  });

  test("API failure shows an error state with retry", async ({ page }) => {
    await page.route("**/api/overview", (r) => r.fulfill({ status: 422, contentType: "application/json", body: JSON.stringify({ error: { code: "boom", message: "Deliberate failure" } }) }));
    await page.goto("/");
    await expect(alertOf(page)).toContainText("Deliberate failure");
    await page.unroute("**/api/overview");
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("telling");
  });

  test("responsive: no horizontal scroll at phone width, and keyboard skip link works", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    for (const path of ["/", "/memory", "/lab", "/experiments", "/explore"]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, `horizontal overflow on ${path}`).toBeLessThanOrEqual(1);
    }
    await page.goto("/");
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  });

  test("unknown ids degrade gracefully", async ({ page }) => {
    await page.goto("/memory/99999999");
    await expect(alertOf(page)).toContainText("not found");
    await page.goto("/experiments/abc");
    await expect(page.getByText("That isn't an experiment id")).toBeVisible();
  });
});
