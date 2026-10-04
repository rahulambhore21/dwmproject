// Starts the dev stack against a brand-new e2e database so tests never depend on earlier runs.
import { rmSync } from "node:fs";
import { join } from "node:path";
import { BACKEND } from "./lib.mjs";

rmSync(join(BACKEND, "data", "e2e.db"), { force: true });
rmSync(join(BACKEND, "data", "e2e-artifacts"), { recursive: true, force: true });
await import("./dev.mjs");
