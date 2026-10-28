import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { WebSocket } from "ws";

const GATEWAY_PORT = Number(process.env.GATEWAY_PORT ?? 18492);
const dataDir = mkdtempSync(join(tmpdir(), "smoke-device-auth-"));
let child = null;
let step = 0;
const ok = (cond, label) => { step += 1; if (!cond) { console.log(`FAIL step ${step}: ${label}`); process.exitCode = 1; throw new Error(label); } console.log(`ok step ${step}: ${label}`); };
const api = async (method, path, body) => { const res = await fetch(`http://127.0.0.1:${GATEWAY_PORT}${path}`, { method, headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined }); const text = await res.text(); let json = {}; try { json = JSON.parse(text); } catch { json = {}; } return { status: res.status, body: json }; };
const waitReady = async () => { for (let i = 0; i < 100; i++) { try { const res = await fetch(`http://127.0.0.1:${GATEWAY_PORT}/healthz`); if (res.ok) return; } catch {} await new Promise((r) => setTimeout(r, 200)); } throw new Error("gateway did not become ready"); };
const gatewayDir = join(dirname(fileURLToPath(import.meta.url)), "..", "gateway");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const sockets = [];
function connectWs() { return new Promise((res, rej) => { const ws = new WebSocket(`ws://127.0.0.1:${GATEWAY_PORT}`); ws.once("open", () => { sockets.push(ws); res(ws); }); ws.once("error", rej); }); }
function waitCloseCode(ws, timeoutMs = 3000) { return new Promise((res, rej) => { const t = setTimeout(() => rej(new Error("timeout waiting close")), timeoutMs); ws.once("close", (code) => { clearTimeout(t); res(code); }); }); }
function helloMsg(adapterId, device) { return JSON.stringify({ v: 1, type: "hello", seq: 1, ack: 0, sender: adapterId, room: "room1", ts: Date.now(), payload: { adapter_id: adapterId, protocol_version: "1.3", last_seen_seq: -1, ...device } }); }

try {
  child = spawn(process.execPath, ["dist/index.js"], { cwd: gatewayDir, env: { ...process.env, GATEWAY_PORT: String(GATEWAY_PORT), DATA_DIR: dataDir }, stdio: "pipe" });
  await waitReady();

  let res = await api("POST", "/api/rooms", { id: "room1", name: "Room 1", owner: "alice" }); ok(res.status === 201 || res.status === 200, "create room");
  res = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice" }); ok(res.status === 201 && typeof res.body.code === "string", "generate pairing code"); const code1 = res.body.code;
  res = await api("POST", "/api/pairing-codes/redeem", { code: code1, adapter_id: "adapter1", device_id: "phone-1" }); ok(res.status === 200 && res.body.device_id === "phone-1" && /^[0-9a-f]{64}$/.test(res.body.device_key), "redeem code 1"); const key1 = res.body.device_key;
  let ws = await connectWs(); ws.send(helloMsg("adapter1", { device_id: "phone-1", device_key: key1 })); await sleep(500); ok(ws.readyState === WebSocket.OPEN, "valid key hello stays open");
  ws = await connectWs(); const closeP5 = waitCloseCode(ws); ws.send(helloMsg("adapter1", { device_id: "phone-1", device_key: "0".repeat(64) })); ok((await closeP5) === 4403, "wrong key hello closed 4403");
  ws = await connectWs(); const closeP6 = waitCloseCode(ws); ws.send(helloMsg("adapter1", { device_id: "ghost", device_key: key1 })); ok((await closeP6) === 4403, "unknown device hello closed 4403");
  ws = await connectWs(); const closeP7 = waitCloseCode(ws); ws.send(helloMsg("adapter1", { device_id: "phone-1" })); ok((await closeP7) === 4403, "device_id alone closed 4403");
  ws = await connectWs(); ws.send(helloMsg("adapter1", {})); await sleep(500); ok(ws.readyState === WebSocket.OPEN, "legacy hello stays open");
  res = await api("DELETE", "/api/rooms/room1/devices/phone-1", { requester: "alice" }); ok(res.status === 204, "revoke device"); ws = await connectWs(); const closeP9 = waitCloseCode(ws); ws.send(helloMsg("adapter1", { device_id: "phone-1", device_key: key1 })); ok((await closeP9) === 4403, "revoked device hello closed 4403");
  ws = await connectWs(); ws.send(helloMsg("adapter1", {})); await sleep(500); ok(ws.readyState === WebSocket.OPEN, "legacy hello stays open after revoke");
} catch (e) {
  process.exitCode = 1;
} finally {
  for (const ws of sockets) { try { ws.terminate(); } catch { /* ignore */ } }
  if (child) {
    child.kill("SIGTERM");
    await new Promise((r) => setTimeout(r, 500));
  }
  rmSync(dataDir, { recursive: true, force: true });
  if (process.exitCode !== 1) {
    console.log("SMOKE_DEVICE_AUTH_PASS");
  }
}