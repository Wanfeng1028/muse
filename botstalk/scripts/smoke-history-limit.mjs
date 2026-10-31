import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const GATEWAY_PORT = process.env.GATEWAY_PORT || "18498";
const GATEWAY_URL = `http://127.0.0.1:${GATEWAY_PORT}`;
const DATA_DIR = mkdtempSync(join(tmpdir(), "smoke-history-limit-"));

const gateway = spawn("node", ["dist/index.js"], {
  cwd: join(__dirname, "..", "gateway"),
  env: { ...process.env, GATEWAY_PORT, DATA_DIR },
  stdio: "inherit"
});

async function waitReady() {
  for (let i = 0; i < 100; i++) {
    try {
      const res = await fetch(GATEWAY_URL + "/healthz");
      if (res.ok) return;
    } catch (_) {}
    await new Promise(r => setTimeout(r, 100));
  }
  throw new Error("gateway not ready");
}

async function run() {
  await waitReady();
  let ok = 0;

  const createRoom = await fetch(GATEWAY_URL + "/api/rooms", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: "room1", name: "Room 1", owner: "alice" })
  });
  if (createRoom.status !== 200 && createRoom.status !== 201) throw new Error("room creation failed");
  ok++;
  console.log(`[OK] ${ok} - room created`);

  const db = new DatabaseSync(join(DATA_DIR, "botstalk.db"));
  for (let i = 1; i <= 7; i++) {
    db.prepare("INSERT INTO messages (room, sender, seq, type, payload, ts) VALUES (?, ?, ?, ?, ?, ?)")
      .run("room1", "alice", i, "message", JSON.stringify({ n: i }), 1000 + i);
  }
  db.close();
  ok++;
  console.log(`[OK] ${ok} - messages seeded`);

  const checks = [
    { qs: "?limit=5", status: 200, len: 5 },
    { qs: "?limit=abc", status: 400, error: "INVALID_HISTORY_LIMIT" },
    { qs: "?limit=0", status: 400, error: "INVALID_HISTORY_LIMIT" },
    { qs: "?limit=1000", status: 200, len: 7 },
    { qs: "", status: 200, len: 7 },
    { qs: "?limit=1", status: 200, len: 1 }
  ];

  for (const c of checks) {
    const res = await fetch(GATEWAY_URL + "/api/rooms/room1/history" + c.qs);
    const body = await res.json();
    if (res.status !== c.status) throw new Error(`expected status ${c.status}, got ${res.status}`);
    if (c.len !== undefined && body.messages.length !== c.len) throw new Error(`expected len ${c.len}, got ${body.messages.length}`);
    if (c.error !== undefined && body.error !== c.error) throw new Error(`expected error ${c.error}, got ${body.error}`);
    ok++;
    console.log(`[OK] ${ok} - ${c.qs || "default"} check passed`);
  }

  console.log("SMOKE_HISTORY_LIMIT_PASS");
}

try {
  await run();
} finally {
  gateway.kill();
  rmSync(DATA_DIR, { recursive: true, force: true });
}
