// `npm run dev`: API (FastAPI, auto-seeds on first boot) + web (Next.js) with prefixed logs.
import { existsSync } from "node:fs";
import { join } from "node:path";
import { BACKEND, FRONTEND, ROOT, choosePort, ensureVenv, killTree, run, spawnLabelled, venvPython } from "./lib.mjs";

if (!existsSync(venvPython) || !existsSync(join(FRONTEND, "node_modules"))) {
  console.log("[signal] first run: completing setup...");
  if (run(process.execPath, [join(ROOT, "scripts", "setup.mjs")]) !== 0) process.exit(1);
}
if (!ensureVenv()) process.exit(1);

const apiPort = await choosePort(process.env.API_PORT ?? "5000", "api");
const webPort = await choosePort(process.env.PORT ?? "3000", "web");
const env = { ...process.env, BACKEND_URL: `http://127.0.0.1:${apiPort}` };

const api = spawnLabelled("api", venvPython, ["-m", "uvicorn", "app.main:app", "--reload", "--port", apiPort, "--reload-dir", "app"], { cwd: BACKEND, env });
const web = spawnLabelled("web", process.execPath, [join(FRONTEND, "node_modules", "next", "dist", "bin", "next"), "dev", "-p", webPort], { cwd: FRONTEND, env });

console.log(`\n  SIGNAL  →  http://localhost:${webPort}   (API docs: http://127.0.0.1:${apiPort}/docs)`);
console.log("  First boot seeds the demo workspace (~10-20s); the UI waits for it automatically.\n");

let stopping = false;
const stop = (code = 0) => {
  if (stopping) return;
  stopping = true;
  killTree(api);
  killTree(web);
  process.exit(code);
};
process.on("SIGINT", () => stop(0));
process.on("SIGTERM", () => stop(0));
api.on("exit", (c) => !stopping && (console.log(`[signal] api exited (${c})`), stop(c ?? 1)));
web.on("exit", (c) => !stopping && (console.log(`[signal] web exited (${c})`), stop(c ?? 1)));
