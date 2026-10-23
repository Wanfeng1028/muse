import assert from 'node:assert/strict';
import { setTimeout as sleep } from 'node:timers/promises';
import http from 'node:http';
import { unlinkSync } from 'node:fs';
import {
  spawnServer,
  waitForHealth,
  registerAndLogin,
  shutdown,
  apiRequest
} from './shot-harness.mjs';

const PORT = 18132;
const DB_PATH = '/home/hatch/workspace/muse-build/kaoyan-techdebt2-selfcheck.db';

function tryConnect(host, port, path) {
  return new Promise((resolve, reject) => {
    const req = http.request(
      { hostname: host, port, path, method: 'GET', timeout: 2000 },
      (res) => {
        res.resume();
        reject(new Error('connection accepted'));
      }
    );
    req.on('error', (err) => {
      if (err.code === 'ECONNREFUSED') resolve();
      else reject(err);
    });
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('socket timeout before ECONNREFUSED'));
    });
    req.end();
  });
}

async function main() {
  let serverProc = null;

  try {
    // ── 1. 就绪超时防线 ──
    const t0 = Date.now();
    try {
      await waitForHealth(9, { timeoutMs: 1500, intervalMs: 200 });
      assert.fail('waitForHealth on dead port should have thrown');
    } catch (err) {
      const elapsed = Date.now() - t0;
      assert.ok(
        elapsed >= 1500 && elapsed <= 5000,
        `timeout fired in ${elapsed}ms, expected 1500-5000ms`
      );
      assert.ok(
        err.message.includes('server not ready'),
        `error message "${err.message}" must contain "server not ready"`
      );
    }
    console.log('PASS: 就绪超时防线');

    // ── 2. 真实服务能起来 ──
    serverProc = spawnServer({ port: PORT, dbPath: DB_PATH });
    assert.ok(serverProc, 'spawnServer must return a truthy process handle');
    await waitForHealth(PORT, { timeoutMs: 60000, intervalMs: 1000 });
    console.log('PASS: 真实服务能起来');

    // ── 3. 注册登录链路 ──
    const token = await registerAndLogin(PORT, 'selfcheck', 'selfcheck-pass-123456');
    assert.ok(
      typeof token === 'string' && token.length > 0,
      'registerAndLogin must return a non-empty token string'
    );
    console.log('PASS: 注册登录链路');

    // ── 4. API代理透传 ──
    const createRes = await apiRequest(PORT, 'POST', '/api/plans', {
      token,
      body: {
        date: '2026-10-24',
        title: '自检计划',
        subject: 'math',
        plannedMinutes: 30
      }
    });
    assert.ok(
      createRes.status >= 200 && createRes.status < 300,
      `POST /api/plans returned ${createRes.status}, expected 2xx`
    );

    const listRes = await apiRequest(PORT, 'GET', '/api/plans', { token });
    assert.ok(
      listRes.status >= 200 && listRes.status < 300,
      `GET /api/plans returned ${listRes.status}, expected 2xx`
    );

    const body = listRes.json;
    const plans = Array.isArray(body)
      ? body
      : Array.isArray(body?.data)
        ? body.data
        : Array.isArray(body?.plans)
          ? body.plans
          : null;
    assert.ok(Array.isArray(plans), 'GET /api/plans response must contain a plans array');
    assert.ok(
      plans.some((p) => p.title === '自检计划'),
      'created plan "自检计划" must appear in the list'
    );
    console.log('PASS: API代理透传');

    // ── 5. 清理不留僵尸 ──
    try {
      await shutdown(serverProc, null);
    } catch (_e) {
      // harness shutdown may not accept null for the browser parameter;
      // fall back to SIGKILL to guarantee the server child process is terminated
      serverProc.kill('SIGKILL');
    }

    // Give the OS a moment to reap the child process
    await sleep(1000);

    const processDead =
      serverProc.exitCode !== null ||
      serverProc.signalCode !== null ||
      serverProc.killed === true;
    assert.ok(
      processDead,
      `server process must be dead (exitCode=${serverProc.exitCode}, signalCode=${serverProc.signalCode}, killed=${serverProc.killed})`
    );

    // After 3 seconds the port must refuse connections
    await sleep(3000);
    try {
      await tryConnect('127.0.0.1', PORT, '/api/health');
    } catch (connErr) {
      assert.fail(
        `port ${PORT} still reachable 3s after shutdown: ${connErr.message}`
      );
    }
    console.log('PASS: 清理不留僵尸');
  } catch (err) {
    console.log(`SELF-CHECK FAIL: ${err.message}`);
    // Emergency cleanup: ensure no orphaned server process or DB file
    if (serverProc) {
      try { serverProc.kill('SIGKILL'); } catch (_) {}
    }
    try { unlinkSync(DB_PATH); } catch (_) {}
    process.exit(1);
  }

  // Delete self-check DB file
  try { unlinkSync(DB_PATH); } catch (_) {}

  console.log('SELF-CHECK ALL PASS');
}

main();