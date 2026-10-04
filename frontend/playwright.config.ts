import { defineConfig, devices } from "@playwright/test";
import { join } from "node:path";

const root = join(__dirname, "..");
const port = process.env.E2E_PORT ?? "3100";
const apiPort = process.env.E2E_API_PORT ?? "8100";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: { baseURL: `http://localhost:${port}`, trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  // Boots the real stack (FastAPI + Next) against an isolated, freshly seeded database.
  webServer: {
    command: "node scripts/e2e-server.mjs",
    cwd: root,
    url: `http://localhost:${port}/api/health`,
    timeout: 180_000,
    reuseExistingServer: !process.env.CI,
    env: {
      PORT: port,
      API_PORT: apiPort,
      SIGNAL_SKIP_SETUP: "1",
      DATABASE_URL: `sqlite:///${join(root, "backend", "data", "e2e.db").replace(/\\/g, "/")}`,
      ARTIFACTS_DIR: join(root, "backend", "data", "e2e-artifacts"),
    },
  },
});
