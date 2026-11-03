import { PROJ, PW, CHROME, PROFILE, FFMPEG, TOOLS, WORKDIR, PROJDIR, PROBEDIR, SHOTDIR, LIB, HOMEDIR, PYTHON, DIR, SECRETS, launch, dismissModals, injectEngine, cookieHeader, sleep, CANVAS_URL, API, TASKS, PROJECT_ID } from './_config.mjs';
/**
 * 通用：重生成指定镜号的视频
 * 用法: node lingcut-regen.mjs KEY1,KEY2,... [--setprompt <json文件>]
 *
 * _tmp/retry-keys.json 可放 {KEY: "追加到提示词的文本"} 的映射
 */
import fs from 'node:fs';

const m = await import(PW);
const chromium = m.chromium || m.default?.chromium;

const keysArg = process.argv[2] || '';
const KEYS = keysArg.split(',').map(s => s.trim()).filter(Boolean);
// 可选：每镜追加/替换提示词的文本
let APPEND = {};
const apFile = ROOT + '/_tmp/retry-append.json';
try { APPEND = JSON.parse(fs.readFileSync(apFile, 'utf8')); } catch (e) {}
console.log('待重生成:', KEYS.join(' '));
if (Object.keys(APPEND).length) console.log('带提示词调整:', Object.keys(APPEND).join(' '));

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

// 若有提示词调整，先写入数据
if (Object.keys(APPEND).length) {
  const r = await page.evaluate((ap) => {
    const e = window.__eng; const out = [];
    for (const [key, txt] of Object.entries(ap)) {
      const n = e.nodes.find(x => x.type === 'video' && new RegExp('\\b' + key + '\\b').test(x.name || ''));
      if (!n) { out.push({ key, ok: false }); continue; }
      let p = (n.data.prompt || '').replace(/★台词[^]*$/, '').trim();
      const np = p + ' ' + txt;
      n.data.prompt = np;
      try { e.updateNodeData(n.id, { prompt: np }, true); } catch (err) {}
      out.push({ key, ok: true, len: np.length });
    }
    return out;
  }, APPEND);
  r.forEach(x => console.log(`  提示词调整 ${x.key} ${x.ok ? '✅ ' + x.len + '字' : '❌'}`));
}

const results = [];
for (let k = 0; k < KEYS.length; k++) {
  const key = KEYS[k];
  if (k > 0) await page.waitForTimeout(15000);
  const n = await page.evaluate((key) => {
    const e = window.__eng;
    const x = e.nodes.find(y => y.type === 'video' && new RegExp('\\b' + key + '\\b').test(y.name || ''));
    return x ? { id: x.id, name: x.name, dur: x.data.duration } : null;
  }, key);
  if (!n) { console.log(`  ${key} ❌ 找不到节点`); results.push({ key, ok: false }); continue; }
  await page.evaluate(id => window.__eng.selectNode(id), n.id);
  await page.waitForTimeout(2200);
  const p = await page.evaluate(id => window.__eng.nodeMap.get(id).data.prompt, n.id);
  const wrote = await page.evaluate(({ p }) => {
    const ce = [...document.querySelectorAll('[contenteditable="true"]')].find(x => x.getBoundingClientRect().width > 300);
    if (!ce) return 0;
    ce.focus();
    const s = window.getSelection(), r = document.createRange();
    r.selectNodeContents(ce); s.removeAllRanges(); s.addRange(r);
    document.execCommand('delete', false, null);
    document.execCommand('insertText', false, p);
    return (ce.innerText || '').length;
  }, { p });
  await page.waitForTimeout(1200);
  const clicked = await page.evaluate(() => {
    const a = [...document.querySelectorAll('button')].find(b => (b.textContent || '').trim() === '↑');
    if (!a) return false; a.click(); return true;
  });
  await page.waitForTimeout(2500);
  console.log(`  ${key} ${n.name} dur=${n.dur} 输入${wrote}字 生成=${clicked}`);
  results.push({ key, id: n.id, name: n.name, ok: clicked });
}
console.log('\n等出片…');
for (let i = 0; i < 90; i++) {
  await page.waitForTimeout(12000);
  const st = await page.evaluate((ids) => ids.map(id => window.__eng.nodeMap.get(id).data.generating), results.filter(r => r.id).map(r => r.id));
  if (i % 4 === 0) console.log(`  [${i * 12}s] 完成 ${st.filter(x => !x).length}/${st.length}`);
  if (st.every(x => !x)) break;
}
const final = await page.evaluate((ids) => ids.map(id => { const d = window.__eng.nodeMap.get(id).data; return { id, src: d.src || '', err: d.genError ? String(d.genError).slice(0, 70) : '' }; }), results.filter(r => r.id).map(r => r.id));
const fm = Object.fromEntries(final.map(x => [x.id, x]));
for (const r of results) { if (r.id && fm[r.id]) { r.url = fm[r.id].src; r.err = fm[r.id].err; } }
console.log('\n结果:');
results.forEach(r => console.log(`  ${r.key} ${r.url ? '✅' : '❌'}  ${r.url || r.err || ''}`));
fs.writeFileSync(ROOT + '/_tmp/regen-' + KEYS.join('-') + '.json', JSON.stringify(results, null, 1), 'utf8');
await page.waitForTimeout(12000);
await ctx.close();
