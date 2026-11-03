#!/usr/bin/env node
// 人工审批 E2E 冒烟：TASK_APPROVAL_MODE=all 下 派任务→挂起(approval_request+task_event pending_approval)
// →REST 待审批列表→放行→执行者收到原任务帧→驳回→task_event failed→执行者自批被忽略。
// 用法：node scripts/smoke-approval.mjs（在 botstalk 目录下执行）
import { spawn } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import WebSocket from "ws";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "..");

// 端口与数据目录每次随机，避免并发跑两个冒烟互相污染（固定端口/目录/任务 ID 会导致串扰）。
async function freePort() {
  return new Promise((resolve, reject) => {
    const s = createServer();
    s.once("error", reject);
    s.listen(0, "127.0.0.1", () => {
      const p = s.address().port;
      s.close(() => resolve(String(p)));
    });
  });
}
const PORT = await freePort();
const WS_URL = `ws://127.0.0.1:${PORT}`;
const HTTP_URL = `http://127.0.0.1:${PORT}`;
const DATA_DIR = `/dev/shm/botstalk-smoke-approval-${process.pid}`;

rmSync(DATA_DIR, { recursive: true, force: true });
mkdirSync(DATA_DIR, { recursive: true });

const gw = spawn("node", ["gateway/dist/index.js"], {
  cwd: REPO_ROOT,
  env: { ...process.env, GATEWAY_PORT: PORT, DATA_DIR, TASK_APPROVAL_MODE: "all" },
  stdio: ["ignore", "pipe", "pipe"],
});
gw.stdout.on("data", (d) => process.stdout.write("[gw] " + d));
gw.stderr.on("data", (d) => process.stderr.write("[gw-err] " + d));

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let seq = 1;
const frame = (type, sender, room, payload) => ({
  v: 1, type, seq: seq++, ack: 0, sender, room, ts: Date.now(), payload,
});

async function waitHttpOk(url, timeoutMs = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await fetch(url);
      if (r.ok) return;
    } catch {}
    await sleep(200);
  }
  throw new Error("gateway http not ready: " + url);
}

function connect(nick, room) {
  return new Promise((res, rej) => {
    const ws = new WebSocket(WS_URL);
    const frames = [];
    ws.on("message", (d) => { try { frames.push(JSON.parse(String(d))); } catch {} });
    ws.on("open", () => {
      ws.send(JSON.stringify(frame("hello", nick, room, { adapter_id: nick, protocol_version: "1.3", last_seen_seq: 0 })));
      res({ ws, frames });
    });
    ws.on("error", rej);
  });
}

async function waitFor(frames, pred, what, timeoutMs = 8000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const f = frames.find(pred);
    if (f) return f;
    await sleep(30);
  }
  throw new Error("timeout waiting " + what);
}

const results = [];
const ok = (name, cond) => {
  results.push([name, !!cond]);
  console.log((cond ? "PASS" : "FAIL") + " " + name);
};

