import { PROJ, PW, CHROME, PROFILE, FFMPEG, TOOLS, WORKDIR, PROJDIR, PROBEDIR, SHOTDIR, LIB, HOMEDIR, PYTHON, DIR, SECRETS, launch, dismissModals, injectEngine, cookieHeader, sleep, CANVAS_URL, API, TASKS, PROJECT_ID } from './_config.mjs';
/**
 * 批量补台词并重生成（用引擎改，避免被自动保存覆盖）
 *
 * 用法: node lingcut-fix-dialog.mjs [startIdx] [count]
 *   例: node lingcut-fix-dialog.mjs 0 6     只做待修清单里的第 0~5 个
 *
 * 清单: _tmp/todo-dialog.json
 * 输出: _tmp/fixed-dialog.json （含每个镜头的新 OSS 地址，供后续下载替换）
 */
import fs from 'node:fs';

const m = await import(PW);
const chromium = m.chromium || m.default?.chromium;

const TODO = JSON.parse(fs.readFileSync(ROOT + '/_tmp/todo-dialog.json', 'utf8'));
const FROM = parseInt(process.argv[2] || '0', 10);
const CNT = parseInt(process.argv[3] || String(TODO.length), 10);
const JOBS = TODO.slice(FROM, FROM + CNT);
console.log(`待修共 ${TODO.length} 个，本批处理 ${FROM}~${FROM + JOBS.length - 1}（${JOBS.length} 个）`);
JOBS.forEach(j => console.log(`   ${j.key} ${j.name}  dur=${j.dur}  +${j.need.join('').length}字`));

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
  if (k > 0) await page.waitForTimeout(14000);   // 节流
  // 找到该镜号的视频节点
  const found = await page.evaluate((key) => {
    const e = window.__eng;
    const n = e.nodes.find(x => x.type === 'video' && new RegExp('\\b' + key + '\\b').test(x.name || ''));
    if (!n) return null;
    return { id: n.id, name: n.name, dur: n.data.duration, prompt: n.data.prompt || '' };
  }, job.key);
  if (!found) { console.log(`\n${job.key} ❌ 画布上没找到视频节点`); results.push({ key: job.key, ok: false, why: 'no-node' }); continue; }

  // 追加台词（带声音方向提示）
  const patch = await page.evaluate(({ id, need }) => {
    const e = window.__eng, n = e.nodeMap.get(id);
    let p = n.data.prompt || '';
    // 去掉之前可能加过的
    p = p.replace(/★台词[^]*$/, '').trim();
    const line = '★台词（必须按照写下来的字，一字不差、清楚完整地说出来；用画面上这个人物自己的声音和语气，不要用旁白腔、不要念稿）：' +
      need.map(x => '「' + x + '」').join('  然后是——  ');
    const np = p + ' ' + line;
    n.data.prompt = np;
    try { e.updateNodeData(id, { prompt: np }, true); } catch (err) {}
    return { id: n.id, name: n.name, dur: n.data.duration, len: np.length };
  }, { id: found.id, need: job.need });
  console.log(`\n${job.key}  ${patch.name}  dur=${patch.dur}  提示词 ${patch.len} 字`);

  await page.evaluate(id => window.__eng.selectNode(id), found.id);
  await page.waitForTimeout(2200);
  const wrote = await page.evaluate((id) => {
    const e = window.__eng, n = e.nodeMap.get(id);
    const ce = [...document.querySelectorAll('[contenteditable="true"]')].find(x => x.getBoundingClientRect().width > 300);
    if (!ce) return 0;
    ce.focus();
    const s = window.getSelection(), r = document.createRange();
    r.selectNodeContents(ce); s.removeAllRanges(); s.addRange(r);
    document.execCommand('delete', false, null);
    document.execCommand('insertText', false, n.data.prompt);
    return (ce.innerText || '').length;
  }, found.id);
  await page.waitForTimeout(1200);
  const clicked = await page.evaluate(() => {
    const a = [...document.querySelectorAll('button')].find(b => (b.textContent || '').trim() === '↑');
    if (!a) return 'no-arrow'; a.click(); return 'clicked';
  });
  console.log(`  输入框 ${wrote} 字, 生成 ${clicked}`);
  await page.waitForTimeout(2500);
  results.push({ key: job.key, id: found.id, name: found.name, ok: clicked === 'clicked' });
}
// 等全部出片
console.log('\n等待出片…');
for (let i = 0; i < 80; i++) {
  await page.waitForTimeout(12000);
  const st = await page.evaluate((ids) => ids.map(id => { const d = window.__eng.nodeMap.get(id).data; return { id, gen: d.generating, src: d.src || '', err: d.genError || '' }; }), results.filter(r => r.id).map(r => r.id));
  const done = st.filter(s => !s.gen).length;
  if (i % 4 === 0) console.log(`  [${i * 12}s] 完成 ${done}/${st.length}`);
  if (st.every(s => !s.gen)) break;
}
const urls = await page.evaluate((ids) => ids.map(id => { const d = window.__eng.nodeMap.get(id).data; return { id, src: d.src || '', err: d.genError ? String(d.genError).slice(0, 70) : '' }; }), results.filter(r => r.id).map(r => r.id));
const um = Object.fromEntries(urls.map(u => [u.id, u]));
for (const r of results) { if (r.id && um[r.id]) { r.url = um[r.id].src; r.err = um[r.id].err; } }
console.log('\n结果:');
results.forEach(r => console.log(`  ${r.key} ${r.ok ? '✅' : '❌'}  ${r.url || r.err || '(无)'}`));
const outFile = ROOT + '/_tmp/fixed-dialog.json';
let prev = [];
try { prev = JSON.parse(fs.readFileSync(outFile, 'utf8')); } catch (e) {}
const merged = prev.filter(p => !results.some(r => r.key === p.key)).concat(results);
fs.writeFileSync(outFile, JSON.stringify(merged, null, 1), 'utf8');
console.log(`\n已写入 ${outFile}（累计 ${merged.length} 条）`);
await page.waitForTimeout(12000);
await ctx.close();
