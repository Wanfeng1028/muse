#!/usr/bin/env node
// 狼人杀 E2E 冒烟：建 playroom → 开 werewolf session(201) → WS hello(1.3) →
// game_action start → game_state 广播 → 状态落库；附带 workroom 开狼人杀 403。
// 用法：node scripts/smoke-werewolf.mjs
import { spawn } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import WebSocket from "ws";
import { makeEnvelope } from "@botstalk/protocol";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "..");
const PORT = "18769";
const WS_URL = `ws://127.0.0.1:${PORT}`;
const HTTP_URL = `http://127.0.0.1:${PORT}`;
const DATA_DIR = "/dev/shm/botstalk-smoke-werewolf";

rmSync(DATA_DIR, { recursive: true, force: true });
mkdirSync(DATA_DIR, { recursive: true });

let passed = 0;
let total = 0;
function record(name, ok, reason = "") {
  total += 1;
  if (ok) {
    passed += 1;
    process.stdout.write(`[PASS] ${name}\n`);
  } else {
    process.stdout.write(`[FAIL] ${name}: ${reason}\n`);
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

const gw = spawn("node", ["gateway/dist/index.js"], {
  cwd: REPO_ROOT,
  env: { ...process.env, GATEWAY_PORT: PORT, DATA_DIR },
  stdio: ["ignore", "pipe", "pipe"],
});
const children = [gw];
let ready = false;
gw.stdout.on("data", (buf) => {
  const s = buf.toString();
  if (s.includes(`listening on :${PORT}`)) ready = true;
  process.stdout.write(`[gw] ${s}`);
});
gw.stderr.on("data", (buf) => process.stderr.write(`[gw-err] ${buf}`));
gw.on("exit", (code, sig) => process.stdout.write(`[gw] exited code=${code} sig=${sig}\n`));

async function rest(method, path, body) {
  const res = await fetch(`${HTTP_URL}${path}`, {
    method,
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let json = null;
  try {
    json = JSON.parse(text);
  } catch {
    /* not json */
  }
  return { status: res.status, json, text };
}

function connectWs() {
  return new Promise((resolvePromise, reject) => {
    const ws = new WebSocket(WS_URL);
    ws.on("open", () => resolvePromise(ws));
    ws.on("error", reject);
  });
}

function sendHello(ws, room, version) {
  const env = makeEnvelope("hello", "smoke", room, 1, 0, {
    adapter_id: "smoke",
    protocol_version: version,
    last_seen_seq: 0,
  });
  ws.send(JSON.stringify(env));
}

function sendGameAction(ws, seq, game, seat, action) {
  const env = makeEnvelope("game_action", "smoke", "ww-smoke", seq, 0, {
    game,
    seat,
    action,
  });
  ws.send(JSON.stringify(env));
}

function waitForFrame(ws, pred, timeoutMs, label) {
  return new Promise((resolvePromise, reject) => {
    const timer = setTimeout(() => {
      ws.off("message", onMsg);
      reject(new Error(`timeout waiting for ${label}`));
    }, timeoutMs);
    function onMsg(raw) {
      let env;
      try {
        env = JSON.parse(raw.toString());
      } catch {
        return;
      }
      if (pred(env)) {
        clearTimeout(timer);
        ws.off("message", onMsg);
        resolvePromise(env);
      }
    }
    ws.on("message", onMsg);
  });
}

async function main() {
  for (let i = 0; i < 100 && !ready; i++) await sleep(100);
  record("gateway started", ready, "gateway did not listen in 10s");
  if (!ready) return 1;

  // 1. 建 playroom
  const r1 = await rest("POST", "/api/rooms", {
    id: "ww-smoke",
    name: "狼人杀冒烟",
    type: "playroom",
  });
  record("create playroom 201", r1.status === 201, `status=${r1.status} ${r1.text}`);

  // 2. playroom 开 werewolf session → 201
  const r2 = await rest("POST", "/api/rooms/ww-smoke/games", { game: "werewolf" });
  record("open werewolf session 201", r2.status === 201, `status=${r2.status} ${r2.text}`);

  // 3. workroom 开 werewolf → 403（游戏清单守卫）
  const rw = await rest("POST", "/api/rooms", { id: "ww-smoke-w", type: "workroom" });
  record("create workroom 201", rw.status === 201, `status=${rw.status}`);
  const r3 = await rest("POST", "/api/rooms/ww-smoke-w/games", { game: "werewolf" });
  record(
    "workroom open werewolf 403",
    r3.status === 403 && r3.json?.error === "ROOM_TYPE_FORBIDDEN",
    `status=${r3.status} ${r3.text}`,
  );

  // 4. WS hello protocol_version=1.3 → 连接保持打开（网关不回 welcome 帧）
  const ws = await connectWs();
  let closeCode13 = null;
  ws.on("close", (code) => {
    closeCode13 = code;
  });
  sendHello(ws, "ww-smoke", "1.3");
  await sleep(1200);
  record("ws hello 1.3 accepted (conn open)", closeCode13 === null, `closeCode=${closeCode13}`);

  // 5. 旧版本 1.2 hello 应被拒绝（4400 protocol version mismatch）
  const ws2 = await connectWs();
  let closeCode12 = null;
  ws2.on("close", (code) => {
    closeCode12 = code;
  });
  sendHello(ws2, "ww-smoke", "1.2");
  for (let i = 0; i < 40 && closeCode12 === null; i++) await sleep(100);
  record(
    "ws hello 1.2 rejected (4400)",
    closeCode12 === 4400,
    `closeCode=${closeCode12}`,
  );
  ws2.terminate();

  // 6. game_action start → game_state 广播
  const seats = ["s1", "s2", "s3", "s4", "s5", "s6"];
  sendGameAction(ws, 2, "werewolf", "s1", { kind: "start", seats });
  let gs = null;
  try {
    gs = await waitForFrame(
      ws,
      (e) => e.type === "game_state" && e.payload?.game === "werewolf",
      5000,
      "game_state",
    );
  } catch (e) {
    record("game_action start → game_state", false, e.message);
  }
  if (gs) {
    record("game_action start → game_state", true);
    const outer = gs.payload.state;
    const inner = outer && typeof outer === "object" && "state" in outer ? outer.state : outer;
    record("state v=1 envelope", outer?.v === 1, JSON.stringify(outer)?.slice(0, 120));
    record(
      "inner state is valid game state",
      !!inner && typeof inner.phase === "string" && Array.isArray(inner.players) && inner.players.length === 6,
      `phase=${inner?.phase} players=${inner?.players?.length}`,
    );
    record("no error envelope", !outer?.error, JSON.stringify(outer?.error));
  }

  // 7. 状态已落库
  const r4 = await rest("GET", "/api/rooms/ww-smoke/games");
  const sess = r4.json?.sessions?.find((s) => s.game === "werewolf");
  let persistedOk = false;
  try {
    const st = JSON.parse(sess?.state ?? "null");
    const inner = st?.state;
    persistedOk = st?.v === 1 && !!inner && Array.isArray(inner.players) && inner.players.length === 6;
  } catch {
    persistedOk = false;
  }
  record("game state persisted to db", persistedOk, JSON.stringify(sess?.state)?.slice(0, 120));

  ws.close();
  return 0;
}

let code = 1;
try {
  code = await main();
} catch (e) {
  process.stdout.write(`[FATAL] ${e.stack ?? e}\n`);
}
for (const c of children) {
  try {
    c.kill("SIGTERM");
  } catch {
    /* ignore */
  }
}
process.stdout.write(`\nSMOKE: ${passed}/${total} passed\n`);
process.exit(passed === total ? 0 : 1);
