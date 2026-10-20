import { PROJ, PW, CHROME, PROFILE, FFMPEG, TOOLS, WORKDIR, PROJDIR, PROBEDIR, SHOTDIR, LIB, HOMEDIR, PYTHON, DIR, SECRETS, launch, dismissModals, injectEngine, cookieHeader, sleep, CANVAS_URL, API, TASKS, PROJECT_ID } from './_config.mjs';
/**
 * 通用：把指定新图接到指定镜头的视频节点，重生成并替换本地
 *
 * 用法: node lingcut-swapimg.mjs <mapping.json>
 *   mapping.json: [{ "key": "K02", "img": "p<ID>_n8096", "nameRe": "二·10章 K02 ", "wantDur": "8s", "addPrompt": "..." }, ...]
 */
import fs from 'node:fs';

const m = await import(PW);
const chromium = m.chromium || m.default?.chromium;

const MAPFILE = process.argv[2];
const JOBS = JSON.parse(fs.readFileSync(MAPFILE, 'utf8'));
console.log('待换图重生成:', JOBS.map(j => j.key).join(' '));

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

// ① 重接线 + 调提示词/时长
const wired = await page.evaluate((jobs) => {
  const e = window.__eng; const out = [];
  for (const j of jobs) {
    const re = new RegExp(j.nameRe);
    const v = e.nodes.find(x => x.type === 'video' && re.test(x.name || ''));
    if (!v) { out.push({ ...j, ok: false, why: 'no-video' }); continue; }
    const srcs = (e.connections || []).filter(c => c.targetId === v.id).map(c => c.sourceId);
    for (const s of srcs) { try { e.removeConnectionBetween(s, v.id); } catch (err) {} }
    if (j.img) { try { e.addConnection(j.img, v.id); } catch (err) {} }
    let np = v.data.prompt || '';
    if (j.addPrompt) { np = np.replace(/★台词[^]*$/, '').trim() + ' ' + j.addPrompt; }
    const upd = { prompt: np };
    if (j.wantDur) upd.duration = j.wantDur;
    v.data.prompt = np; if (j.wantDur) v.data.duration = j.wantDur;
    try { e.updateNodeData(v.id, upd, true); } catch (err) {}
    out.push({ ...j, ok: true, videoId: v.id, name: v.name, dur: v.data.duration, dropped: srcs.length });
  }
  try { e.forceUpdate && e.forceUpdate(); } catch (err) {}
  return out;
}, JOBS);
console.log('重接线:');
wired.forEach(w => console.log(`   ${w.key} ${w.ok ? '✅ ' + w.name + ' dur=' + w.dur + ' (断开' + w.dropped + '条)' : '❌ ' + w.why}`));
await page.waitForTimeout(2500);

// ② 生成
const jobs = wired.filter(w => w.ok);
for (let k = 0; k < jobs.length; k++) {
  if (k > 0) await page.waitForTimeout(14000);
  const j = jobs[k];
  await page.evaluate(id => window.__eng.selectNode(id), j.videoId);
  await page.waitForTimeout(2300);
  if (j.wantDur) {
    const b = await page.evaluate((want) => {
      const x = [...document.querySelectorAll('button')].find(y => /^\d+s[▼▾]?$/.test((y.textContent || '').trim()));
      if (!x) return 'no-btn';
      if ((x.textContent || '').trim().startsWith(want)) return 'already';
      x.click(); return 'opened';
    }, j.wantDur);
    if (b === 'opened') {
      await page.waitForTimeout(1600);
      await page.evaluate((want) => {
        const h = [...document.querySelectorAll('*')].filter(e => e.children.length === 0 && (e.textContent || '').trim() === want && e.getBoundingClientRect().width > 0);
        if (h.length) h[h.length - 1].click();
      }, j.wantDur);
      await page.waitForTimeout(1500);
    }
  }
  const prompt = await page.evaluate(id => window.__eng.nodeMap.get(id).data.prompt, j.videoId);
  const wrote = await page.evaluate(({ prompt }) => {
    const ce = [...document.querySelectorAll('[contenteditable="true"]')].find(x => x.getBoundingClientRect().width > 300);
    if (!ce) return 0;
    ce.focus();
    const s = window.getSelection(), r = document.createRange();
    r.selectNodeContents(ce); s.removeAllRanges(); s.addRange(r);
    document.execCommand('delete', false, null);
    document.execCommand('insertText', false, prompt);
    return (ce.innerText || '').length;
  }, { prompt });
  await page.waitForTimeout(1200);
  const clicked = await page.evaluate(() => {
    const a = [...document.querySelectorAll('button')].find(b => (b.textContent || '').trim() === '↑');
    if (!a) return false; a.click(); return true;
  });
  await page.waitForTimeout(2500);
  console.log(`   ${j.key} 输入${wrote}字 生成=${clicked}`);
}
console.log('\n等出片…');
for (let i = 0; i < 80; i++) {
  await page.waitForTimeout(12000);
  const st = await page.evaluate((ids) => ids.map(id => window.__eng.nodeMap.get(id).data.generating), jobs.map(j => j.videoId));
  if (i % 4 === 0) console.log(`   [${i * 12}s] 完成 ${st.filter(x => !x).length}/${st.length}`);
  if (st.every(x => !x)) break;
}
const final = await page.evaluate((ids) => ids.map(id => { const d = window.__eng.nodeMap.get(id).data; return { id, src: d.src || '', err: d.genError ? String(d.genError).slice(0,60) : '' }; }), jobs.map(j => j.videoId));
const fm = Object.fromEntries(final.map(x => [x.id, x]));
console.log('\n结果:');
for (const j of jobs) { j.url = (fm[j.videoId] || {}).src; j.err = (fm[j.videoId] || {}).err; console.log(`   ${j.key} ${j.url ? '✅ ' + j.url : '❌ ' + (j.err || '')}`); }
fs.writeFileSync(ROOT + '/_tmp/swapimg-' + JOBS.map(j => j.key).join('-') + '.json', JSON.stringify(jobs, null, 1), 'utf8');

// ③ 替换本地
for (const j of jobs) {
  if (!j.url) continue;
  const buf = Buffer.from(await (await fetch(j.url)).arrayBuffer());
  for (const dir of ['20-三卷视频', '17-二卷视频', '12-v2新视频', '★网站最新/视频']) {
    const full = ROOT + '/' + dir;
    if (!fs.existsSync(full)) continue;
    for (const f of fs.readdirSync(full)) {
      if (new RegExp('\\b' + j.key + '\\b').test(f) && f.endsWith('.mp4')) {
        fs.writeFileSync(full + '/' + f, buf);
        console.log('   已替换:', dir + '/' + f);
      }
    }
  }
}
await page.waitForTimeout(10000);
await ctx.close();
