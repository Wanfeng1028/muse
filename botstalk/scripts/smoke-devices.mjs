import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const GATEWAY_PORT = Number(process.env.GATEWAY_PORT ?? 18491);
const dataDir = mkdtempSync(join(tmpdir(), "smoke-devices-"));
let child = null;
let step = 0;
const ok = (cond, label) => { step += 1; if (!cond) { console.log(`FAIL step ${step}: ${label}`); process.exitCode = 1; throw new Error(label); } console.log(`ok step ${step}: ${label}`); };
const api = async (method, path, body) => { const res = await fetch(`http://127.0.0.1:${GATEWAY_PORT}${path}`, { method, headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined }); const text = await res.text(); let json = {}; try { json = JSON.parse(text); } catch { json = {}; } return { status: res.status, body: json }; };
const waitReady = async () => { for (let i = 0; i < 100; i++) { try { const res = await fetch(`http://127.0.0.1:${GATEWAY_PORT}/healthz`); if (res.ok) return; } catch {} await new Promise((r) => setTimeout(r, 200)); } throw new Error("gateway did not become ready"); };

const gatewayDir = join(dirname(fileURLToPath(import.meta.url)), "..", "gateway");

try {
  child = spawn(process.execPath, ["dist/index.js"], { cwd: gatewayDir, env: { ...process.env, GATEWAY_PORT: String(GATEWAY_PORT), DATA_DIR: dataDir }, stdio: "pipe" });
  await waitReady();

  let res = await api("POST", "/api/rooms", { id: "room1", name: "Room 1", owner: "alice" });
  ok(res.status === 201 || res.status === 200, "create room");

  res = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice" });
  ok(res.status === 201 && typeof res.body.code === "string", "generate pairing code 1");
  const code1 = res.body.code;

  res = await api("POST", "/api/pairing-codes/redeem", { code: code1, adapter_id: "adapter1", device_id: "phone-1" });
  ok(res.status === 200 && res.body.device_id === "phone-1" && /^[0-9a-f]{64}$/.test(res.body.device_key), "redeem code 1");
  const key1 = res.body.device_key;

  res = await api("GET", "/api/rooms/room1/devices?requester=alice");
  ok(res.status === 200 && Array.isArray(res.body.devices) && res.body.devices.length === 1 && res.body.devices[0].device_id === "phone-1" && !("device_key_hash" in res.body.devices[0]), "list devices");

  res = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice" });
  ok(res.status === 201 && typeof res.body.code === "string", "generate pairing code 2");
  const code2 = res.body.code;
  
  res = await api("POST", "/api/pairing-codes/redeem", { code: code2, adapter_id: "adapter1", device_id: "phone-1" });
  ok(res.status === 200 && res.body.device_key !== key1, "redeem code 2 with new key");
  
  res = await api("GET", "/api/rooms/room1/devices?requester=alice");
  ok(res.status === 200 && Array.isArray(res.body.devices) && res.body.devices.length === 1 && res.body.devices[0].device_id === "phone-1", "list devices still 1");

  res = await api("DELETE", "/api/rooms/room1/devices/phone-1", { requester: "alice" });
  ok(res.status === 204, "delete device");
  
  res = await api("GET", "/api/rooms/room1/devices?requester=alice");
  ok(res.status === 200 && Array.isArray(res.body.devices) && res.body.devices.length === 1 && typeof res.body.devices[0].revoked_at_ms === "number", "device revoked_at_ms is number");

  res = await api("POST", "/api/rooms/room1/pairing-codes", { requester: "alice" });
  ok(res.status === 201 && typeof res.body.code === "string", "generate pairing code 3");
  const code3 = res.body.code;
  
  res = await api("POST", "/api/pairing-codes/redeem", { code: code3, adapter_id: "adapter1", device_id: "phone-1" });
  ok(res.status === 403 && res.body.error === "DEVICE_REVOKED", "redeem code 3 fails with DEVICE_REVOKED");

} catch (e) {
  process.exitCode = 1;
} finally {
  if (child) {
    child.kill("SIGTERM");
    await new Promise((r) => setTimeout(r, 500));
  }
  rmSync(dataDir, { recursive: true, force: true });
  if (process.exitCode !== 1) {
    console.log("SMOKE_DEVICES_PASS");
  }
}
