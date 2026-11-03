import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

const GATEWAY_PORT = process.env.GATEWAY_PORT || "18497";
const GATEWAY_URL = `http://127.0.0.1:${GATEWAY_PORT}`;
const DATA_DIR = mkdtempSync(join(tmpdir(), "smoke-share-ttl-"));

let passed = 0;
function ok(name) { passed++; console.log(`ok ${passed}: ${name}`); }

async function waitReady(timeoutMs = 10000) {
  const start = Date.now();
  for (;;) {
    try {
      const res = await fetch(`${GATEWAY_URL}/healthz`);
      if (res.ok) return;
    } catch {}
    if (Date.now() - start > timeoutMs) {
      throw new Error("gateway did not become ready in time");
    }
    await new Promise((r) => setTimeout(r, 100));
  }
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data = null;
  try { data = await res.json(); } catch { data = null; }
  return { status: res.status, data };
}

const gateway = spawn("node", ["dist/index.js"], {
  cwd: join(__dirname, "..", "gateway"),
  env: { ...process.env, GATEWAY_PORT, DATA_DIR },
  stdio: "inherit",
});

try {
  // 1. gateway ready
  await waitReady();
  ok("gateway ready");

  // 2. room created
  {
    const res = await postJson(`${GATEWAY_URL}/api/rooms`, { id: "room1", name: "Room 1", owner: "alice" });
    if (res.status !== 200 && res.status !== 201) {
      throw new Error(`room created: unexpected status ${res.status}`);
    }
    ok("room created");
  }

  // 3. ttl_hours=0 rejected
  {
    const res = await postJson(`${GATEWAY_URL}/api/rooms/room1/share-links`, { requester: "alice", ttl_hours: 0 });
    if (res.status !== 400 || res.data?.error !== "INVALID_TTL_HOURS") {
      throw new Error(`ttl_hours=0 rejected: status ${res.status}, error ${res.data?.error}`);
    }
    ok("ttl_hours=0 rejected");
  }

  // 4. ttl_hours=721 rejected
  {
    const res = await postJson(`${GATEWAY_URL}/api/rooms/room1/share-links`, { requester: "alice", ttl_hours: 721 });
    if (res.status !== 400 || res.data?.error !== "INVALID_TTL_HOURS") {
      throw new Error(`ttl_hours=721 rejected: status ${res.status}, error ${res.data?.error}`);
    }
    ok("ttl_hours=721 rejected");
  }

  // 5. ttl_hours="24" rejected
  {
    const res = await postJson(`${GATEWAY_URL}/api/rooms/room1/share-links`, { requester: "alice", ttl_hours: "24" });
    if (res.status !== 400 || res.data?.error !== "INVALID_TTL_HOURS") {
      throw new Error(`ttl_hours="24" rejected: status ${res.status}, error ${res.data?.error}`);
    }
    ok(`ttl_hours="24" rejected`);
  }

  // 6. non-owner rejected
  {
    const res = await postJson(`${GATEWAY_URL}/api/rooms/room1/share-links`, { requester: "mallory", ttl_hours: 0 });
    if (res.status !== 403 || res.data?.error !== "ROOM_MANAGE_FORBIDDEN") {
      throw new Error(`non-owner rejected: status ${res.status}, error ${res.data?.error}`);
    }
    ok("non-owner rejected");
  }

  // 7. ttl_hours=1 ok
  {
    const anchor = Date.now();
    const res = await postJson(`${GATEWAY_URL}/api/rooms/room1/share-links`, { requester: "alice", ttl_hours: 1 });
    if (res.status !== 201) {
      throw new Error(`ttl_hours=1 ok: unexpected status ${res.status}`);
    }
    if (typeof res.data?.share_token !== "string" || res.data.share_token.length !== 32) {
      throw new Error("ttl_hours=1 ok: share_token not a 32-char string");
    }
    const delta = res.data.expires_at_ms - anchor;
    if (delta < 3300000 || delta > 3900000) {
      throw new Error(`ttl_hours=1 ok: expires_at_ms delta ${delta} out of range`);
    }
    ok("ttl_hours=1 ok");
  }

  // 8. default ttl ok
  {
    const anchor = Date.now();
    const res = await postJson(`${GATEWAY_URL}/api/rooms/room1/share-links`, { requester: "alice" });
    if (res.status !== 201) {
      throw new Error(`default ttl ok: unexpected status ${res.status}`);
    }
    if (typeof res.data?.share_token !== "string" || res.data.share_token.length !== 32) {
      throw new Error("default ttl ok: share_token not a 32-char string");
    }
    const delta = res.data.expires_at_ms - anchor;
    if (delta < 604200000 || delta > 605400000) {
      throw new Error(`default ttl ok: expires_at_ms delta ${delta} out of range`);
    }
    ok("default ttl ok");
  }
} finally {
  gateway.kill();
  rmSync(DATA_DIR, { recursive: true, force: true });
  console.log("SMOKE_SHARE_TTL_PASS");
}
