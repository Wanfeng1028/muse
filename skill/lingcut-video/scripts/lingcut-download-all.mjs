import { PROJ, PW, CHROME, PROFILE, FFMPEG, TOOLS, WORKDIR, PROJDIR, PROBEDIR, SHOTDIR, LIB, HOMEDIR, PYTHON, DIR, SECRETS, launch, dismissModals, injectEngine, cookieHeader, sleep, CANVAS_URL, API, TASKS, PROJECT_ID } from './_config.mjs';
/**
 * 从 LingCut 画布批量下载全部节点的最新出片
 *
 * 输出：★网站最新\视频\  和  ★网站最新\图片\
 * 文件名：序号_单元_镜号_内容.ext   （序号 = 剧情顺序，排序即播放顺序）
 *
 * 用法: node lingcut-download-all.mjs
 */
import fs from 'node:fs';
import path from 'node:path';

const m = await import(PW);
const chromium = m.chromium || m.default?.chromium;

const BASE = `${PROJ}/★网站最新`;
const DIR_V = path.join(BASE, '视频');
const DIR_I = path.join(BASE, '图片');
fs.mkdirSync(DIR_V, { recursive: true });
fs.mkdirSync(DIR_I, { recursive: true });

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
console.log('画布节点:', cd.nodes.length);

// ── 排序键：单元顺序 → 镜号 → 图先于视频 ──────────────
const UNIT_ORDER = ['楔子','第一章','第二章','第三章','第四章','第五章','第六章','第七章','第八章','第九章','第十章',
  '第十一章','第十二章','第十三章','第十四章','第十五章','第十六章','第十七章','第十八章','尾声'];
function parse(name, entityName) {
  const s = (entityName || name || '').trim();
  let mm = s.match(/^\[(角色|场景|道具|机位)\]\s*(.+)$/);
  if (mm) return { cls: 'asset', sub: mm[1], content: mm[2].replace(/\s*·\s*(定板|场景|道具|机位)\s*$/, '').trim() };
  mm = s.match(/^\[([^\]]+?)\s+([A-Z]\d+)\]\s*(.+?)(?:\s*·\s*(图|视频))?$/) || s.match(/^([A-Z]\d+)\s*[-–·]?\s*(.*)$/);
  if (mm) {
    const shot = mm[2] || mm[1];
    const unit = (mm[1] && UNIT_ORDER.includes(mm[1])) ? mm[1] : null;
    return { cls: 'shot', unit, shot, content: (mm[3] || mm[2] || '').replace(/\s*·\s*(图|视频)\s*$/, '').trim() };
  }
  return { cls: 'other', content: s };
}
const LETTER_UNIT = { A:'楔子', B:'第一章', C:'第二章', D:'第三章', E:'第四章', F:'第五章', G:'第六章', H:'第七章',
  I:'第八章', J:'第九章', K:'第十章', L:'第十一章', M:'第十二章', N:'第十三章', O:'第十四章', P:'第十五章',
  Q:'第十六章', R:'第十七章', S:'第十八章', T:'尾声' };

const items = [];
for (const n of cd.nodes) {
  const d = n.data || {};
  const src = d.src || d.selectedSrc || (d.srcs || [])[0] || '';
  if (!src) continue;
  const p = parse(n.name, d.entityName);
  let unit, shot, content;
  if (p.cls === 'asset') { unit = '资产'; shot = ''; content = `${p.sub}·${p.content}`; }
  else if (p.cls === 'shot') { shot = p.shot; unit = p.unit || LETTER_UNIT[(shot || 'X')[0]] || '未归类'; content = p.content; shot = `${unit} ${shot}`; }
  else { unit = '未归类'; shot = ''; content = p.content; }
  const uo = unit === '资产' ? -1 : (UNIT_ORDER.indexOf(unit) >= 0 ? UNIT_ORDER.indexOf(unit) : 800);
  const num = parseInt((shot.match(/([A-Z])(\d+)/) || [])[2] || '0', 10);
  items.push({ node: n, src, isVideo: n.type === 'video', uo, num, isImg: true, unit, shot, content });
}
items.sort((a, b) => a.uo - b.uo || a.num - b.num || (a.isVideo ? 1 : 0) - (b.isVideo ? 1 : 0));

console.log('待下载:', items.length, '（视频', items.filter(x => x.isVideo).length, '/ 图片', items.filter(x => !x.isVideo).length, '）');

// ── 下载（并发 5）──────────────────────────────
function safeName(s) { return String(s).replace(/[\\/:*?"<>|]/g, '_').replace(/\s+/g, ' ').trim(); }
let done = 0, bytes = 0, fail = [];
const seq = { video: 0, image: 0 };
async function dl(it) {
  const key = it.isVideo ? 'video' : 'image';
  seq[key]++;
  const dir = it.isVideo ? DIR_V : DIR_I;
  const ext = (it.src.match(/\.(mp4|png|jpe?g|webp|gif)(?:\?|$)/i) || [null, it.isVideo ? 'mp4' : 'png'])[1].toLowerCase().replace('jpeg', 'jpg');
  const label = it.unit === '资产' ? `000_资产_${it.content}` : `${String(seq[key]).padStart(3, '0')}_${it.shot}${it.content ? '_' + it.content : ''}`;
  const file = path.join(dir, `${safeName(label)}.${ext}`);
  try {
    const res = await fetch(it.src);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const buf = Buffer.from(await res.arrayBuffer());
    fs.writeFileSync(file, buf);
    bytes += buf.length; done++;
    if (done % 25 === 0) console.log(`  已下载 ${done}/${items.length}  (${(bytes / 1048576).toFixed(0)} MB)`);
  } catch (e) { fail.push({ file, err: String(e).slice(0, 60) }); }
}
const CONC = 5;
let idx = 0;
await Promise.all(Array.from({ length: CONC }, async () => {
  while (idx < items.length) { const i = idx++; await dl(items[i]); }
}));

console.log(`\n✅ 下载完成 ${done} / ${items.length}   共 ${(bytes / 1048576).toFixed(1)} MB`);
if (fail.length) { console.log(`❌ 失败 ${fail.length} 个:`); fail.slice(0, 12).forEach(f => console.log('   ', path.basename(f.file), f.err)); }
console.log(`\n  视频 → ${DIR_V}  (${fs.readdirSync(DIR_V).length} 个)`);
console.log(`  图片 → ${DIR_I}  (${fs.readdirSync(DIR_I).length} 个)`);
await ctx.close();
