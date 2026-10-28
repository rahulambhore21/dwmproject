import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { createServer } from "node:net";
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

// ----- ports: a leftover SIGNAL server (e.g. the terminal was closed instead of Ctrl+C) must not block the next run

export function portFree(port) {
  return new Promise((done) => {
    const srv = createServer();
    srv.once("error", () => done(false));
    srv.once("listening", () => srv.close(() => done(true)));
    srv.listen(Number(port)); // no host: binds dual-stack, the same way Next.js and uvicorn collide
  });
}

function listenerPid(port) {
  if (isWin) {
    const r = spawnSync("netstat", ["-ano"], { encoding: "utf8" });
    for (const line of (r.stdout ?? "").split(/\r?\n/)) {
      const cols = line.trim().split(/\s+/);
      if (cols[0] === "TCP" && cols[3] === "LISTENING" && cols[1].endsWith(`:${port}`)) return Number(cols[4]);
    }
    return null;
  }
  const r = spawnSync("lsof", ["-nP", `-iTCP:${port}`, "-sTCP:LISTEN", "-t"], { encoding: "utf8" });
  const pid = Number((r.stdout ?? "").split(/\s+/)[0]);
  return pid > 0 ? pid : null;
}

// The listening process and up to three ancestors: [{ pid, cmd }], listener first.
function processChain(pid) {
  if (isWin) {
    const ps = `$p=${pid};$o=@();for($i=0;$i -lt 4 -and $p;$i++){$x=Get-CimInstance Win32_Process -Filter "ProcessId=$p";`
      + `if(-not $x){break};$o+=[pscustomobject]@{pid=[int]$x.ProcessId;cmd=[string]$x.CommandLine};$p=$x.ParentProcessId};`
      + `ConvertTo-Json -InputObject $o -Compress`;
    const r = spawnSync("powershell", ["-NoProfile", "-NonInteractive", "-Command", ps], { encoding: "utf8" });
    try { return [].concat(JSON.parse(r.stdout || "[]")); } catch { return []; }
  }
  const chain = [];
  for (let p = pid; p > 1 && chain.length < 4;) {
    const r = spawnSync("ps", ["-o", "ppid=,command=", "-p", String(p)], { encoding: "utf8" });
    const m = (r.stdout ?? "").trim().match(/^(\d+)\s+(.*)$/);
    if (!m) break;
    chain.push({ pid: p, cmd: m[2] });
    p = Number(m[1]);
  }
  return chain;
}

const norm = (s) => String(s ?? "").replaceAll("\\", "/").toLowerCase();

// Stop a stale process from this repository that holds `port`. Returns true if it did.
function reclaim(port, label) {
  const pid = listenerPid(port);
  if (!pid) return false;
  const chain = processChain(pid);
  const ours = (c) => norm(c.cmd).includes(norm(ROOT));
  // the listener may be a worker whose command line omits the path (uvicorn --reload), so match its ancestors too
  let top = chain.findIndex(ours);
  if (top < 0) return false;
  while (top + 1 < chain.length && ours(chain[top + 1])) top++;
  const target = chain[top].pid;
  if (isWin) spawnSync("taskkill", ["/pid", String(target), "/T", "/F"], { stdio: "ignore" });
  else spawnSync("kill", ["-TERM", String(target)], { stdio: "ignore" });
  console.log(`[signal] port ${port} was held by a leftover SIGNAL ${label} (pid ${target}); stopped it.`);
  return true;
}

// Prefer `preferred`; reclaim it from our own leftovers; otherwise move to the next free port.
export async function choosePort(preferred, label) {
  const want = Number(preferred);
  if (await portFree(want)) return String(want);
  if (reclaim(want, label)) {
    for (let i = 0; i < 25; i++) {
      if (await portFree(want)) return String(want);
      await new Promise((r) => setTimeout(r, 200));
    }
  }
  for (let p = want + 1; p < want + 20; p++) {
    if (await portFree(p)) {
      console.log(`[signal] port ${want} is used by another program; using ${p} for the ${label} instead.`);
      return String(p);
    }
  }
  console.error(`[signal] no free port found near ${want} for the ${label}. Set ${label === "web" ? "PORT" : "API_PORT"} to a free port.`);
  process.exit(1);
}
