import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

delete process.env.BOTSTALK_DEVICE_ID;
delete process.env.BOTSTALK_DEVICE_KEY;

import { AdapterClient } from "../adapters/base/dist/index.js";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

const GATEWAY_PORT = process.env.GATEWAY_PORT || "18493";
const GATEWAY_URL = `http://127.0.0.1:${GATEWAY_PORT}`;
const WS_GATEWAY_URL = `ws://127.0.0.1:${GATEWAY_PORT}`;

let okCount = 0;
function ok(msg) {
  okCount++;
  console.log(`  ok [${okCount}] ${msg}`);
}

const DATA_DIR = mkdtempSync(join(tmpdir(), "smoke-device-hello-"));

async function waitReady(url, timeoutMs = 10000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error("gateway not ready: " + url);
}

async function postJson(path, body) {
  const res = await fetch(GATEWAY_URL + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return { status: res.status, data };
}

async function getPresence(room) {
  const res = await fetch(`${GATEWAY_URL}/api/rooms/${room}/presence`);
  return res.json();
}

async function waitForPresence(room, adapterId, timeoutMs = 5000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const data = await getPresence(room);
      const members = Array.isArray(data.members) ? data.members : [];
      if (members.some((m) => m.adapter_id === adapterId)) return true;
    } catch {}
    await new Promise((r) => setTimeout(r, 200));
  }
  return false;
}

const gateway = spawn("node", ["dist/index.js"], {
  cwd: join(__dirname, "..", "gateway"),
  env: { ...process.env, GATEWAY_PORT, DATA_DIR },
  stdio: "inherit",
});

const clients = [];

try {
  await waitReady(`${GATEWAY_URL}/healthz`);
  ok("gateway ready");

  // Step 1: create room, generate pairing code, redeem
  const roomRes = await postJson("/api/rooms", { id: "room1", name: "Room 1", owner: "alice" });
  if (roomRes.status !== 200 && roomRes.status !== 201) {
    throw new Error("create room failed: " + roomRes.status);
  }
  ok("room created");

  const codeRes = await postJson("/api/rooms/room1/pairing-codes", { requester: "alice" });
  if (codeRes.status !== 201 || typeof codeRes.data.code !== "string") {
    throw new Error("pairing code failed: " + codeRes.status);
  }
  ok("pairing code generated");

  const redeemRes = await postJson("/api/pairing-codes/redeem", {
    code: codeRes.data.code,
    adapter_id: "adapter1",
    device_id: "phone-1",
  });
  if (redeemRes.status !== 200 || redeemRes.data.device_id !== "phone-1") {
    throw new Error("redeem failed: " + redeemRes.status);
  }
  if (!/^[0-9a-f]{64}$/.test(redeemRes.data.device_key)) {
    throw new Error("redeem device_key not 64-hex");
  }
  ok("pairing code redeemed");

  // Step 2: valid device client
  const client1 = new AdapterClient({
    adapterId: "adapter1",
    gatewayUrl: WS_GATEWAY_URL,
    room: "room1",
    heartbeatMs: 200,
    device: { id: "phone-1", key: redeemRes.data.device_key },
  });
  clients.push(client1);
  client1.connect();
  ok("valid device client connect() called");

  if (!(await waitForPresence("room1", "adapter1", 5000))) {
    throw new Error("adapter1 not present in presence within 5s");
  }
  ok("adapter1 present in presence");

  // Step 3: legacy client (no device)
  const client2 = new AdapterClient({
    adapterId: "adapter2",
    gatewayUrl: WS_GATEWAY_URL,
    room: "room1",
    heartbeatMs: 200,
  });
  clients.push(client2);
  client2.connect();
  ok("legacy client connect() called");

  if (!(await waitForPresence("room1", "adapter2", 5000))) {
    throw new Error("adapter2 not present in presence within 5s");
  }
  ok("adapter2 present in presence");

  // Step 4: wrong-key client
  const client3 = new AdapterClient({
    adapterId: "adapter3",
    gatewayUrl: WS_GATEWAY_URL,
    room: "room1",
    heartbeatMs: 200,
    device: { id: "phone-1", key: "0".repeat(64) },
  });
  clients.push(client3);
  client3.connect();
  ok("wrong-key client connect() called");

  await new Promise((r) => setTimeout(r, 1500));

  const presenceData = await getPresence("room1");
  const members = Array.isArray(presenceData.members) ? presenceData.members : [];
  if (members.some((m) => m.adapter_id === "adapter3")) {
    throw new Error("adapter3 should be absent from presence (wrong key)");
  }
  // 精确 4403 码由第 18 轮原始 WS 冒烟覆盖，本脚本以 presence 缺席为旁证，不重复断言码。
  ok("adapter3 absent from presence (wrong key rejected)");

  console.log("SMOKE_DEVICE_HELLO_PASS");
} catch (err) {
  console.error("SMOKE_DEVICE_HELLO_FAIL:", err);
  throw err;
} finally {
  for (const c of clients) {
    c.disconnect();
  }
  gateway.kill("SIGTERM");
  await new Promise((r) => setTimeout(r, 500));
  if (gateway.exitCode === null) {
    gateway.kill("SIGKILL");
    await new Promise((r) => setTimeout(r, 200));
  }
  try {
    rmSync(DATA_DIR, { recursive: true, force: true });
  } catch {}
}
