import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const GATEWAY_PORT = process.env.GATEWAY_PORT || "18501";
const GATEWAY_URL = `http://127.0.0.1:${GATEWAY_PORT}`;
const DATA_DIR = mkdtempSync(join(tmpdir(), "smoke-tasks-limit-"));

let gatewayChild = null;
let ok = 0;

async function waitReady() {
  for (let i = 0; i < 100; i++) {
    try {
      const res = await fetch(GATEWAY_URL + "/healthz");
      if (res.ok) return;
    } catch (_) {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error("gateway did not become ready within 100 polls");
}

async function startGateway() {
  gatewayChild = spawn("node", ["dist/index.js"], {
    cwd: join(__dirname, "..", "gateway"),
    env: { ...process.env, GATEWAY_PORT, DATA_DIR },
    stdio: "inherit",
  });
  await waitReady();
}

async function stopGateway() {
  if (gatewayChild) {
    const child = gatewayChild;
    gatewayChild = null;
    child.kill();
    await new Promise((r) => setTimeout(r, 100));
  }
}

function checkPassed(label) {
  ok += 1;
  console.log(`[OK] ${ok} - ${label} check passed`);
}

async function run() {
  // Stage 1: start the gateway so it creates its tables, then stop it.
  await startGateway();
  await stopGateway();

  // Stage 2: seed 7 tasks directly into SQLite while the gateway is stopped.
  const db = new DatabaseSync(join(DATA_DIR, "botstalk.db"));
  const insert = db.prepare(
    "INSERT INTO tasks (task_id, room, owner, assignee, title, status, created_at_ms, updated_at_ms, deadline_ms, error, progress_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
  );
  for (let n = 1; n <= 7; n++) {
    insert.run(`t${n}`, "lobby", "alice", "echo", `task ${n}`, "dispatched", 1000 + n, 1000 + n, null, null, 0);
  }
  db.close();

  // Stage 3: restart the gateway with the same port and data dir.
  await startGateway();

  async function check(label, qs, expectedStatus, expectedLength, expectedError) {
    const res = await fetch(GATEWAY_URL + "/api/tasks" + qs);
    const body = await res.json().catch(() => null);
    if (res.status !== expectedStatus) {
      throw new Error(`${label}: expected status ${expectedStatus}, got ${res.status}`);
    }
    if (expectedError !== undefined) {
      if (!body || body.error !== expectedError) {
        throw new Error(`${label}: expected body.error ${expectedError}, got ${body && body.error}`);
      }
    } else if (body && Array.isArray(body.tasks)) {
      if (body.tasks.length !== expectedLength) {
        throw new Error(`${label}: expected tasks length ${expectedLength}, got ${body.tasks.length}`);
      }
    } else {
      throw new Error(`${label}: expected tasks array of length ${expectedLength}, got ${JSON.stringify(body)}`);
    }
    checkPassed(label);
  }

  await check("limit=5", "?limit=5", 200, 5, undefined);
  await check("limit=1", "?limit=1", 200, 1, undefined);
  await check("limit=1000", "?limit=1000", 200, 7, undefined);
  await check("no query string", "", 200, 7, undefined);
  await check("limit=abc", "?limit=abc", 400, undefined, "INVALID_TASKS_LIMIT");
  await check("limit=0", "?limit=0", 400, undefined, "INVALID_TASKS_LIMIT");
  await check("limit=1.5", "?limit=1.5", 400, undefined, "INVALID_TASKS_LIMIT");
  await check("limit= (empty)", "?limit=", 400, undefined, "INVALID_TASKS_LIMIT");

  console.log("SMOKE_TASKS_LIMIT_PASS");
}

try {
  await run();
} finally {
  await stopGateway();
  rmSync(DATA_DIR, { recursive: true, force: true });
}
