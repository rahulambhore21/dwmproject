// Production-style run: uvicorn (no reload) + `next start`. Requires `npm run build` first.
import { join } from "node:path";
import { BACKEND, FRONTEND, killTree, spawnLabelled, venvPython } from "./lib.mjs";

const apiPort = process.env.API_PORT ?? "8000";
const webPort = process.env.PORT ?? "3000";
const env = { ...process.env, BACKEND_URL: `http://127.0.0.1:${apiPort}` };
const api = spawnLabelled("api", venvPython, ["-m", "uvicorn", "app.main:app", "--port", apiPort], { cwd: BACKEND, env });
const web = spawnLabelled("web", process.execPath, [join(FRONTEND, "node_modules", "next", "dist", "bin", "next"), "start", "-p", webPort], { cwd: FRONTEND, env });
const stop = () => { killTree(api); killTree(web); process.exit(0); };
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
api.on("exit", stop);
web.on("exit", stop);
