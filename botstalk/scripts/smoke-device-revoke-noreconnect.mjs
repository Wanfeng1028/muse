import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

delete process.env.BOTSTALK_DEVICE_ID;
delete process.env.BOTSTALK_DEVICE_KEY;

import { AdapterClient } from "../adapters/base/dist/index.js";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

const GATEWAY_PORT = process.env.GATEWAY_PORT || "18495";
const GATEWAY_URL = `http://127.0.0.1:${GATEWAY_PORT}`;
const WS_GATEWAY_URL = `ws://127.0.0.1:${GATEWAY_PORT}`;

let okCount = 0;
function ok(msg) {
  okCount += 1;
  console.log(`  ok [${okCount}] ${msg}`);
}

const DATA_DIR = mkdtempSync(join(tmpdir(), "smoke-device-revoke-noreconnect-"));

async function waitReady(url, timeoutMs = 10000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url);
      if (res.ok) return true;
    } catch {}
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error(`gateway not ready: ${url}`);
}

async function postJson(path, body) {
  const res = await fetch(`${GATEWAY_URL}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  let data = null;
  try {
    data = await res.json();
  } catch {}
  return { status: res.status, data };
}

async function deleteJson(path, body) {
  const res = await fetch(`${GATEWAY_URL}${path}`, {
    method: "DELETE",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  let data = null;
  try {
    data = await res.json();
  } catch {}
  return { status: res.status, data };
}

async function getPresence(room) {
  const res = await fetch(`${GATEWAY_URL}/api/rooms/${room}/presence`);
  return res.json();
}

async function waitForPresence(room, adapterId, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const presence = await getPresence(room);
      const members = presence.members || [];
      if (members.some((m) => m.adapter_id === adapterId && m.status === "online")) return true;
    } catch {}
    await new Promise((r) => setTimeout(r, 100));
  }
  return false;
}

async function waitForPresenceAbsent(room, adapterId, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const presence = await getPresence(room);
      const members = presence.members || [];
      if (!members.some((m) => m.adapter_id === adapterId && m.status === "online")) return true;
    } catch {}
    await new Promise((r) => setTimeout(r, 100));
  }
  return false;
}

const gateway = spawn("node", ["dist/index.js"], { cwd: join(__dirname, "..", "gateway"), env: { ...process.env, GATEWAY_PORT, DATA_DIR }, stdio: "inherit" });
const clients = [];
try {
  if (!(await waitReady(`${GATEWAY_URL}/healthz`))) throw new Error("gateway not ready");
  ok("gateway ready");

  const roomRes = await postJson("/api/rooms", { id: "room1", name: "Room 1", owner: "alice" });
  if (roomRes.status !== 200 && roomRes.status !== 201) throw new Error("room creation failed");
  ok("room created");

  const codeRes = await postJson("/api/rooms/room1/pairing-codes", { requester: "alice" });
  if (codeRes.status !== 201 || typeof codeRes.data.code !== "string") throw new Error("pairing code issuance failed");
  const code = codeRes.data.code;
  ok("pairing code issued");

  const redeemRes = await postJson("/api/pairing-codes/redeem", { code, adapter_id: "adapter1", device_id: "phone-1" });
  if (redeemRes.status !== 200 || !/^[0-9a-f]{64}$/.test(redeemRes.data.device_key)) throw new Error("device redeem failed");
  const deviceKey = redeemRes.data.device_key;
  ok("device paired");

  const calls = [];
  const client = new AdapterClient({
    adapterId: "adapter1",
    gatewayUrl: WS_GATEWAY_URL,
    room: "room1",
    heartbeatMs: 200,
    device: { id: "phone-1", key: deviceKey },
    onDeviceAuthFailed: (c, reason) => { calls.push([c, reason]); }
  });
  clients.push(client);
  await client.connect();
  if (!(await waitForPresence("room1", "adapter1"))) throw new Error("device client not online");
  ok("device client online");

  const revokeRes = await deleteJson("/api/rooms/room1/devices/phone-1", { requester: "alice" });
  if (revokeRes.status !== 204) throw new Error("device revoke failed");
  ok("device revoked");

  await new Promise(r => setTimeout(r, 3500));
  if (calls.length !== 1 || calls[0][0] !== 4403 || calls[0][1] !== "device revoked") throw new Error("unexpected calls state");
  ok("no reconnect after revoke");

  if (client.hasDeviceAuthFailure() !== true) throw new Error("auth failure not flagged");
  ok("auth failure flagged");

  if (!(await waitForPresenceAbsent("room1", "adapter1"))) throw new Error("revoked device still online");
  ok("revoked device offline");

  console.log("SMOKE_DEVICE_REVOKE_NORECONNECT_PASS");
} catch (err) {
  console.log("SMOKE_DEVICE_REVOKE_NORECONNECT_FAIL: " + err);
  throw err;
} finally {
  for (const c of clients) await c.disconnect();
  gateway.kill("SIGTERM");
  await new Promise(r => setTimeout(r, 500));
  if (gateway.exitCode === null) {
    gateway.kill("SIGKILL");
    await new Promise(r => setTimeout(r, 200));
  }
  rmSync(DATA_DIR, { recursive: true, force: true });
}

