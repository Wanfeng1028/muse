import { execSync } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export const VENV_DIR = join(homedir(), ".openclaw", "hy-memory-venv");

const IS_WIN = process.platform === "win32";

/** Default python command name for this OS (config placeholder / fallback). */
export function defaultPythonCommand(): string {
  return IS_WIN ? "python" : "python3";
}

/** True when user did not set an explicit interpreter (use auto venv). */
export function isAutoPythonPath(path: string | undefined): boolean {
  if (!path || !path.trim()) return true;
  const t = path.trim();
  return t === "python3" || t === "python";
}

/** Path to Python inside the managed venv. */
export function getVenvPythonPath(): string {
  return IS_WIN
    ? join(VENV_DIR, "Scripts", "python.exe")
    : join(VENV_DIR, "bin", "python");
}

/** Whether the venv layout exists (bin/ or Scripts/). */
export function venvLayoutExists(): boolean {
  return IS_WIN
    ? existsSync(join(VENV_DIR, "Scripts", "python.exe"))
    : existsSync(join(VENV_DIR, "bin", "python"));
}

/** Candidates to create a venv when none exists yet. */
export function systemPythonCandidates(): string[] {
  if (IS_WIN) {
    return ["python", "python3"];
  }
  if (process.platform === "darwin") {
    return ["python3", "/usr/bin/python3", "/usr/local/bin/python3", "python"];
  }
  return ["python3", "/usr/bin/python3", "/usr/local/bin/python3", "python"];
}

function probePython(cmd: string): boolean {
  try {
    const opts = { stdio: "ignore" as const, timeout: 5_000 };
    if (cmd.includes(" ")) {
      execSync(`${cmd} --version`, { ...opts, shell: true });
    } else {
      execSync(`${cmd} --version`, opts);
    }
    return true;
  } catch {
    return false;
  }
}

/** First working system Python for `python -m venv`. */
export function findSystemPython(): string {
  for (const candidate of systemPythonCandidates()) {
    if (probePython(candidate)) return candidate;
  }
  // Windows: py launcher
  if (IS_WIN && probePython("py -3")) return "py -3";
  return defaultPythonCommand();
}

/** Run `python -m …` (handles `py -3` on Windows). */
export function execPythonModule(python: string, moduleArgs: string, timeoutMs: number): void {
  const cmd = `${python} -m ${moduleArgs}`;
  const opts = { stdio: "pipe" as const, timeout: timeoutMs };
  if (python.includes(" ")) {
    execSync(cmd, { ...opts, shell: true });
  } else {
    execSync(cmd, opts);
  }
}
