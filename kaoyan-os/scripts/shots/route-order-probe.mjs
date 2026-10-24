import { spawnServer, waitForHealth, registerAndLogin, createShotContext, shutdown } from './shot-harness.mjs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { existsSync, unlinkSync } from 'node:fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const repoRoot = resolve(__dirname, '..', '..');

function parsePort() {
  const idx = process.argv.indexOf('--port');
  if (idx !== -1 && process.argv[idx + 1]) {
    return Number(process.argv[idx + 1]);
  }
  return 18133;
}

async function main() {
  const port = parsePort();
  const dbPath = resolve(repoRoot, 'scripts', 'shots', '.probe.db');

  if (existsSync(dbPath)) {
    unlinkSync(dbPath);
  }

  let serverProc;
  let browser;
  let page;

  try {
    serverProc = await spawnServer({ port, dbPath });
    await waitForHealth(port);

    const token = await registerAndLogin(port, 'probe', 'probe-pass-123456');
    const ctx = await createShotContext({ port, token });
    browser = ctx.browser;
    page = await ctx.context.newPage();

    await page.goto(`http://127.0.0.1:${port}/`);

    const results = await page.evaluate(async () => {
      const out = {};

      try {
        const res = await fetch('/api/health');
        const json = await res.json();
        out.health = json.status === 'ok';
      } catch {
        out.health = false;
      }

      try {
        const res = await fetch('/');
        const text = await res.text();
        const head = text.slice(0, 200).toLowerCase();
        out.index = head.startsWith('<') && (head.includes('<html') || head.includes('<!doctype'));
      } catch {
        out.index = false;
      }

      try {
        const res = await fetch('/api/plans');
        const json = await res.json();
        out.plans = Array.isArray(json);
      } catch {
        out.plans = false;
      }

      return out;
    });

    const failures = [];
    if (!results.health) failures.push('health');
    if (!results.index) failures.push('index');
    if (!results.plans) failures.push('plans');

    if (failures.length === 0) {
      console.log('ROUTE-ORDER PROBE PASS');
    } else {
      console.log(`ROUTE-ORDER PROBE FAIL: ${failures.join(', ')}`);
      process.exitCode = 1;
    }
  } finally {
    await shutdown(serverProc, browser);
    try {
      if (existsSync(dbPath)) unlinkSync(dbPath);
    } catch {}
  }
}

try {
  await main();
} catch (err) {
  console.log('ROUTE-ORDER PROBE FAIL');
  console.error(err.message || err);
  process.exitCode = 1;
}
