#!/usr/bin/env node
// Smoke test for botstalk share-link management (OpenAgents round 11):
// issue / list / read-only view / revoke / revoked view, via a real gateway.
// Usage: build the gateway first (npx tsc -p tsconfig.json in gateway/),
// then run from botstalk/: node scripts/smoke-share-manage.mjs
import { spawn } from 'node:child_process';
import { createServer, request } from 'node:http';
import { rmSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = join(__dirname, '..');
const gatewayEntry = join(projectRoot, 'gateway', 'dist', 'index.js');
const dataDir = `/dev/shm/botstalk-smoke-share-manage-${process.pid}`;
let gatewayProc = null;
let port = 0;

async function getFreePort() {
  return new Promise((resolve, reject) => {
    const srv = createServer();
    srv.listen(0, () => { port = srv.address().port; srv.close(() => resolve(port)); });
    srv.on('error', reject);
  });
}

function fetch(method, path, body = null) {
  // Node http client does not frame a DELETE body on its own (no
  // Content-Length, no chunked encoding), which the gateway's HTTP
  // parser rejects with 400. Browsers set Content-Length for fetch
  // bodies, so set it explicitly here to match real browser behavior.
  const payload = body ? JSON.stringify(body) : null;
  const headers = { 'Content-Type': 'application/json' };
  if (payload) headers['Content-Length'] = Buffer.byteLength(payload);
  return new Promise((resolve, reject) => {
    const req = request({ hostname: '127.0.0.1', port, path, method, headers }, (res) => {
      let data = '';
      res.on('data', (c) => { data += c; });
      res.on('end', () => {
        try { resolve({ status: res.statusCode, body: JSON.parse(data) }); }
        catch { resolve({ status: res.statusCode, body: data }); }
      });
    });
    req.on('error', reject);
    if (payload) req.write(payload);
    req.end();
  });
}

async function waitForHealthz(timeout = 15000, interval = 200) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try { const res = await fetch('GET', '/healthz'); if (res.status === 200) return; } catch {}
    await new Promise((r) => setTimeout(r, interval));
  }
  throw new Error('healthz timeout');
}

function cleanup() {
  if (gatewayProc && !gatewayProc.killed) gatewayProc.kill('SIGTERM');
  try { rmSync(dataDir, { recursive: true, force: true }); } catch {}
}

async function run() {
  try {
    await getFreePort();
    gatewayProc = spawn('node', [gatewayEntry], {
      cwd: projectRoot,
      env: { ...process.env, GATEWAY_PORT: String(port), DATA_DIR: dataDir },
      stdio: 'inherit',
    });
    await waitForHealthz();
    console.log('ok 1 spawn-gateway');
    let res = await fetch('POST', '/api/rooms', { id: 'share-room', name: 'ShareRoom', owner: 'alice' });
    if (res.status !== 201) throw { step: '2 create-room', ...res };
    console.log('ok 2 create-room');
    res = await fetch('POST', '/api/rooms/share-room/share-links', { requester: 'mallory', ttl_hours: 168 });
    if (res.status !== 403 || res.body.error !== 'ROOM_MANAGE_FORBIDDEN') throw { step: '3 non-owner-issue', ...res };
    console.log('ok 3 non-owner-issue-forbidden');
    res = await fetch('POST', '/api/rooms/share-room/share-links', { requester: 'alice', ttl_hours: 168 });
    if (res.status !== 201) throw { step: '4 owner-issue', ...res };
    const token = res.body.share_token;
    const linkId = res.body.id;
    if (!/^[A-Za-z0-9]{32}$/.test(token || '')) throw { step: '4 owner-issue-token-format', body: { id: linkId } };
    if (res.body.share_url !== '/share/' + token) throw { step: '4 owner-issue-url', ...res };
    console.log('ok 4 owner-issue');
    res = await fetch('GET', '/api/rooms/share-room/share-links?requester=alice');
    if (res.status !== 200) throw { step: '5 list', ...res };
    if (!Array.isArray(res.body.links) || res.body.links.length !== 1) throw { step: '5 list-count', ...res };
    if ('share_token' in res.body.links[0] || 'token_hash' in res.body.links[0]) throw { step: '5 list-no-token-leak', ...res };
    if (res.body.links[0].id !== linkId) throw { step: '5 list-id', ...res };
    console.log('ok 5 list-no-token-leak');
    res = await fetch('GET', '/api/share/' + token);
    if (res.status !== 200) throw { step: '6 share-view', ...res };
    if (res.body.room.id !== 'share-room' || !Array.isArray(res.body.messages)) throw { step: '6 share-view-shape', ...res };
    console.log('ok 6 share-view');
    res = await fetch('GET', '/api/share/' + token);
    if (res.status !== 200) throw { step: '7 share-view-refresh', ...res };
    console.log('ok 7 share-view-refresh');
    res = await fetch('DELETE', '/api/rooms/share-room/share-links/' + linkId, { requester: 'mallory' });
    if (res.status !== 403) throw { step: '8 non-owner-revoke', ...res };
    console.log('ok 8 non-owner-revoke-forbidden');
    res = await fetch('DELETE', '/api/rooms/share-room/share-links/' + linkId, { requester: 'alice' });
    if (res.status !== 204) throw { step: '9 owner-revoke', ...res };
    console.log('ok 9 owner-revoke');
    res = await fetch('GET', '/api/rooms/share-room/share-links?requester=alice');
    if (res.status !== 200 || res.body.links[0].revoked_at_ms == null) throw { step: '10 list-revoked', ...res };
    console.log('ok 10 list-revoked');
    res = await fetch('GET', '/api/share/' + token);
    if (res.status !== 410 || res.body.error !== 'SHARE_LINK_REVOKED') throw { step: '11 revoked-view', ...res };
    console.log('ok 11 revoked-view');
    console.log('SMOKE_SHARE_MANAGE_PASS');
    cleanup();
    process.exit(0);
  } catch (e) {
    console.error('SMOKE_SHARE_MANAGE_FAIL', e);
    cleanup();
    process.exit(1);
  }
}
run();
