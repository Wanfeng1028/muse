/**
 * 烟雾测试：验证 thread_context 功能
 *
 * 当 adapter client 启用 threadContext.enabled=true 时，
 * 收到的消息 payload.thread_context 应包含房间历史消息，
 * 且顺序为先旧后新，同时不包含触发消息本身。
 *
 * 用法：node scripts/smoke-thread-context.mjs（在 botstalk 目录下运行）
 */

import { spawn } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { WebSocket } from "ws";
import { AdapterClient } from "../adapters/base/dist/index.js";
import assert from "node:assert/strict";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// --- helpers ---

function freePort() {
  return new Promise((res, rej) => {
    const srv = createServer();
    srv.on("error", rej);
    srv.listen(0, () => {
      const addr = srv.address();
      srv.close(() => res(String(addr.port)));
    });
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let seq = 1;
function frame(type, sender, room, payload) {
  return {
    v: 1,
    type,
    seq: seq++,
    ack: 0,
    sender,
    room,
    ts: Date.now(),
    payload,
  };
}

async function waitHttpOk(url, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (true) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {}
    if (Date.now() > deadline) throw new Error("waitHttpOk timeout: " + url);
    await sleep(200);
  }
}

async function waitFor(predicate, label, timeoutMs = 10000) {
  const deadline = Date.now() + timeoutMs;
  while (true) {
    if (predicate()) return;
    if (Date.now() > deadline) throw new Error("timeout: " + label);
    await sleep(100);
  }
}

function connect(nick, room) {
  const wsUrl = `ws://127.0.0.1:${PORT}`;
  return new Promise((resolveWs, rej) => {
    const ws = new WebSocket(wsUrl);
    ws.on("error", rej);
    ws.on("open", () => {
      ws.send(
        JSON.stringify({
          v: 1,
          type: "hello",
          seq: seq++,
          ack: 0,
          sender: nick,
          room,
          ts: Date.now(),
          payload: {
            adapter_id: nick,
            protocol_version: "1.3",
            last_seen_seq: -1,
          },
        })
      );
      resolveWs(ws);
    });
  });
}

// --- main ---

const PORT = await freePort();
const WS_URL = `ws://127.0.0.1:${PORT}`;
const HTTP_URL = `http://127.0.0.1:${PORT}`;
const DATA_DIR = `/dev/shm/botstalk-smoke-threadctx-${process.pid}`;

rmSync(DATA_DIR, { recursive: true, force: true });
mkdirSync(DATA_DIR, { recursive: true });

const REPO_ROOT = resolve(__dirname, "..");

const gw = spawn("node", ["gateway/dist/index.js"], {
  cwd: REPO_ROOT,
  env: { ...process.env, GATEWAY_PORT: PORT, DATA_DIR },
  stdio: ["ignore", "pipe", "pipe"],
});
gw.stdout.on("data", (d) => process.stdout.write("[gw] " + d));
gw.stderr.on("data", (d) => process.stderr.write("[gw-err] " + d));

const received = [];
let boss = null;
let worker = null;

try {
  // 1. Wait for gateway HTTP ready
  await waitHttpOk(HTTP_URL + "/healthz");
  console.log("PASS 1: gateway HTTP ready");

  // 2. Connect boss, send two history messages, wait for persistence
  boss = await connect("boss", "lobby");

  boss.send(
    JSON.stringify(
      frame("message", "boss", "lobby", {
        msg_id: "hist-1",
        text: "first decision: use postgres",
        mentions: [],
      })
    )
  );

  boss.send(
    JSON.stringify(
      frame("message", "boss", "lobby", {
        msg_id: "hist-2",
        text: "second decision: deploy friday",
        mentions: [],
      })
    )
  );

  {
    const deadline = Date.now() + 10000;
    let persisted = false;
    while (!persisted) {
      try {
        const res = await fetch(HTTP_URL + "/api/rooms/lobby/history?limit=100");
        if (res.ok) {
          const json = await res.json();
          persisted = Array.isArray(json.messages) && json.messages.length >= 2;
        }
      } catch {}
      if (!persisted) {
        if (Date.now() > deadline) throw new Error("timeout: boss messages persisted");
        await sleep(100);
      }
    }
  }
  console.log("PASS 2: boss history messages persisted");

  // 3. Connect worker via AdapterClient with threadContext enabled
  worker = new AdapterClient({
    adapterId: "worker",
    gatewayUrl: WS_URL,
    room: "lobby",
    heartbeatMs: 60000,
    stateDir: DATA_DIR + "/worker-state",
    intents: ["chat"],
    threadContext: { enabled: true },
    onMessage: (env) => {
      received.push(env);
    },
  });
  await worker.connect();

  // Brief wait for the worker's hello to be processed by the gateway
  await sleep(500);

  // Boss sends trigger mentioning worker
  boss.send(
    JSON.stringify(
      frame("message", "boss", "lobby", {
        msg_id: "trig-1",
        text: "@worker proceed",
        mentions: ["worker"],
      })
    )
  );

  await waitFor(
    () => received.length > 0,
    "worker receives trigger"
  );
  console.log("PASS 3: worker received trigger message");

  // 4. Validate thread_context on the received message
  const env = received[0];
  assert.equal(env.payload.text, "@worker proceed", "trigger text untouched");
  console.log("PASS 4a: trigger text untouched");

  assert.equal(
    typeof env.payload.thread_context,
    "string",
    "thread_context is a string"
  );

  const ctx = env.payload.thread_context;
  const idxFirst = ctx.indexOf("first decision: use postgres");
  const idxSecond = ctx.indexOf("second decision: deploy friday");
  assert.ok(idxFirst !== -1, "thread_context contains first history message");
  assert.ok(idxSecond !== -1, "thread_context contains second history message");
  assert.ok(
    idxFirst < idxSecond,
    "first history message appears before second in thread_context"
  );
  console.log("PASS 4b: thread_context has history in correct order");

  // The trigger itself must NOT appear in its own context block
  const triggerCount = ctx.split("@worker proceed").length - 1;
  assert.equal(triggerCount, 0, "trigger text must not appear in thread_context");
  console.log("PASS 4c: trigger text excluded from own thread_context");

  // 5. All pass
  console.log("SMOKE-THREAD-CONTEXT ALL PASS");
  process.exitCode = 0;
} catch (err) {
  console.error("SMOKE FAIL:", err);
  process.exitCode = 1;
} finally {
  try {
    boss?.close();
  } catch {}
  try {
    worker?.disconnect();
  } catch {}
  gw.kill();
}