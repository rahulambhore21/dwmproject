// `npm run verify`: the full pre-release gate (lint, types, unit + API tests, build, seed, e2e smoke).
import { rmSync } from "node:fs";
import { join } from "node:path";
import { BACKEND, FRONTEND, ROOT, run, venvPython } from "./lib.mjs";

const steps = [
  ["backend lint (ruff)", venvPython, ["-m", "ruff", "check", "app", "tests"], BACKEND],
  ["backend types (mypy)", venvPython, ["-m", "mypy", "-p", "app", "--explicit-package-bases"], BACKEND],
  ["backend tests (pytest)", venvPython, ["-m", "pytest", "-q"], BACKEND],
  ["frontend lint (eslint)", "npm", ["run", "lint"], FRONTEND],
  ["frontend types (tsc)", "npm", ["run", "typecheck"], FRONTEND],
  ["frontend tests (vitest)", "npm", ["test"], FRONTEND],
  ["production build (next)", "npm", ["run", "build"], FRONTEND],
  ["seed from scratch", venvPython, ["-m", "app.seed.cli", "--reset"], BACKEND, { DATABASE_URL: `sqlite:///${join(BACKEND, "data", "verify.db").replace(/\\/g, "/")}`, ARTIFACTS_DIR: join(BACKEND, "data", "verify-artifacts") }],
  ["end-to-end smoke (playwright)", "npm", ["run", "test:e2e"], FRONTEND],
];

let failed = null;
for (const [name, cmd, args, cwd, env] of steps) {
  console.log(`\n━━ ${name}`);
  if (run(cmd, args, { cwd, env: { ...process.env, ...(env ?? {}) } }) !== 0) { failed = name; break; }
}
for (const f of ["verify.db", "e2e.db"]) rmSync(join(BACKEND, "data", f), { force: true });
if (failed) { console.error(`\n✘ verify failed at: ${failed}`); process.exit(1); }
console.log(`\n✔ all ${steps.length} checks passed (${ROOT})`);
