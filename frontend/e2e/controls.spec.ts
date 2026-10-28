import { type Page, expect, test } from "@playwright/test";

// Every filter / button does what its label says. Effects are checked against the API, not just "no crash".

const alertOf = (page: Page) => page.locator('[role="alert"]:not(#__next-route-announcer__)');
const api = async (page: Page, path: string) => (await page.request.get(`/api${path}`)).json();
const matchCount = async (page: Page) => Number(((await page.getByText(/^[\d,]+ match$/).first().innerText()).replace(/\D/g, "")));
const optionsOf = async (page: Page, label: string) =>
  (await page.getByLabel(label, { exact: true }).first().locator("option").allTextContents()).filter((o) => o && o !== "All" && o !== "—");

test.describe("memory filters", () => {
  for (const [label, param] of [["Platform", "platform"], ["Topic", "topic"], ["Hook", "hook"], ["Tone", "tone"]] as const) {
    test(`${label} filter narrows the list to the API's count and can be reset`, async ({ page }) => {
      await page.goto("/memory");
      await expect(page.locator("tbody tr").first()).toBeVisible();
      const all = await matchCount(page);
      const value = (await optionsOf(page, label))[1];
      await page.getByLabel(label, { exact: true }).selectOption(value);
      const expected = (await api(page, `/posts?${param}=${encodeURIComponent(value)}&page_size=1`)).total;
      expect(expected).toBeGreaterThan(0);
      expect(expected).toBeLessThan(all);
      await expect(page.getByText(`${expected.toLocaleString("en-US")} match`)).toBeVisible();
      await page.getByLabel(label, { exact: true }).selectOption("");
      await expect(page.getByText(`${all.toLocaleString("en-US")} match`)).toBeVisible();
    });
  }

  test("Format options follow the chosen platform, and changing platform clears a stale format", async ({ page }) => {
    await page.goto("/memory");
    await expect.poll(async () => (await optionsOf(page, "Format")).length).toBeGreaterThan(0);
    const every = await optionsOf(page, "Format");
    await page.getByLabel("Platform", { exact: true }).selectOption("LinkedIn");
    const li = await optionsOf(page, "Format");
    expect(li.length).toBeGreaterThan(0);
    expect(li.length).toBeLessThanOrEqual(every.length);
    await page.getByLabel("Format", { exact: true }).selectOption(li[0]);
    const expected = (await api(page, `/posts?platform=LinkedIn&format=${encodeURIComponent(li[0])}&page_size=1`)).total;
    await expect(page.getByText(`${expected.toLocaleString("en-US")} match`)).toBeVisible();
    await page.getByLabel("Platform", { exact: true }).selectOption("X");
    await expect(page.getByLabel("Format", { exact: true })).toHaveValue("");
  });

  test("filters combine, search narrows further, Clear filters restores everything", async ({ page }) => {
    await page.goto("/memory");
    const all = await matchCount(page);
    await page.getByLabel("Platform", { exact: true }).selectOption("Instagram");
    await page.getByLabel("Tone", { exact: true }).selectOption((await optionsOf(page, "Tone"))[0]);
    const tone = await page.getByLabel("Tone", { exact: true }).inputValue();
    const both = (await api(page, `/posts?platform=Instagram&tone=${encodeURIComponent(tone)}&page_size=1`)).total;
    await expect(page.getByText(`${both.toLocaleString("en-US")} match`)).toBeVisible();
    await page.getByLabel("Search captions").fill("zzzzqqqq");
    await expect(page.getByText("No posts match these filters")).toBeVisible();
    await page.getByRole("button", { name: "Clear filters" }).click();
    await expect(page.getByText(`${all.toLocaleString("en-US")} match`)).toBeVisible();
    await expect(page.getByLabel("Platform", { exact: true })).toHaveValue("");
    await expect(page.getByLabel("Search captions")).toHaveValue("");
  });

  test("search matches captions per the API", async ({ page }) => {
    await page.goto("/memory");
    await page.getByLabel("Search captions").fill("data");
    const expected = (await api(page, "/posts?search=data&page_size=1")).total;
    await expect(page.getByText(`${expected.toLocaleString("en-US")} match`)).toBeVisible();
  });

  test("sort, order toggle and pagination reorder rows exactly like the API", async ({ page }) => {
    await page.goto("/memory");
    const firstId = async () => Number((await page.locator("tbody tr").first().getByRole("link").getAttribute("href"))!.split("/").pop());
    await expect(page.locator("tbody tr").first()).toBeVisible();

    await page.getByLabel("Sort").selectOption("impressions");
    let want = (await api(page, "/posts?sort=impressions&order=desc&page_size=20")).items[0].post_id;
    await expect.poll(firstId).toBe(want);

    await page.getByRole("button", { name: /^Order:/ }).click();
    await expect(page.getByRole("button", { name: "Order: ascending" })).toBeVisible();
    want = (await api(page, "/posts?sort=impressions&order=asc&page_size=20")).items[0].post_id;
    await expect.poll(firstId).toBe(want);

    for (const sort of ["perf_index", "engagement_rate", "published_at"]) {
      await page.getByLabel("Sort").selectOption(sort);
      want = (await api(page, `/posts?sort=${sort}&order=asc&page_size=20`)).items[0].post_id;
      await expect.poll(firstId, { message: sort }).toBe(want);
    }

    await page.getByRole("button", { name: "Prev", exact: true }).isDisabled().then((d) => expect(d).toBe(true));
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await expect(page.getByText(/^Page 2 of/)).toBeVisible();
    want = (await api(page, "/posts?sort=published_at&order=asc&page_size=20&page=2")).items[0].post_id;
    await expect.poll(firstId).toBe(want);
    await page.getByRole("button", { name: "Prev", exact: true }).click();
    await expect(page.getByText(/^Page 1 of/)).toBeVisible();
  });

  test("changing a filter returns to page 1", async ({ page }) => {
    await page.goto("/memory");
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await expect(page.getByText(/^Page 2 of/)).toBeVisible();
    await page.getByLabel("Platform", { exact: true }).selectOption("LinkedIn");
    await expect(page.getByText(/^Page 1 of/)).toBeVisible();
  });
});

