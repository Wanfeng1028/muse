import { PROJ, PW, CHROME, PROFILE, FFMPEG, TOOLS, WORKDIR, PROJDIR, PROBEDIR, SHOTDIR, LIB, HOMEDIR, PYTHON, DIR, SECRETS, launch, dismissModals, injectEngine, cookieHeader, sleep, CANVAS_URL, API, TASKS, PROJECT_ID } from './_config.mjs';
/**
 * 延长时长 + 补全台词 + 重生成
 * 用法: node lingcut-extend.mjs
 */
import fs from 'node:fs';

const m = await import(PW);
const chromium = m.chromium || m.default?.chromium;

const JOBS = [
  { key: 'B05', dur: '10s', add: '★台词（必须按照写下来的字，一字不差、清楚完整地说出来，用画面上人物自己的声音，不要旁白腔）：老赵先问：「老三又没回来？」然后是——「捎话就行。说家里都好，他媳妇给他生了个闺女，等他回来起名。」然后是——「……他知道就成。」' },
  { key: 'F02', dur: '8s', add: '★台词（必须按顺序一字不差地说出来，用画面上人物自己的声音）：阿婆先问：「先生，你说，我儿子在宗门里，能吃上这样的米吗？」宋先生答：「吃得上。」阿婆笑了：「那就好。」' },
  { key: 'S06', dur: '10s', add: '★台词（必须一字不差、完整说出来，是这位老阿婆自己的声音，苍老的女声，不要旁白腔）：「这碗不要钱。你替我带句话给宋先生——就说，茶棚还在。位置还留着。他要是哪天路过西漠，来喝碗茶。」' },
];

const ctx = await chromium.launchPersistentContext(`${PROBEDIR}/chrome-profile`, {
  headless: true, executablePath: CHROME,
  viewport: { width: 1440, height: 900 }, args: ['--no-sandbox'], locale: 'zh-CN' });