try {
  await waitHttpOk(HTTP_URL + "/healthz");
  const boss = await connect("boss", "lobby");
  const worker = await connect("worker", "lobby");
  worker.ws.send(JSON.stringify(frame("capability_update", "worker", "lobby",
    { version: 1, capabilities: { intents: ["chat", "task"] } })));
  await sleep(400);

  // 1. 派任务 → 挂起
  const taskId = "task-smoke-1";
  boss.ws.send(JSON.stringify(frame("message", "boss", "lobby", {
    msg_id: "m-smoke-1", text: "@worker 把周报写一下", mentions: ["worker"], intent: "task", task_id: taskId,
  })));
  const ar = await waitFor(boss.frames, (f) => f.type === "approval_request", "approval_request");
  ok("approval_request broadcast", !!ar.payload.approval_id && ar.payload.task_id === taskId);
  ok("approval_request fields", ar.payload.requester === "boss" && ar.payload.assignee === "worker");
  ok("approval_request ttl", typeof ar.payload.expires_at_ms === "number" && ar.payload.expires_at_ms > Date.now());
  const te1 = await waitFor(boss.frames,
    (f) => f.type === "task_event" && f.payload.task_id === taskId, "task_event pending");
  ok("task_event pending_approval", te1.payload.status === "pending_approval");

  // 2. REST 待审批列表
  const r1 = await fetch(`${HTTP_URL}/api/rooms/lobby/approvals`);
  const j1 = await r1.json();
  ok("REST 200", r1.status === 200);
  ok("REST lists 1 pending", j1.approvals.length === 1 && j1.approvals[0].approval_id === ar.payload.approval_id);
  ok("REST no env leak", !("env" in j1.approvals[0]));

  // 3. 放行前执行者收不到任务
  await sleep(400);
  ok("worker got nothing before approve",
    !worker.frames.some((f) => f.type === "message" && f.payload.task_id === taskId));

  // 4. 放行 → 执行者收到原任务帧
  boss.ws.send(JSON.stringify(frame("approval_decision", "boss", "lobby", {
    approval_id: ar.payload.approval_id, decision: "approve", note: "去吧",
  })));
  const dispatched = await waitFor(worker.frames,
    (f) => f.type === "message" && f.payload.task_id === taskId, "dispatched task frame");
  ok("worker got task after approve", String(dispatched.payload.text).includes("周报"));
  const te2 = await waitFor(boss.frames,
    (f) => f.type === "task_event" && f.payload.task_id === taskId && f.payload.status === "dispatched",
    "task_event dispatched");
  ok("task_event dispatched", !!te2);

  // 5. REST 已清空
  const j2 = await (await fetch(`${HTTP_URL}/api/rooms/lobby/approvals`)).json();
  ok("REST empty after decision", j2.approvals.length === 0);

  // 6. 驳回路径
  const taskId2 = "task-smoke-2";
  boss.ws.send(JSON.stringify(frame("message", "boss", "lobby", {
    msg_id: "m-smoke-2", text: "@worker 把月报也写一下", mentions: ["worker"], intent: "task", task_id: taskId2,
  })));
  const ar2 = await waitFor(boss.frames,
    (f) => f.type === "approval_request" && f.payload.task_id === taskId2, "approval_request 2");
  boss.ws.send(JSON.stringify(frame("approval_decision", "boss", "lobby", {
    approval_id: ar2.payload.approval_id, decision: "reject", note: "不做了",
  })));
  const te3 = await waitFor(boss.frames,
    (f) => f.type === "task_event" && f.payload.task_id === taskId2 && f.payload.status === "failed",
    "task_event failed");
  ok("reject -> task_event failed", te3.payload.status === "failed" && te3.payload.note === "不做了");
  await sleep(400);
  ok("worker got nothing after reject",
    !worker.frames.some((f) => f.type === "message" && f.payload.task_id === taskId2));

  // 7. 防自批：执行者给自己放行被忽略
  const taskId3 = "task-smoke-3";
  boss.ws.send(JSON.stringify(frame("message", "boss", "lobby", {
    msg_id: "m-smoke-3", text: "@worker 写年报", mentions: ["worker"], intent: "task", task_id: taskId3,
  })));
  const ar3 = await waitFor(boss.frames,
    (f) => f.type === "approval_request" && f.payload.task_id === taskId3, "approval_request 3");
  worker.ws.send(JSON.stringify(frame("approval_decision", "worker", "lobby", {
    approval_id: ar3.payload.approval_id, decision: "approve",
  })));
  await sleep(500);
  ok("self-approve ignored (no task frame)",
    worker.frames.every((f) => !(f.type === "message" && f.payload.task_id === taskId3)));
  const j3 = await (await fetch(`${HTTP_URL}/api/rooms/lobby/approvals`)).json();
  ok("REST still lists it", j3.approvals.some((a) => a.approval_id === ar3.payload.approval_id));

  boss.ws.close();
  worker.ws.close();
} catch (e) {
  console.error("SMOKE ERROR:", e.message);
  process.exitCode = 1;
} finally {
  gw.kill("SIGTERM");
  await sleep(500);
  rmSync(DATA_DIR, { recursive: true, force: true });
}

const failed = results.filter(([, c]) => !c);
console.log(failed.length === 0 && !process.exitCode ? "SMOKE PASS" : `SMOKE FAIL (${failed.length})`);
if (failed.length > 0) process.exitCode = 1;
