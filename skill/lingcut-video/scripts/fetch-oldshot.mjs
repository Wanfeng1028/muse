import { PROJ, PW, CHROME, PROFILE, FFMPEG, TOOLS, WORKDIR, PROJDIR, PROBEDIR, SHOTDIR, LIB, HOMEDIR, PYTHON, DIR, SECRETS, launch, dismissModals, injectEngine, cookieHeader, sleep, CANVAS_URL, API, TASKS, PROJECT_ID } from './_config.mjs';
/**
 * 从 OSS 拉回旧版本镜头
 *  用 _tmp/canvas.json（10-02 19:51 快照 = 第一次交付时的状态）
 *  对比当前画布，找出 src 变了的节点，下载旧版
 *
 * 用法: node fetch-oldshot.mjs [--all]
 */
import fs from 'node:fs';
import path from 'node:path';

const OLD_CANVAS = ROOT + '/_tmp/canvas.json';
const OUT_V = ROOT + '/★剪辑工作台/02-旧视频/逐镜旧版（从OSS拉回）';
const OUT_I = ROOT + '/★剪辑工作台/02-旧视频/逐镜旧图（从OSS拉回）';
fs.mkdirSync(OUT_V, { recursive: true });
fs.mkdirSync(OUT_I, { recursive: true });

// ── ① 旧画布 ────────────────────────────────────
const raw = JSON.parse(fs.readFileSync(OLD_CANVAS, 'utf8'));
const oldCd = raw.canvas_data ? JSON.parse(raw.canvas_data) : (raw.nodes ? raw : (raw.project ? JSON.parse(raw.project.canvas_data) : null));
if (!oldCd || !oldCd.nodes) { console.log('❌ 旧画布解析失败, keys:', Object.keys(raw).slice(0, 10)); process.exit(1); }
console.log('旧画布节点:', oldCd.nodes.length, '(快照时间 10-02 19:51)');
const oldMap = {};
for (const n of oldCd.nodes) {
  const d = n.data || {};
  const src = d.src || d.selectedSrc || (d.srcs || [])[0] || '';
  const key = ((n.name || '').match(/\b([A-Z]\d\d)\b/) || [])[1] || (d.entityName || n.name || '');
  oldMap[n.id] = { name: n.name, src, type: n.type, key, entity: d.entityName || '' };
}

// ── ② 当前画布 ──────────────────────────────────
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
const newCd = JSON.parse(j.canvas_data || j.project.canvas_data);
const newMap = {};
for (const n of newCd.nodes) {
  const d = n.data || {};
  newMap[n.id] = { name: n.name, src: d.src || (d.srcs || [])[0] || '', type: n.type };
}
await ctx.close();
console.log('当前画布节点:', newCd.nodes.length);

// ── ③ 找出 src 变了的 ───────────────────────────
const changed = [];
for (const [id, o] of Object.entries(oldMap)) {
  if (!o.src) continue;
  const nn = newMap[id];
  if (!nn) { changed.push({ ...o, id, why: '节点已删' }); continue; }
  if (nn.src !== o.src) changed.push({ ...o, id, now: nn.src, why: '已重新生成' });
}
console.log('\n★ src 变了的节点:', changed.length, '个');
const stat = { video: 0, image: 0, other: 0 };
changed.forEach(c => { if (/\.mp4/.test(c.src)) stat.video++; else if (/\.(png|jpg|jpeg|webp)/.test(c.src)) stat.image++; else stat.other++; });
console.log('   其中视频', stat.video, '/ 图片', stat.image, '/ 其它', stat.other);
console.log('\n清单（前 40 个）:');
changed.slice(0, 40).forEach(c => console.log(`   ${c.type === 'video' ? '视频' : '图 '} ${(c.name || '').slice(0, 34).padEnd(36)} ${c.why}`));

// ── ④ 下载 ──────────────────────────────────────
console.log('\n═══ 下载旧版 ═══');
function safe(s) { return String(s).replace(/[\\/:*?"<>|]/g, '_').replace(/\s+/g, ' ').trim(); }
let ok = 0, fail = 0, bytes = 0;
const CONC = 6;
let idx = 0;
async function dl(c) {
  const isV = /\.mp4/.test(c.src);
  const dir = isV ? OUT_V : OUT_I;
  const ext = (c.src.match(/\.(mp4|png|jpe?g|webp)/i) || [, isV ? 'mp4' : 'png'])[1].toLowerCase().replace('jpeg', 'jpg');
  const base = c.key && /^[A-Z]\d\d$/.test(c.key) ? c.key : (c.name || 'x').slice(0, 30);
  const file = path.join(dir, `${safe(base)}_旧_${safe((c.entity || '').slice(0, 24)) || c.why}.${ext}`);
  if (fs.existsSync(file)) { ok++; return; }
  try {
    const res = await fetch(c.src);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const buf = Buffer.from(await res.arrayBuffer());
    if (buf.length < 500) throw new Error('文件太小 ' + buf.length);
    fs.writeFileSync(file, buf);
    bytes += buf.length; ok++;
    if (ok % 20 === 0) console.log(`   已下载 ${ok}/${changed.length}  (${(bytes / 1048576).toFixed(0)} MB)`);
  } catch (e) { fail++; if (fail <= 6) console.log(`   ❌ ${path.basename(file)}  ${String(e).slice(0, 50)}`); }
}
await Promise.all(Array.from({ length: CONC }, async () => { while (idx < changed.length) { const i = idx++; await dl(changed[i]); } }));
console.log(`\n✅ 下载完成 ${ok}/${changed.length}   共 ${(bytes / 1048576).toFixed(1)} MB   失败 ${fail}`);
console.log(`   视频 → ${OUT_V}`);
console.log(`   图片 → ${OUT_I}`);
fs.writeFileSync(ROOT + '/_tmp/old-versions.json', JSON.stringify(changed, null, 1), 'utf8');
console.log('   清单已存 _tmp/old-versions.json');
