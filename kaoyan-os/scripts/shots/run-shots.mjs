import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { existsSync, unlinkSync } from 'node:fs';
import {
  spawnServer,
  waitForHealth,
  registerAndLogin,
  seedDemoData,
  createShotContext,
  runShotPlan,
  shutdown,
} from './shot-harness.mjs';
import { defaultShotPlan } from './shot-plan.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '../..');

function parseArgs() {
  const args = process.argv.slice(2);
  let port = 18131;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--port' && args[i + 1] !== undefined) {
      port = Number(args[i + 1]);
      i++;
    }
  }
  return { port };
}

async function main() {
  const { port } = parseArgs();
  const dbPath = resolve(repoRoot, 'scripts/shots/.shot-demo.db');
  const outDir = resolve(repoRoot, 'docs/screenshots');

  if (existsSync(dbPath)) {
    unlinkSync(dbPath);
  }

  const serverProc = spawnServer({ port, dbPath });
  let browser = null;

  try {
    await waitForHealth(port);
    const token = await registerAndLogin(port, 'shotbot', 'shot-pass-123456');
    await seedDemoData(port, token);
    const ctx = await createShotContext({ port, token });
    browser = ctx.browser;
    const page = await ctx.context.newPage();
    await runShotPlan(page, defaultShotPlan, outDir, port);
    console.log('[harness] 截图完成，清单：');
    for (const item of defaultShotPlan) {
      console.log(`  ✓ ${item.shotName}  (${item.name})`);
    }
  } catch (e) {
    console.error(`[harness] FATAL ${e.message}`);
    process.exitCode = 1;
  } finally {
    await shutdown(serverProc, browser);
  }
}

main();
