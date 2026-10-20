import { PROJ, PW, CHROME, PROFILE, FFMPEG, TOOLS, WORKDIR, PROJDIR, PROBEDIR, SHOTDIR, LIB, HOMEDIR, PYTHON, DIR, SECRETS, launch, dismissModals, injectEngine, cookieHeader, sleep, CANVAS_URL, API, TASKS, PROJECT_ID } from './_config.mjs';
/**
 * 彻底审计：逐字对照分镜表台词 vs 提示词
 * 输出完整待修清单（含"装不下需拆镜"的标记）
 */
import fs from 'node:fs';
const SB_FILES = [
  `${PROJ}/00-剧本/分镜表v2-楔子与第一卷.md`,
  `${PROJ}/00-剧本/分镜表-第二卷与第三卷.md`,
];

// ── 解析分镜表：拿到每镜的「画面」和「声音」两列 ──
const SB = {};
for (const f of SB_FILES) {
  for (const line of fs.readFileSync(f, 'utf8').split('\n')) {
    const mm = line.match(/^\|\s*\*\*([A-Z]\d+)\*\*\s*\|([^|]*)\|([^|]*)\|([\s\S]+?)\|([^|]*)\|\s*$/);
    if (!mm) continue;
    const [, key, dur, size, scene, sound] = mm;
    SB[key] = {
      dur: parseInt((dur.match(/(\d+)/) || [0, 0])[1], 10),
      size: size.replace(/\s+/g, ' ').trim(),
      scene: scene,
      sound: sound.replace(/\s+/g, ' ').trim(),
    };
  }
}
console.log('分镜表镜头:', Object.keys(SB).length);

// ── 抽台词：画面里所有「」或 ""，排除明显是"画面上的字"的短词 ──
const NOISE = /^(烧酒老号|当柜的|候赎|灯嫂|玉|北原|宋怀玉|怀玉|灯油省着用|见字如面)$/;
function quotes(s) {
  const out = [];
  for (const re of [/[「]([^」]{2,})[」]/g, /"([^"]{2,})"/g, /“([^”]{2,})”/g]) {
    let x; while ((x = re.exec(s))) {
      const q = x[1].replace(/\*\*/g, '').replace(/<br\s*\/?>/g, '').trim();
      if (q && !NOISE.test(q)) out.push(q);
    }
  }
  return [...new Set(out)];
}
function hasDialog(key) { return /对话|对白|喊声|呼喊|喝问/.test(SB[key].sound); }

// ── 拉画布 ──

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
const V = {};
for (const n of cd.nodes) {
  if (n.type !== 'video') continue;
  const mm = (n.name || '').match(/\b([A-Z]\d\d)\b/);
  if (mm) V[mm[1]] = n;
}

// ── 逐镜比对：算"台词覆盖率" ──
const CN = /[\u4e00-\u9fa5]/g;
const need = [], okList = [], noDialog = [];
for (const key of Object.keys(SB).sort()) {
  if (!SB[key] || !V[key]) continue;
  const q = quotes(SB[key].scene);
  if (!q.length || !hasDialog(key)) { noDialog.push(key); continue; }
  const full = q.join('');
  const prompt = (V[key].data && V[key].data.prompt) || '';
  const pChars = new Set((prompt.match(CN) || []));
  const missingChars = (full.match(CN) || []).filter(c => !pChars.has(c));
  const cover = 1 - missingChars.length / Math.max(1, (full.match(CN) || []).length);
  const dur = parseInt((V[key].data.duration || '0').match(/(\d+)/)?.[1] || '0', 10);
  const needSec = (full.match(CN) || []).length / 4.5;
  const rec = { key, dur, chars: (full.match(CN) || []).length, cover: +cover.toFixed(2), needSec: +needSec.toFixed(1), quotes: q, name: V[key].name, split: needSec > dur - 0.5 };
  if (cover < 0.92) need.push(rec); else okList.push(rec);
}
console.log('\n══════ 台词覆盖率审计 ══════');
console.log(`  台词完整 ✅: ${okList.length}`);
console.log(`  台词缺失/不全 ❌: ${need.length}`);
console.log(`  无台词镜（旁白/静场）: ${noDialog.length}`);
console.log('\n══════ 待修清单 ══════');
const unitOf = k => ({A:'楔子',B:'一·1章',C:'一·2章',D:'一·3章',E:'一·4章',F:'一·5章',G:'二·6章',H:'二·7章',I:'二·8章',J:'二·9章',K:'二·10章',L:'二·11章',M:'二·12章',N:'二·13章',O:'三·14章',P:'三·15章',Q:'三·16章',R:'三·17章',S:'三·18章',T:'尾声'})[k[0]];
let splitCnt = 0;
for (const x of need.sort((a, b) => a.key.localeCompare(b.key))) {
  const flag = x.split ? ' ★需拆镜' : '';
  if (x.split) splitCnt++;
  console.log(`  ${x.key} [${unitOf(x.key)}] dur=${x.dur}s 台词${x.chars}字(需${x.needSec}s) 覆盖${(x.cover*100).toFixed(0)}%${flag}`);
  console.log(`       ${x.quotes.join(' ／ ').slice(0, 110)}`);
}
console.log(`\n  合计 ${need.length} 镜待修，其中 ${splitCnt} 镜需要拆镜`);
fs.writeFileSync(`${PROJ}/_tmp/todo-full.json`, JSON.stringify(need, null, 1), 'utf8');
console.log('  清单已存 _tmp/todo-full.json');
await ctx.close();