test.describe("overview", () => {
  test("platform chips switch the trend and report pressed state; CTAs navigate", async ({ page }) => {
    await page.goto("/");
    const chips = page.locator("button[aria-pressed]");
    await expect(chips.first()).toBeVisible();
    const n = await chips.count();
    expect(n).toBeGreaterThan(2);
    for (let i = 0; i < n; i++) {
      await chips.nth(i).click();
      await expect(chips.nth(i)).toHaveAttribute("aria-pressed", "true");
      await expect(page.locator("button[aria-pressed='true']")).toHaveCount(1);
    }
    await page.getByRole("link", { name: "Score a draft", exact: true }).click();
    await expect(page).toHaveURL(/\/lab/);
    await page.goto("/");
    await page.getByRole("link", { name: "Explore the data", exact: true }).click();
    await expect(page).toHaveURL(/\/explore/);
  });

  test("'Try in Lab' prefills the lab", async ({ page }) => {
    await page.goto("/");
    const link = page.getByRole("link", { name: /Try in Lab/ }).first();
    await expect(link).toBeVisible();
    await link.click();
    await expect(page).toHaveURL(/\/lab\?prefill=/);
    await expect(page.getByText("Estimated engagement rate")).toBeVisible();
  });
});

test.describe("lab", () => {
  test("every draft control re-scores, and a suggestion becomes an experiment (Cancel also works)", async ({ page }) => {
    await page.goto("/lab");
    await expect(page.getByText("Estimated engagement rate")).toBeVisible();
    for (const id of ["lab-topic", "lab-hook", "lab-tone", "lab-format"]) {
      const sel = page.locator(`#${id}`);
      const opts = await sel.locator("option").evaluateAll((os) => os.map((o) => (o as HTMLOptionElement).value));
      expect(opts.length).toBeGreaterThan(1);
      const current = await sel.inputValue();
      const next = opts.find((o) => o !== current)!;
      await sel.selectOption(next);
      await expect(sel).toHaveValue(next);
      await expect(page.getByText("Estimated engagement rate")).toBeVisible();
    }
    const test_it = page.getByRole("button", { name: "Test it" }).first();
    await expect(test_it).toBeVisible({ timeout: 20_000 });
    await test_it.click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await test_it.click();
    await page.getByRole("button", { name: "Create experiment" }).click();
    await expect(page).toHaveURL(/\/experiments\/\d+$/);
  });

  test("AI interpret + regenerate buttons work in the lab", async ({ page }) => {
    await page.goto("/lab");
    await page.getByRole("button", { name: "Interpret this" }).click();
    await expect(page.getByRole("button", { name: "Regenerate" })).toBeVisible({ timeout: 30_000 });
    await expect(alertOf(page)).toHaveCount(0);
  });
});

