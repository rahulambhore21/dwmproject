import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
export const BACKEND = join(ROOT, "backend");
export const FRONTEND = join(ROOT, "frontend");
export const isWin = process.platform === "win32";
export const venvPython = isWin
  ? join(BACKEND, ".venv", "Scripts", "python.exe")
  : join(BACKEND, ".venv", "bin", "python");

export function findSystemPython() {
  const candidates = isWin ? ["py -3", "python", "python3"] : ["python3", "python"];
  for (const c of candidates) {
    const [cmd, ...args] = c.split(" ");
    const r = spawnSync(cmd, [...args, "-c", "import sys; print(sys.version_info[:2] >= (3, 10))"], { encoding: "utf8" });
    if (r.status === 0 && r.stdout.trim() === "True") return { cmd, args };
  }
  return null;
}

export function run(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { stdio: "inherit", shell: isWin && !cmd.endsWith(".exe"), ...opts });
  return r.status ?? 1;
}

export function ensureVenv() {
  if (existsSync(venvPython)) return true;
  const py = findSystemPython();
  if (!py) {
    console.error("[signal] Python 3.10+ is required for the backend. Install it from https://www.python.org/ and re-run `npm install`.");
    return false;
  }
  console.log("[signal] creating backend virtualenv...");
  return run(py.cmd, [...py.args, "-m", "venv", join(BACKEND, ".venv")]) === 0;
}

export function spawnLabelled(label, cmd, args, opts = {}) {
  const child = spawn(cmd, args, { shell: isWin && !cmd.endsWith(".exe"), ...opts, stdio: ["ignore", "pipe", "pipe"] });
  const tag = `[${label}]`;
  const pipe = (stream, out) => {
    let buf = "";
    stream.on("data", (d) => {
      buf += d.toString();
      const lines = buf.split(/\r?\n/);
      buf = lines.pop() ?? "";
      for (const l of lines) if (l.trim()) out.write(`${tag} ${l}\n`);
    });
  };
  pipe(child.stdout, process.stdout);
  pipe(child.stderr, process.stdout);
  return child;
}

export function killTree(child) {
  if (!child || child.killed || child.exitCode !== null) return;
  if (isWin) spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  else child.kill("SIGTERM");
}
