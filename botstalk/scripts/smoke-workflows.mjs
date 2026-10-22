#!/usr/bin/env node
import { spawn } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { DatabaseSync } from "node:sqlite";
import WebSocket from "ws";
const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "..");
async function freePort() {
  return new Promise((resolveFn, reject) => {
    const s = createServer();
    s.once("error", reject);
    s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => resolveFn(String(p))); });
  });
}
const PORT = await freePort();
const WS_URL = `ws://127.0.0.1:${PORT}`;
const HTTP_URL = `http://127.0.0.1:${PORT}`;
const DATA_DIR = `/dev/shm/botstalk-smoke-workflows-${process.pid}`;
rmSync(DATA_DIR, { recursive: true, force: true });
mkdirSync(DATA_DIR, { recursive: true });
const gw = spawn("node", ["gateway/dist/index.js"], {
  cwd: REPO_ROOT,
  env: { ...process.env, GATEWAY_PORT: PORT, DATA_DIR },
  stdio: ["ignore", "pipe", "pipe"],
});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let seq = 1;
const frame = (type, sender, room, payload) => ({ v: 1, type, seq: seq++, ack: 0, sender, room, ts: Date.now(), payload });
async function waitHttpOk(url, timeoutMs = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try { const r = await fetch(url); if (r.ok) return; } catch {}
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
async function waitFor(frames, pred, what, timeoutMs = 25000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const f = frames.find(pred);
    if (f) return f;
    await sleep(200);
  }
  throw new Error("timeout waiting " + what);
}
async function postJson(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`POST ${url} failed: ${r.status}`);
  return await r.json();
}
async function getJson(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`GET ${url} failed: ${r.status}`);
  return await r.json();
}
let worker = null;
let user = null;
(async () => {
  await waitHttpOk(`${HTTP_URL}/healthz`);

  await postJson(`${HTTP_URL}/api/rooms`, { id: "wftest", name: "wf", type: "workroom" });

  const sched = await postJson(`${HTTP_URL}/api/rooms/wftest/schedules`, {
    name: "smoke 定时",
    interval_sec: 3600,
    prompt: "冒烟定时任务",
    owner: "smoke",
    agent_id: "worker1",
  });
  const schedId = sched.schedule.id;
  if (!schedId) throw new Error("schedule id missing");

  const db = new DatabaseSync(`${DATA_DIR}/botstalk.db`);
  db.prepare("UPDATE scheduled_tasks SET next_run_ms=? WHERE id=?").run(Date.now() - 5000, schedId);
  db.close();

  worker = await connect("worker1", "wftest");
  worker.ws.send(JSON.stringify(frame("capability_update", "worker1", "wftest", { version: 1, capabilities: { intents: ["chat", "task"] } })));
  await sleep(500);

  await waitFor(worker.frames, f => f.type === "message" && f.payload && f.payload.intent === "task" && f.sender === "scheduler", "scheduler task frame", 30000);
  console.log("PASS 定时任务到期派发");

  const tasksData = await getJson(`${HTTP_URL}/api/tasks?room=wftest`);
  const tasks = Array.isArray(tasksData) ? tasksData : (tasksData.tasks || tasksData.items || []);
  const ledger = tasks.find(t => t.owner === "scheduler" && t.status === "dispatched");
  if (!ledger) throw new Error("scheduler dispatched task missing in ledger");
  console.log("PASS 任务台账");

  await postJson(`${HTTP_URL}/api/rooms/wftest/triggers`, {
    name: "smoke 关键词",
    match_type: "keyword",
    pattern: "开火",
    prompt: "{sender} 说了 {text}",
    owner: "smoke",
    agent_id: "worker1",
    cooldown_sec: 3600,
  });

  user = await connect("user1", "wftest");
  user.ws.send(JSON.stringify(frame("message", "user1", "wftest", { msg_id: "m-smoke-1", text: "全体注意，开火！", mentions: [], intent: "chat" })));

  const trigFrame = await waitFor(worker.frames, f => f.type === "message" && f.payload && f.payload.intent === "task" && typeof f.sender === "string" && f.sender.startsWith("trigger:"), "trigger task frame", 10000);
  if (trigFrame.payload.text !== "user1 说了 全体注意，开火！") {
    throw new Error("trigger template mismatch: " + JSON.stringify(trigFrame.payload));
  }
  console.log("PASS 关键词触发+模板渲染");

  user.ws.send(JSON.stringify(frame("message", "user1", "wftest", { msg_id: "m-smoke-2", text: "再次开火", mentions: [], intent: "chat" })));
  await sleep(2000);
  const triggerFrames = worker.frames.filter(f => f.type === "message" && f.payload && f.payload.intent === "task" && typeof f.sender === "string" && f.sender.startsWith("trigger:"));
  if (triggerFrames.length !== 1) throw new Error(`cooldown failed, trigger frames=${triggerFrames.length}`);
  console.log("PASS 冷却防重");

  console.log("SMOKE OK");
})().catch((err) => {
  console.error("FATAL", err && err.stack ? err.stack : err);
  process.exitCode = 1;
}).finally(() => {
  try { if (worker && worker.ws) worker.ws.close(); } catch {}
  try { if (user && user.ws) user.ws.close(); } catch {}
  try { if (gw.stdout) gw.stdout.destroy(); } catch {}
  try { if (gw.stderr) gw.stderr.destroy(); } catch {}
  try { gw.kill("SIGTERM"); } catch {}
  if (process.exitCode) process.exit(process.exitCode);
});