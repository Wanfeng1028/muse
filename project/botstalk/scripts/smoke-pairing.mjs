#!/usr/bin/env node

/**
 * Smoke test for botstalk pairing feature.
 * Usage: First build the gateway by running `npx tsc -p tsconfig.json` in the gateway directory,
 * then run this script from the project root: `node scripts/smoke-pairing.mjs`
 */

import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { request } from 'node:http';
import { rmSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = join(__dirname, '..');
const gatewayEntry = join(projectRoot, 'gateway', 'dist', 'index.js');
const dataDir = `/dev/shm/botstalk-smoke-pairing-${process.pid}`;

let gatewayProc = null;
let port = 0;

async function getFreePort() {
  return new Promise((resolve, reject) => {
    const srv = createServer();
    srv.listen(0, () => {
      port = srv.address().port;
      srv.close(() => resolve(port));
    });
    srv.on('error', reject);
  });
}

function fetch(method, path, body = null) {
  return new Promise((resolve, reject) => {
    const opts = {
      hostname: '127.0.0.1',
      port,
      path,
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    const req = request(opts, (res) => {
      let data = '';
      res.on('data', (chunk) => (data += chunk));
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, body: JSON.parse(data) });
        } catch {
          resolve({ status: res.statusCode, body: data });
        }
      });
    });
    req.on('error', reject);
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

async function waitForHealthz(timeout = 15000, interval = 200) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try {
      const res = await fetch('GET', '/healthz');
      if (res.status === 200) return;
    } catch {}
    await new Promise((r) => setTimeout(r, interval));
  }
  throw new Error('healthz timeout');
}

// 注意：process.exit() 不会走 finally，因此清理必须在 exit 之前显式调用。
function cleanup() {
  if (gatewayProc && !gatewayProc.killed) {
    gatewayProc.kill('SIGTERM');
  }
  try {
    rmSync(dataDir, { recursive: true, force: true });
  } catch {}
}

async function run() {
  try {
    // 1
    await getFreePort();
    gatewayProc = spawn('node', [gatewayEntry], {
      cwd: projectRoot,
      env: { ...process.env, GATEWAY_PORT: String(port), DATA_DIR: dataDir },
      stdio: 'inherit',
    });
    await waitForHealthz();
    console.log('ok 1 spawn-gateway');

    // 2
    let res = await fetch('POST', '/api/rooms', { id: 'pair-room', name: 'Pair', owner: 'alice' });
    if (res.status !== 201) throw { step: '2 create-room', ...res };
    console.log('ok 2 create-room');

    // 3
    res = await fetch('POST', '/api/rooms/pair-room/pairing-codes', { requester: 'mallory' });
    if (res.status !== 403) throw { step: '3 non-owner-pairing-code', ...res };
    console.log('ok 3 non-owner-pairing-code');

    // 4
    res = await fetch('POST', '/api/rooms/pair-room/pairing-codes', { requester: 'alice' });
    if (res.status !== 201) throw { step: '4 owner-pairing-code', ...res };
    const code = res.body.code || res.body.data?.code;
    const codeRegex = /^[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{4}-[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{4}$/;
    if (!codeRegex.test(code)) throw { step: '4 owner-pairing-code-format', status: res.status, body: { code } };
    console.log('ok 4 owner-pairing-code');

    // 5
    res = await fetch('POST', '/api/pairing-codes/redeem', { code: 'XXXX-XXXX', adapter_id: 'ghost' });
    if (res.status !== 404) throw { step: '5 redeem-invalid-code', ...res };
    console.log('ok 5 redeem-invalid-code');

    // 6
    res = await fetch('POST', '/api/pairing-codes/redeem', { code, adapter_id: 'dev1' });
    if (res.status !== 200) throw { step: '6 redeem-valid-code', ...res };
    if ((res.body.room || res.body.data?.room) !== 'pair-room') throw { step: '6 redeem-valid-code-room', ...res };
    console.log('ok 6 redeem-valid-code');

    // 7
    res = await fetch('GET', '/api/rooms/pair-room/members');
    if (res.status !== 200) throw { step: '7 get-members', ...res };
    const members = res.body.members || res.body.data?.members || [];
    if (!members.some(m => m.adapter_id === 'dev1')) throw { step: '7 get-members-dev1', ...res };
    console.log('ok 7 get-members');

    // 8
    res = await fetch('POST', '/api/pairing-codes/redeem', { code, adapter_id: 'dev2' });
    if (res.status !== 409) throw { step: '8 double-redeem', ...res };
    console.log('ok 8 double-redeem');

    // 9
    res = await fetch('POST', '/api/rooms/pair-room/pairing-codes', { requester: 'alice' });
    if (res.status !== 201) throw { step: '9 multi-code-redeem-create', ...res };
    const code2 = res.body.code || res.body.data?.code;
    res = await fetch('POST', '/api/pairing-codes/redeem', { code: code2, adapter_id: 'dev3' });
    if (res.status !== 200) throw { step: '9 multi-code-redeem', ...res };
    console.log('ok 9 multi-code-redeem');

    console.log('SMOKE_PAIRING_PASS');
    cleanup();
    process.exit(0);
  } catch (err) {
    const step = err.step || 'unknown';
    const status = err.status !== undefined ? err.status : 'N/A';
    const body = err.body !== undefined ? (typeof err.body === 'object' ? JSON.stringify(err.body) : err.body) : (err.message || 'N/A');
    console.error(`FAIL ${step} status=${status} body=${body}`);
    cleanup();
    process.exit(1);
  }
}

run();
