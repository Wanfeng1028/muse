#!/usr/bin/env node
//
// Usage: node scripts/smoke-capability-matching.mjs
//   (run from the botstalk directory)
//

import { spawn } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import WebSocket from "ws";
import assert from "node:assert/strict";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// --- freePort ---
function freePort() {
  return new Promise((res, rej) => {
    const srv = createServer();
    srv.listen(0, "127.0.0.1", () => {
      const port = srv.address().port;
      srv.close(() => res(port));
    });
    srv.on("error", rej);
  });
}

// --- DATA_DIR ---
const DATA_DIR = `/dev/shm/botstalk-smoke-capability-${process.pid}`;
try { rmSync(DATA_DIR, { recursive: true }); } catch {}
mkdirSync(DATA_DIR, { recursive: true });

// --- helpers ---
const sleep = ms => new Promise(r => setTimeout(r, ms));

let _seq = 0;
function frame(type, sender, room, payload) {
  return { v: 1, type, seq: ++_seq, ack: 0, sender, room, ts: Date.now(), payload };
}

async function waitHttpOk(url, timeoutMs = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await fetch(url);
      if (r.ok) return;
    } catch {}
    await sleep(200);
  }
  throw new Error(`HTTP not ready at ${url} within ${timeoutMs}ms`);
}

let port;
let gw;

function connect(nick, room) {
  return new Promise((res, rej) => {
    const frames = [];
    const ws = new WebSocket(`ws://127.0.0.1:${port}/ws`);
    ws.on("message", raw => {
      try { frames.push(JSON.parse(raw.toString())); } catch {}
    });
    ws.on("open", () => {
      ws.send(JSON.stringify(frame("hello", nick, room, {
        adapter_id: nick,
        protocol_version: "1.3",
        last_seen_seq: -1
      })));
      res({ nick, ws, frames });
    });
    ws.on("error", rej);
  });
}

async function waitFor(frames, pred, what, timeoutMs = 8000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const found = frames.find(pred);
    if (found) return found;
    await sleep(100);
  }
  throw new Error(`Timeout waiting for: ${what}`);
}

// --- cleanup ---
function cleanup() {
  try { gw?.kill(); } catch {}
  try { rmSync(DATA_DIR, { recursive: true }); } catch {}
}

// --- main ---
async function main() {
  port = await freePort();

  gw = spawn("node", ["gateway/dist/index.js"], {
    cwd: resolve(__dirname, ".."),
    env: { ...process.env, GATEWAY_PORT: String(port), DATA_DIR },
    stdio: ["pipe", "pipe", "pipe"]
  });
  gw.stdout.on("data", d => process.stdout.write(`[gw] ${d}`));
  gw.stderr.on("data", d => process.stderr.write(`[gw-err] ${d}`));

  await waitHttpOk(`http://127.0.0.1:${port}/healthz`);

  // Step 1: connect three clients to "lobby"
  const boss     = await connect("boss",     "lobby");
  const reviewer = await connect("reviewer", "lobby");
  const general  = await connect("general",  "lobby");

  // Step 2: capability declarations
  reviewer.ws.send(JSON.stringify(frame("capability_update", "reviewer", "lobby", {
    version: 1,
    capabilities: {
      intents: ["chat", "task"],
      skills: ["code-review"],
      tags: []
    }
  })));
  await sleep(300);

  general.ws.send(JSON.stringify(frame("capability_update", "general", "lobby", {
    version: 1,
    capabilities: {
      intents: ["chat", "task"]
    }
  })));
  await sleep(300);

  // Step 3: task requiring code-review skill
  boss.ws.send(JSON.stringify(frame("message", "boss", "lobby", {
    msg_id: "smoke-cap-1",
    text: "review this",
    mentions: [],
    intent: "task",
    task_id: "smoke-cap-1",
    required_capabilities: { skills: ["code-review"] }
  })));

  await waitFor(reviewer.frames,
    f => f.type === "message" && f.payload?.task_id === "smoke-cap-1",
    "reviewer receives task smoke-cap-1");

  assert(
    !general.frames.find(f => f.type === "message" && f.payload?.task_id === "smoke-cap-1"),
    "general should NOT receive task smoke-cap-1"
  );

  const dispatched = await waitFor(boss.frames,
    f => f.type === "task_event" && f.payload?.status === "dispatched" && f.payload?.assignee === "reviewer",
    "boss receives task_event dispatched for reviewer");
  assert.equal(dispatched.payload.status, "dispatched");
  assert.equal(dispatched.payload.assignee, "reviewer");

  // Step 4: task requiring non-existent skill → unsupported
  boss.ws.send(JSON.stringify(frame("message", "boss", "lobby", {
    msg_id: "smoke-cap-2",
    text: "impossible task",
    mentions: [],
    intent: "task",
    task_id: "smoke-cap-2",
    required_capabilities: { skills: ["no-such-skill"] }
  })));

  await waitFor(boss.frames,
    f => f.type === "task_event" && f.payload?.status === "unsupported",
    "boss receives task_event unsupported for smoke-cap-2");

  assert(
    !reviewer.frames.find(f => f.type === "message" && f.payload?.task_id === "smoke-cap-2"),
    "reviewer should NOT receive task smoke-cap-2"
  );
  assert(
    !general.frames.find(f => f.type === "message" && f.payload?.task_id === "smoke-cap-2"),
    "general should NOT receive task smoke-cap-2"
  );

  // Step 5: @-mention overrides scoring
  boss.ws.send(JSON.stringify(frame("message", "boss", "lobby", {
    msg_id: "smoke-cap-3",
    text: "@general do this",
    mentions: ["general"],
    intent: "task",
    task_id: "smoke-cap-3",
    required_capabilities: { skills: ["code-review"] }
  })));

  await waitFor(general.frames,
    f => f.type === "message" && f.payload?.task_id === "smoke-cap-3",
    "general receives task smoke-cap-3 via @mention override");

  // All pass
  console.log("SMOKE CAPABILITY MATCHING: ALL PASS");
  cleanup();
  process.exit(0);
}

main().catch(err => {
  console.error(err);
  cleanup();
  process.exit(1);
});
