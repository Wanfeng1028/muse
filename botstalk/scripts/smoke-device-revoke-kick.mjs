import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

delete process.env.BOTSTALK_DEVICE_ID;
delete process.env.BOTSTALK_DEVICE_KEY;

import { AdapterClient } from "../adapters/base/dist/index.js";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

const GATEWAY_PORT = process.env.GATEWAY_PORT || "18494";
const GATEWAY_URL = `http://127.0.0.1:${GATEWAY_PORT}`;
const WS_GATEWAY_URL = `ws://127.0.0.1:${GATEWAY_PORT}`;

let okCount = 0;
function ok(msg) {
  okCount += 1;
  console.log(`  ok [${okCount}] ${msg}`);
}

const DATA_DIR = mkdtempSync(join(tmpdir(), "smoke-device-revoke-kick-"));

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

const gateway = spawn("node", ["dist/index.js"], {
  cwd: join(__dirname, "..", "gateway"),
  env: { ...process.env, GATEWAY_PORT, DATA_DIR },
  stdio: "inherit",
});

const clients = [];

try {
  await waitReady(`${GATEWAY_URL}/healthz`);
  ok("gateway ready");

  const createRoom = await postJson("/api/rooms", {
    id: "room1",
    name: "Room 1",
    owner: "alice",
  });
  if (createRoom.status !== 200 && createRoom.status !== 201) {
    throw new Error(`create room failed: ${createRoom.status}`);
  }
  ok("room created");

  const pairing = await postJson("/api/rooms/room1/pairing-codes", {
    requester: "alice",
  });
  if (pairing.status !== 201 || typeof pairing.data?.code !== "string") {
    throw new Error(`pairing code failed: ${pairing.status}`);
  }
  const code = pairing.data.code;
  ok("pairing code issued");

  const redeem = await postJson("/api/pairing-codes/redeem", {
    code,
    adapter_id: "adapter1",
    device_id: "phone-1",
  });
  if (redeem.status !== 200 || typeof redeem.data?.device_key !== "string" || !/^[0-9a-f]{64}$/.test(redeem.data.device_key)) {
    throw new Error(`redeem failed: ${redeem.status}`);
  }
  const deviceKey = redeem.data.device_key;
  ok("device paired");

  const deviceClient = new AdapterClient({
    adapterId: "adapter1",
    gatewayUrl: WS_GATEWAY_URL,
    room: "room1",
    heartbeatMs: 200,
    device: { id: "phone-1", key: deviceKey },
  });
  clients.push(deviceClient);
  deviceClient.connect();
  if (!(await waitForPresence("room1", "adapter1"))) {
    throw new Error("device client not present");
  }
  ok("device client online");

  const legacyClient = new AdapterClient({
    adapterId: "adapter2",
    gatewayUrl: WS_GATEWAY_URL,
    room: "room1",
    heartbeatMs: 200,
  });
  clients.push(legacyClient);
  legacyClient.connect();
  if (!(await waitForPresence("room1", "adapter2"))) {
    throw new Error("legacy client not present");
  }
  ok("legacy client online");

  const unknownRevoke = await deleteJson("/api/rooms/room1/devices/nope", {
    requester: "alice",
  });
  if (unknownRevoke.status !== 404) {
    throw new Error(`unknown device revoke expected 404, got ${unknownRevoke.status}`);
  }
  const presenceAfterUnknown = await getPresence("room1");
  const membersAfterUnknown = presenceAfterUnknown.members || [];
  if (!membersAfterUnknown.some((m) => m.adapter_id === "adapter1" && m.status === "online")) {
    throw new Error("adapter1 missing after unknown revoke");
  }
  if (!membersAfterUnknown.some((m) => m.adapter_id === "adapter2" && m.status === "online")) {
    throw new Error("adapter2 missing after unknown revoke");
  }
  ok("unknown device revoke did not kick anyone");

  const revoke = await deleteJson("/api/rooms/room1/devices/phone-1", {
    requester: "alice",
  });
  if (revoke.status !== 204) {
    throw new Error(`revoke expected 204, got ${revoke.status}`);
  }
  ok("device revoked");

  await new Promise((r) => setTimeout(r, 1500));
  if (!(await waitForPresenceAbsent("room1", "adapter1"))) {
    throw new Error("adapter1 still present after revoke");
  }
  ok("revoked device kicked offline");

  const presenceAfterRevoke = await getPresence("room1");
  const membersAfterRevoke = presenceAfterRevoke.members || [];
  if (!membersAfterRevoke.some((m) => m.adapter_id === "adapter2" && m.status === "online")) {
    throw new Error("adapter2 missing after revoke");
  }
  ok("legacy client unaffected");

  console.log("SMOKE_DEVICE_REVOKE_KICK_PASS");
} catch (err) {
  console.error("SMOKE_DEVICE_REVOKE_KICK_FAIL:", err);
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