const page = ctx.pages()[0] || await ctx.newPage();
await page.goto('https://www.lingcut.cn/canvas/<ID>', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(13000);
for (let i = 0; i < 4; i++) {
  const hit = await page.evaluate(() => { const b = [...document.querySelectorAll('button')].find(x => /^(开始使用|我知道了|知道了|关闭)$/.test((x.textContent || '').trim())); if (b) { b.click(); return true; } return false; });
  if (!hit) break;
  await page.waitForTimeout(1000);
}
const inj = await page.evaluate(() => {
  const seen = new Set(); let eng = null;
  function walk(o, d) {
    if (!o || d > 8 || seen.has(o) || eng) return;
    try { seen.add(o); } catch (e) { return; }
    try { if (o.nodeMap instanceof Map && typeof o.addNode === 'function') { eng = o; return; } } catch (e) {}
    for (const k of ['stateNode','child','sibling','return','memoizedState','memoizedProps','pendingProps','ref','current']) { try { walk(o[k], d+1); } catch(e){} }
    if (o.memoizedState) { let h=o.memoizedState,n=0; while(h&&n++<60&&!eng){ try{ walk(h.memoizedState,d+1);}catch(e){} h=h.next; } }
  }
  for (const el of [...document.querySelectorAll('*')].slice(0,5000)) { for (const k in el) if (k.startsWith('__react')) walk(el[k],0); if (eng) break; }
  if (eng) { window.__eng = eng; return { ok: true, nodes: eng.nodeMap.size }; }
  return { ok: false };
});
console.log('引擎:', JSON.stringify(inj));
if (!inj.ok) { await ctx.close(); process.exit(1); }

const results = [];
for (let k = 0; k < JOBS.length; k++) {
  const job = JOBS[k];
  if (k > 0) await page.waitForTimeout(15000);
  const info = await page.evaluate(({ key, dur, add }) => {
    const e = window.__eng;
    const n = e.nodes.find(x => x.type === 'video' && new RegExp('\\b' + key + '\\b').test(x.name || ''));
    if (!n) return null;
    let p = (n.data.prompt || '').replace(/★台词[^]*$/, '').trim();
    const np = p + ' ' + add;
    n.data.prompt = np; n.data.duration = dur;
    try { e.updateNodeData(n.id, { prompt: np, duration: dur }, true); } catch (err) {}
    return { id: n.id, name: n.name, oldDur: n.data.duration, len: np.length };
  }, job);
  if (!info) { console.log(`  ${job.key} ❌ 找不到节点`); results.push({ key: job.key, ok: false }); continue; }
  await page.evaluate(id => window.__eng.selectNode(id), info.id);
  await page.waitForTimeout(2300);
  // 设时长下拉
  const durSet = await page.evaluate((want) => {
    const b = [...document.querySelectorAll('button')].find(x => /^\d+s[▼▾]?$/.test((x.textContent || '').trim()));
    if (!b) return 'no-btn';
    if ((b.textContent || '').trim().startsWith(want)) return 'already';
    b.click(); return 'opened';
  }, job.dur);
  if (durSet === 'opened') {
    await page.waitForTimeout(1600);
    const picked = await page.evaluate((want) => {
      const hits = [...document.querySelectorAll('*')].filter(e => e.children.length === 0 && (e.textContent || '').trim() === want && e.getBoundingClientRect().width > 0);
      if (!hits.length) return null; hits[hits.length - 1].click(); return want;
    }, job.dur);
    await page.waitForTimeout(1500);
    console.log(`  ${job.key} 时长 ${info.oldDur} → ${picked || '(选不到)'}`);
  } else console.log(`  ${job.key} 时长下拉: ${durSet}`);
  const wrote = await page.evaluate(({ id }) => {
    const n = window.__eng.nodeMap.get(id);
    const ce = [...document.querySelectorAll('[contenteditable="true"]')].find(x => x.getBoundingClientRect().width > 300);
    if (!ce) return 0;
    ce.focus();
    const s = window.getSelection(), r = document.createRange();
    r.selectNodeContents(ce); s.removeAllRanges(); s.addRange(r);
    document.execCommand('delete', false, null);
    document.execCommand('insertText', false, n.data.prompt);
    return (ce.innerText || '').length;
  }, { id: info.id });
  await page.waitForTimeout(1200);
  const clicked = await page.evaluate(() => {
    const a = [...document.querySelectorAll('button')].find(b => (b.textContent || '').trim() === '↑');
    if (!a) return false; a.click(); return true;
  });
  await page.waitForTimeout(2500);
  console.log(`  ${job.key} ${info.name} 输入${wrote}字 生成=${clicked}`);
  results.push({ key: job.key, id: info.id, name: info.name, ok: clicked });
}
console.log('\n等出片…');
for (let i = 0; i < 80; i++) {
  await page.waitForTimeout(12000);
  const st = await page.evaluate((ids) => ids.map(id => window.__eng.nodeMap.get(id).data.generating), results.filter(r => r.id).map(r => r.id));
  if (i % 4 === 0) console.log(`  [${i * 12}s] 完成 ${st.filter(x => !x).length}/${st.length}`);
  if (st.every(x => !x)) break;
}
const final = await page.evaluate((ids) => ids.map(id => { const d = window.__eng.nodeMap.get(id).data; return { id, src: d.src || '', dur: d.duration, err: d.genError ? String(d.genError).slice(0, 70) : '' }; }), results.filter(r => r.id).map(r => r.id));
const fm = Object.fromEntries(final.map(x => [x.id, x]));
for (const r of results) { if (r.id && fm[r.id]) { r.url = fm[r.id].src; r.dur = fm[r.id].dur; r.err = fm[r.id].err; } }
console.log('\n结果:');
results.forEach(r => console.log(`  ${r.key} dur=${r.dur || '?'} ${r.url ? '✅' : '❌'}  ${r.url || r.err || ''}`));
fs.writeFileSync(ROOT + '/_tmp/fixed-extend.json', JSON.stringify(results, null, 1), 'utf8');
await page.waitForTimeout(12000);
await ctx.close();
