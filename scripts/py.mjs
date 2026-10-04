// Run a command with the backend virtualenv's Python, from backend/: `node scripts/py.mjs -m pytest -q`
import { BACKEND, run, venvPython } from "./lib.mjs";

process.exit(run(venvPython, process.argv.slice(2), { cwd: BACKEND }));
