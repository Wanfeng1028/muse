import { PROJ, PW, CHROME, PROFILE, FFMPEG, TOOLS, WORKDIR, PROJDIR, PROBEDIR, SHOTDIR, LIB, HOMEDIR, PYTHON, DIR, SECRETS, launch, dismissModals, injectEngine, cookieHeader, sleep, CANVAS_URL, API, TASKS, PROJECT_ID } from './_config.mjs';
/**
 * 把拉回来的旧版文件改成有意义的镜号名
 * 用法: node rename-oldshot.mjs
 */
import fs from 'node:fs';
import path from 'node:path';

const DIR_V = ROOT + '/★剪辑工作台/02-旧视频/逐镜旧版（从OSS拉回）';
const DIR_I = ROOT + '/★剪辑工作台/02-旧视频/逐镜旧图（从OSS拉回）';
const CHANGED = JSON.parse(fs.readFileSync(ROOT + '/_tmp/old-versions.json', 'utf8'));

// 拿当前画布：nodeId → 现在的正式名
const m = await import(PW);
const chromium = m.chromium || m.default?.chromium;
const ctx = await chromium.launchPersistentContext(`${PROBEDIR}/chrome-profile`, {
  headless: true, executablePath: CHROME,
  viewport: { width: 1440, height: 900 }, args: ['--no-sandbox'], locale: 'zh-CN' });
const page = ctx.pages()[0] || await ctx.newPage();
await page.goto('https://www.lingcut.cn/canvas/<ID>', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(9000);
const H = { Cookie: (await ctx.cookies()).map(c => c.name + '=' + c.value).join('; ') };
await page.goto('about:blank'); await page.waitForTimeout(1000);
const r = await fetch('https://www.lingcut.cn/api/projects/<ID>', { headers: H });
const j = await r.json();
const cd = JSON.parse(j.canvas_data || j.project.canvas_data);
const nowName = {};
for (const n of cd.nodes) nowName[n.id] = n.name || '';
await ctx.close();

function safe(s) { return String(s).replace(/[\\/:*?"<>|]/g, '_').replace(/\s+/g, ' ').trim(); }
let renamed = 0, missing = 0;
for (const c of CHANGED) {
  const isV = /\.mp4/.test(c.src);
  const dir = isV ? DIR_V : DIR_I;
  const ext = (c.src.match(/\.(mp4|png|jpe?g|webp)/i) || [, isV ? 'mp4' : 'png'])[1].toLowerCase().replace('jpeg', 'jpg');
  // 旧文件名（按下载时的规则）
  const base = c.key && /^[A-Z]\d\d$/.test(c.key) ? c.key : (c.name || 'x').slice(0, 30);
  const oldFile = path.join(dir, `${safe(base)}_旧_${safe((c.entity || '').slice(0, 24)) || c.why}.${ext}`);
  const cur = nowName[c.id] || c.name || '未知';
  const newFile = path.join(dir, `${safe(cur)}_【旧版】.${ext}`);
  if (fs.existsSync(oldFile)) {
    if (oldFile !== newFile) { try { fs.renameSync(oldFile, newFile); } catch (e) { fs.copyFileSync(oldFile, newFile); fs.unlinkSync(oldFile); } }
    renamed++;
  } else if (fs.existsSync(newFile)) { renamed++; }
  else { missing++; if (missing <= 5) console.log('   ⚠️ 找不到:', path.basename(oldFile)); }
}
console.log(`✅ 重命名 ${renamed} 个，找不到 ${missing} 个`);
console.log('\n旧版视频清单（应与新视频一一对应）:');
const vs = fs.readdirSync(DIR_V).filter(f => f.endsWith('.mp4')).sort();
vs.slice(0, 60).forEach((f, i) => console.log(`   ${String(i + 1).padStart(2)}  ${f}`));
console.log(`   …… 共 ${vs.length} 个`);
const sz = (function walk(x) { let n = 0; for (const f of fs.readdirSync(x)) { const q = path.join(x, f); const st = fs.statSync(q); n += st.isDirectory() ? walk(q) : st.size; } return n; })(DIR_V);
console.log(`   ${(sz / 1048576).toFixed(1)} MB`);
