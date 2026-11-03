import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

const GATEWAY_PORT = process.env.GATEWAY_PORT || "18496";
const GATEWAY_URL = `http://127.0.0.1:${GATEWAY_PORT}`;

const DATA_DIR = mkdtempSync(join(tmpdir(), "smoke-pairing-ttl-"));

let passed = 0;
function ok(name) {
  passed++;
  console.log(`ok ${passed}: ${name}`);
}

async function waitReady(timeoutMs = 10000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(`${GATEWAY_URL}/healthz`);
      if (res.ok) return;
    } catch {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error(`gateway not ready within ${timeoutMs}ms at ${GATEWAY_URL}/healthz`);
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  return { status: res.status, data };
}

const gateway = spawn("node", ["dist/index.js"], {
  cwd: join(__dirname, "..", "gateway"),
  env: { ...process.env, GATEWAY_PORT, DATA_DIR },
  stdio: "inherit",
});

try {
  // 1. gateway ready
  await waitReady(10000);
  ok("gateway ready");

  // 2. create room
  const createRes = await postJson(`${GATEWAY_URL}/api/rooms`, {
    id: "room1",
    name: "Room 1",
    owner: "alice",
  });
  if (createRes.status !== 200 && createRes.status !== 201) {
    throw new Error(`expected create room status 200 or 201, got ${createRes.status} data ${JSON.stringify(createRes.data)}`);
  }
  ok("room created");

  // 3. ttl_minutes=0 -> 400 INVALID_TTL_MINUTES
  const res3 = await postJson(`${GATEWAY_URL}/api/rooms/room1/pairing-codes`, {
    requester: "alice",
    ttl_minutes: 0,
  });
  if (res3.status !== 400 || !res3.data || res3.data.error !== "INVALID_TTL_MINUTES") {
    throw new Error(`expected ttl_minutes=0 -> 400 INVALID_TTL_MINUTES, got status ${res3.status} data ${JSON.stringify(res3.data)}`);
  }
  ok("ttl_minutes=0 rejected");

  // 4. ttl_minutes=61 -> 400 INVALID_TTL_MINUTES
  const res4 = await postJson(`${GATEWAY_URL}/api/rooms/room1/pairing-codes`, {
    requester: "alice",
    ttl_minutes: 61,
  });
  if (res4.status !== 400 || !res4.data || res4.data.error !== "INVALID_TTL_MINUTES") {
    throw new Error(`expected ttl_minutes=61 -> 400 INVALID_TTL_MINUTES, got status ${res4.status} data ${JSON.stringify(res4.data)}`);
  }
  ok("ttl_minutes=61 rejected");

  // 5. ttl_minutes="x" -> 400 INVALID_TTL_MINUTES
  const res5 = await postJson(`${GATEWAY_URL}/api/rooms/room1/pairing-codes`, {
    requester: "alice",
    ttl_minutes: "x",
  });
  if (res5.status !== 400 || !res5.data || res5.data.error !== "INVALID_TTL_MINUTES") {
    throw new Error(`expected ttl_minutes="x" -> 400 INVALID_TTL_MINUTES, got status ${res5.status} data ${JSON.stringify(res5.data)}`);
  }
  ok("ttl_minutes=x rejected");

  // 6. ttl_minutes=1 -> 201, code string, expires_at_ms delta in [30000, 90000]
  const before6 = Date.now();
  const res6 = await postJson(`${GATEWAY_URL}/api/rooms/room1/pairing-codes`, {
    requester: "alice",
    ttl_minutes: 1,
  });
  if (res6.status !== 201) {
    throw new Error(`expected ttl_minutes=1 -> 201, got status ${res6.status} data ${JSON.stringify(res6.data)}`);
  }
  if (!res6.data || typeof res6.data.code !== "string") {
    throw new Error(`expected ttl_minutes=1 -> code string, got ${JSON.stringify(res6.data)}`);
  }
  const delta6 = res6.data.expires_at_ms - before6;
  if (delta6 < 30000 || delta6 > 90000) {
    throw new Error(`expected ttl_minutes=1 expires_at_ms delta in [30000, 90000], got ${delta6}`);
  }
  ok("ttl_minutes=1 issued");

  // 7. no ttl_minutes -> 201, delta in [540000, 660000]
  const before7 = Date.now();
  const res7 = await postJson(`${GATEWAY_URL}/api/rooms/room1/pairing-codes`, {
    requester: "alice",
  });
  if (res7.status !== 201) {
    throw new Error(`expected no ttl_minutes -> 201, got status ${res7.status} data ${JSON.stringify(res7.data)}`);
  }
  const delta7 = res7.data.expires_at_ms - before7;
  if (delta7 < 540000 || delta7 > 660000) {
    throw new Error(`expected default ttl expires_at_ms delta in [540000, 660000], got ${delta7}`);
  }
  ok("default ttl issued");

  // 8. ttl_minutes=60 -> 201, delta in [3540000, 3660000]
  const before8 = Date.now();
  const res8 = await postJson(`${GATEWAY_URL}/api/rooms/room1/pairing-codes`, {
    requester: "alice",
    ttl_minutes: 60,
  });
  if (res8.status !== 201) {
    throw new Error(`expected ttl_minutes=60 -> 201, got status ${res8.status} data ${JSON.stringify(res8.data)}`);
  }
  const delta8 = res8.data.expires_at_ms - before8;
  if (delta8 < 3540000 || delta8 > 3660000) {
    throw new Error(`expected ttl_minutes=60 expires_at_ms delta in [3540000, 3660000], got ${delta8}`);
  }
  ok("ttl_minutes=60 issued");

  console.log(`SMOKE_PAIRING_TTL_PASS (${passed} checks)`);
} catch (err) {
  console.error(`SMOKE_PAIRING_TTL_FAIL: ${err.message}`);
  throw err;
} finally {
  gateway.kill("SIGTERM");
  await new Promise((resolve) => {
    const timer = setTimeout(() => {
      gateway.kill("SIGKILL");
      resolve();
    }, 500);
    gateway.once("exit", () => {
      clearTimeout(timer);
      resolve();
    });
  });
  rmSync(DATA_DIR, { recursive: true, force: true });
}