test.describe("experiments", () => {
  test("New experiment: validation hint, Cancel, then create navigates to the new experiment", async ({ page }) => {
    await page.goto("/experiments");
    await page.getByRole("button", { name: "New experiment" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("button", { name: "Create" })).toBeDisabled();
    await expect(dialog.getByText(/To create: add/)).toBeVisible();
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(dialog).toHaveCount(0);

    await page.getByRole("button", { name: "New experiment" }).click();
    await dialog.getByLabel("Name").fill("Control test: short vs long");
    await dialog.getByLabel("Hypothesis").fill("Shorter captions earn more engagement.");
    const descs = dialog.locator("input[type='text'], input:not([type])");
    const n = await descs.count();
    for (let i = 0; i < n; i++) if (!(await descs.nth(i).inputValue())) await descs.nth(i).fill(i % 2 ? "Long caption" : "Short caption");
    await expect(dialog.getByRole("button", { name: "Create" })).toBeEnabled();
    await dialog.getByRole("button", { name: "Create" }).click();
    await expect(page).toHaveURL(/\/experiments\/\d+$/);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Control test");
  });

  test("disabled actions say why, and Conclude works once every variant has enough posts", async ({ page }) => {
    await page.goto("/experiments");
    await page.getByRole("link", { name: /Question hook vs story hook/ }).click();
    await expect(page).toHaveURL(/\/experiments\/\d+$/);
    const id = page.url().split("/").pop();
    await expect(page.getByRole("button", { name: /Conclude/ })).toBeDisabled();
    await expect(page.getByText("Conclude is unavailable yet.")).toBeVisible();
    await expect(page.getByText(/To add a post: enter impressions/)).toBeVisible();

    const exp = await api(page, `/experiments/${id}`);
    for (const v of exp.variants) {
      for (let i = v.n; i < exp.min_per_variant; i++) {
        const r = await page.request.post(`/api/experiments/${id}/observations`, {
          data: { variant_id: v.id, published_at: "2026-09-01T12:00:00", impressions: 1000, engagements: 40 + ((i * 7) % 25) + (v.is_control ? 0 : 20), saves: 0 },
        });
        expect(r.ok()).toBeTruthy();
      }
    }
    await page.reload();
    const conclude = page.getByRole("button", { name: /Conclude/ });
    await expect(conclude).toBeEnabled();
    await conclude.click();
    await expect(page.getByRole("button", { name: /Conclude/ })).toHaveCount(0);
    await expect(page.getByText("completed").first()).toBeVisible();
    await page.goto("/learning");
    await expect(page.getByText(/Question hook|story hook|outperformed|no reliable difference/i).first()).toBeVisible();
  });

  test("experiment cards are links", async ({ page }) => {
    await page.goto("/experiments");
    const cards = page.locator("main a[href^='/experiments/']");
    await expect(cards.first()).toBeVisible();
    await cards.first().click();
    await expect(page).toHaveURL(/\/experiments\/\d+$/);
  });
});

test.describe("explore", () => {
  test("pivot controls (rows, drill-down, column, measure, slice/dice, subtotals) change the result", async ({ page }) => {
    await page.goto("/explore");
    await expect(page.locator("table tbody tr").first()).toBeVisible();
    const scope = async () => (await page.getByText(/[\d,]+ posts in scope/).first().innerText());
    const total = await scope();

    await page.getByLabel("Platform", { exact: true }).selectOption("LinkedIn");
    await expect.poll(scope).not.toBe(total);
    const li = (await api(page, "/posts?platform=LinkedIn&page_size=1")).total;
    await expect(page.getByText(`${li.toLocaleString("en-US")} posts in scope`)).toBeVisible();
    await page.getByLabel("Platform", { exact: true }).selectOption("");
    await expect(page.getByText(total)).toBeVisible();

    for (const id of ["Format", "Topic", "Hook", "Tone"]) {
      const opts = await optionsOf(page, id);
      await page.getByLabel(id, { exact: true }).selectOption(opts[0]);
      await expect(page.locator("table tbody tr").first()).toBeVisible();
      await page.getByLabel(id, { exact: true }).selectOption("");
    }

    const sub = page.getByLabel("Subtotals (roll-up)");
    await expect(sub).toBeEnabled();
    const rowsWith = await page.locator("table tbody tr").count();
    await sub.uncheck();
    await expect.poll(() => page.locator("table tbody tr").count()).toBeLessThan(rowsWith);
    await sub.check();

    await page.getByLabel("Then by (drill-down 2)").selectOption({ index: 1 });
    await expect(page.locator("table tbody tr").first()).toBeVisible();

    await page.getByLabel("Pivot columns").selectOption("daypart");
    await expect(page.getByRole("columnheader", { name: "Morning" })).toBeVisible();
    await page.getByLabel("Cell measure").selectOption({ index: 2 });
    await expect(page.getByRole("columnheader", { name: "Morning" })).toBeVisible();
  });

  test("pivot SQL panel opens and its copy button reports success", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.goto("/explore");
    await expect(page.locator("table tbody tr").first()).toBeVisible();
    await page.getByText("Show the SQL for this view").click();
    await expect(page.getByLabel("SQL for the current pivot", { exact: true })).toContainText("FROM fact_post f");
    await page.getByRole("button", { name: "Copy SQL for the current pivot" }).click();
    await expect(page.getByRole("button", { name: "Copy SQL for the current pivot" })).toContainText("Copied");
    expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("GROUP BY");
  });

  test("tabs switch and deep-link, 'Retrain all' re-runs models", async ({ page }) => {
    await page.goto("/explore?tab=drivers");
    await expect(page.getByText("Which attributes carry signal?")).toBeVisible();
    await page.getByRole("tab", { name: "OLAP pivot" }).click();
    await expect(page).toHaveURL(/tab=pivot/);
    await page.getByRole("tab", { name: "Models & data" }).click();
    const before = (await api(page, "/models")).total_runs_stored;
    await page.getByRole("button", { name: "Retrain all (force)" }).click();
    await expect.poll(async () => (await api(page, "/models")).total_runs_stored, { timeout: 60_000 }).toBeGreaterThan(before);
    await expect(alertOf(page)).toHaveCount(0);
  });

  test("CSV importer: a full import commits, reports, and retrains", async ({ page }) => {
    await page.goto("/explore?tab=models");
    const template = await (await page.request.get("/api/ingest/template.csv")).text();
    const header = template.split(/\r?\n/)[0];
    const cols = header.split(",");
    const rows = [0, 1].map((i) => cols.map((c) => ({ external_id: `ctl-${Date.now()}-${i}`, platform: "LinkedIn", format: "Text", topic: "Testing", hook_type: "Question", tone: "Direct", caption: "A question about testing?", published_at: "2026-08-01 10:00", impressions: "1000", reach: "800", likes: "30", comments: "5", shares: "3", saves: "2", media_count: "1" } as Record<string, string>)[c] ?? "").join(","));
    await page.locator("input[type='file']").setInputFiles({ name: "two-rows.csv", mimeType: "text/csv", buffer: Buffer.from([header, ...rows].join("\n")) });
    const before = (await api(page, "/health")).posts;
    const go = page.getByRole("button", { name: "Import and retrain" });
    await expect(go).toBeEnabled();
    await go.click();
    await expect(page.getByRole("status").filter({ hasText: /loaded|imported|rows/i }).first()).toBeVisible({ timeout: 60_000 });
    expect((await api(page, "/health")).posts).toBe(before + 2);
  });

  test("CSV importer: choose file → preview → cancel; template link downloads", async ({ page }) => {
    await page.goto("/explore?tab=models");
    const href = await page.getByRole("link", { name: /Download template/ }).getAttribute("href");
    const csv = await (await page.request.get(href!)).text();
    expect(csv.split("\n")[0]).toContain("platform");
    await page.locator("input[type='file']").setInputFiles({ name: "posts.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
    const cancel = page.getByRole("button", { name: "Cancel" });
    await expect(cancel).toBeVisible();
    await expect(page.getByRole("button", { name: /Import and retrain|Replace data and retrain/ })).toBeVisible();
    await cancel.click();
    await expect(cancel).toHaveCount(0);
  });
});

test.describe("methods page", () => {
  test("lists every algorithm with live source, metrics and working controls", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.goto("/methods");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Under the hood");
    for (const name of ["ETL", "Dimensional warehouse", "OLAP engine", "Linear regression", "Multiple linear regression", "Mutual information", "Decision tree", "Gaussian Naive Bayes", "K-Means clustering", "Agglomerative clustering", "Apriori association rules", "Similarity search", "Experiment comparison"]) {
      await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
    }
    // star schema is derived from the models
    await expect(page.getByText("fact_post").first()).toBeVisible();

    // OLAP operations: every tab shows SQL + a result
    for (const op of ["Roll-up", "Drill-down", "Slice", "Dice", "Pivot", "Roll-up with subtotals"]) {
      await page.getByRole("tab", { name: op, exact: true }).click();
      await expect(page.getByRole("tab", { name: op, exact: true })).toHaveAttribute("aria-selected", "true");
      await expect(page.getByRole("tabpanel")).toContainText("SELECT");
      await expect(page.getByRole("tabpanel").locator("table").first()).toBeVisible();
    }
    await expect(page.getByRole("tabpanel")).toContainText("ROLLUP");
    await page.getByRole("button", { name: "Copy Roll-up with subtotals SQL" }).click();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("GROUP BY ROLLUP");

    // family filter
    const group = page.getByRole("group", { name: "Filter algorithms by family" });
    await group.getByRole("button", { name: /^Predictive/ }).click();
    await expect(page.getByRole("heading", { name: "Decision tree", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "K-Means clustering", exact: true })).toHaveCount(0);
    await group.getByRole("button", { name: /^Descriptive/ }).click();
    await expect(page.getByRole("heading", { name: "K-Means clustering", exact: true })).toBeVisible();
    await group.getByRole("button", { name: /^All/ }).click();

    // source + metrics are real
    const tree = page.locator("#decision_tree");
    await expect(tree.getByText("Latest stored run")).toBeVisible();
    await tree.getByText("View source").click();
    await expect(tree.getByLabel("Source of decision_tree", { exact: true })).toContainText("DecisionTreeClassifier");
    await tree.getByRole("button", { name: "Copy Source of decision_tree" }).click();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("def decision_tree");
  });

  test("nav and in-page links work, with no horizontal overflow on a phone", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: /Methods/ }).click();
    await expect(page).toHaveURL(/\/methods$/);
    await page.getByRole("link", { name: "OLAP queries" }).click();
    await expect(page).toHaveURL(/#olap$/);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/methods");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
