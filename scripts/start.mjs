// Production-style run: uvicorn (no reload) + `next start`. Requires `npm run build` first.
import { join } from "node:path";
import { BACKEND, FRONTEND, choosePort, killTree, spawnLabelled, venvPython } from "./lib.mjs";

const apiPort = await choosePort(process.env.API_PORT ?? "5000", "api");
const webPort = await choosePort(process.env.PORT ?? "3000", "web");
const env = { ...process.env, BACKEND_URL: `http://127.0.0.1:${apiPort}` };
const api = spawnLabelled("api", venvPython, ["-m", "uvicorn", "app.main:app", "--port", apiPort], { cwd: BACKEND, env });
const web = spawnLabelled("web", process.execPath, [join(FRONTEND, "node_modules", "next", "dist", "bin", "next"), "start", "-p", webPort], { cwd: FRONTEND, env });
const stop = () => { killTree(api); killTree(web); process.exit(0); };
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
api.on("exit", stop);
web.on("exit", stop);
