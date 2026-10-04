// Runs on `npm install` at the repo root: installs the frontend and the backend virtualenv.
import { createHash } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { BACKEND, FRONTEND, ROOT, ensureVenv, run, venvPython } from "./lib.mjs";

if (process.env.SIGNAL_SKIP_SETUP === "1") process.exit(0);

if (!existsSync(join(FRONTEND, "node_modules"))) {
  console.log("[signal] installing frontend dependencies...");
  if (run("npm", ["--prefix", FRONTEND, "install", "--no-audit", "--no-fund"], { cwd: ROOT }) !== 0) process.exit(1);
}

if (!ensureVenv()) process.exit(0); // do not fail the whole install if Python is missing; dev.mjs explains

const req = join(BACKEND, "requirements-dev.txt");
const stamp = join(BACKEND, ".venv", ".requirements.sha256");
const hash = createHash("sha256")
  .update(readFileSync(join(BACKEND, "requirements.txt")))
  .update(readFileSync(req))
  .digest("hex");
if (!existsSync(stamp) || readFileSync(stamp, "utf8") !== hash) {
  console.log("[signal] installing backend dependencies (first run takes a few minutes)...");
  const code = run(venvPython, ["-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", req], { cwd: BACKEND });
  if (code !== 0) {
    console.error("[signal] pip install failed.");
    process.exit(1);
  }
  writeFileSync(stamp, hash);
}
console.log("[signal] setup complete. Run `npm run dev`.");
