import { PROJ, PW, CHROME, PROFILE, FFMPEG, TOOLS, WORKDIR, PROJDIR, PROBEDIR, SHOTDIR, LIB, HOMEDIR, PYTHON, DIR, SECRETS, launch, dismissModals, injectEngine, cookieHeader, sleep, CANVAS_URL, API, TASKS, PROJECT_ID } from './_config.mjs';
/**
 * 通用「尾帧接续」拆镜器
 * 用法: node lingcut-split.mjs <KEY> <前半json> <后半json>
 *
 * 输入 json 文件格式: { "promptA": "...", "promptB": "...", "durA": "12s", "durB": "8s", "nameB": "..." }
 * 流程: A(生成) → 抽尾帧 → 上传 → B(以尾帧为首帧) → 拼接
 */
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';

const m = await import(PW);
const chromium = m.chromium || m.default?.chromium;

const FF = FFMPEG;

const KEY = process.argv[2];
const CFG = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
console.log(`拆镜 ${KEY}: 前半 ${CFG.durA} + 后半 ${CFG.durB}`);

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

async function genNode(id, prompt, dur) {
  await page.evaluate(({ id, prompt, dur }) => {
    const e = window.__eng, n = e.nodeMap.get(id);
    n.data.prompt = prompt; if (dur) n.data.duration = dur;
    try { e.updateNodeData(id, { prompt, ...(dur ? { duration: dur } : {}) }, true); } catch (err) {}
  }, { id, prompt, dur });
  await page.evaluate(id => window.__eng.selectNode(id), id);
  await page.waitForTimeout(2300);
  if (dur) {
    const b = await page.evaluate((want) => {
      const x = [...document.querySelectorAll('button')].find(y => /^\d+s[▼▾]?$/.test((y.textContent || '').trim()));
      if (!x) return 'no-btn';
      if ((x.textContent || '').trim().startsWith(want)) return 'already';
      x.click(); return 'opened';
    }, dur);
    if (b === 'opened') {
      await page.waitForTimeout(1600);
      await page.evaluate((want) => {
        const h = [...document.querySelectorAll('*')].filter(e => e.children.length === 0 && (e.textContent || '').trim() === want && e.getBoundingClientRect().width > 0);
        if (h.length) h[h.length - 1].click();
      }, dur);
      await page.waitForTimeout(1500);
    }
  }
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
  return { wrote, clicked };
}
async function waitDone(ids) {
  for (let i = 0; i < 80; i++) {
    await page.waitForTimeout(12000);
    const st = await page.evaluate((ids) => ids.map(id => { const d = window.__eng.nodeMap.get(id).data; return { gen: d.generating, src: d.src || '', err: d.genError || '', dur: d.duration }; }), ids);
    if (i % 4 === 0) console.log(`   [${i * 12}s] ` + st.map(s => s.gen ? '…' : (s.src ? '✓' : '✗')).join(''));
    if (st.every(s => !s.gen)) return st;
  }
  return null;
}

// ① 找 A 节点
const A = await page.evaluate((key) => {
  const n = window.__eng.nodes.find(x => x.type === 'video' && new RegExp('\\b' + key + '\\b').test(x.name || ''));
  return n ? { id: n.id, name: n.name } : null;
}, KEY);
if (!A) { console.log('❌ 找不到 ' + KEY); await ctx.close(); process.exit(1); }
console.log('前半节点:', A.name, A.id.replace('p3535_', ''));

// ② 生成前半
const ga = await genNode(A.id, CFG.promptA, CFG.durA);
console.log('前半 输入', ga.wrote, '字 生成=', ga.clicked);
let st = await waitDone([A.id]);
if (!st || !st[0].src) { console.log('❌ 前半失败', JSON.stringify(st)); await ctx.close(); process.exit(1); }
console.log('前半 ✅', st[0].src);
const aFile = ROOT + '/_tmp/' + KEY + '-A.mp4';
fs.writeFileSync(aFile, Buffer.from(await (await fetch(st[0].src)).arrayBuffer()));
const tailPng = ROOT + '/_tmp/' + KEY + '-tail.png';
execFileSync(FF, ['-hide_banner','-loglevel','error','-y','-sseof','-0.15','-i',aFile,'-frames:v','1','-update','1',tailPng], { stdio: 'inherit' });
console.log('尾帧:', fs.statSync(tailPng).size, 'bytes');

// ③ 建 B 节点 + 尾帧图
const ids = await page.evaluate(({ key, nameB }) => {
  const e = window.__eng;
  const vid = e.addNode('video', -3600, -5400);
  const img = e.addNode('image', -4200, -5400);
  e.updateNodeData(vid, { name: nameB, entityType: 'shot', entityName: key + 'b', model: 'lingcut', aspectRatio: '16:9', duration: '8s', prompt: '' });
  e.updateNodeData(img, { name: '[参考] ' + key + ' 尾帧', entityType: 'prop', entityName: key + '尾帧', model: 'gpt-image-2.5', aspectRatio: '16:9', resolution: '1K', count: '1', prompt: key + ' 前半的尾帧，作为后半段的首帧参考' });
  try { e.addConnection(img, vid); } catch (err) {}
  e.forceUpdate && e.forceUpdate();
  return { vid, img };
}, { key: KEY, nameB: CFG.nameB || (KEY + 'b 续') });
console.log('后半节点:', ids.vid.replace('p3535_', ''), ' 尾帧图:', ids.img.replace('p3535_', ''));
await page.waitForTimeout(2500);
await page.evaluate(id => window.__eng.selectNode(id), ids.img);
await page.waitForTimeout(2500);
const all = await page.$$('input[type=file]');
let up = false;
for (const h of all) { const acc = await h.getAttribute('accept'); if (acc && /image|png/.test(acc)) { await h.setInputFiles(tailPng); up = true; break; } }
if (!up && all.length) { await all[0].setInputFiles(tailPng); up = true; }
console.log('尾帧上传:', up ? '✅' : '❌');
await page.waitForTimeout(9000);
console.log('尾帧图 src:', (await page.evaluate(id => window.__eng.nodeMap.get(id).data.src || '', ids.img)).slice(-36));

// ④ 生成后半
const gb = await genNode(ids.vid, CFG.promptB, CFG.durB);
console.log('后半 输入', gb.wrote, '字 生成=', gb.clicked);
st = await waitDone([ids.vid]);
if (!st || !st[0].src) { console.log('❌ 后半失败', JSON.stringify(st)); await ctx.close(); process.exit(1); }
console.log('后半 ✅', st[0].src);
const bFile = ROOT + '/_tmp/' + KEY + '-B.mp4';
fs.writeFileSync(bFile, Buffer.from(await (await fetch(st[0].src)).arrayBuffer()));

// ⑤ 拼接
const nA = ROOT + '/_tmp/' + KEY + '-A-n.mp4', nB = ROOT + '/_tmp/' + KEY + '-B-n.mp4';
for (const [s, d] of [[aFile, nA], [bFile, nB]]) {
  execFileSync(FF, ['-hide_banner','-loglevel','error','-y','-fflags','+genpts','-avoid_negative_ts','make_zero','-i',s,'-c:v','libx264','-preset','veryfast','-crf','20','-r','24','-vf','scale=1280:720','-pix_fmt','yuv420p','-c:a','aac','-ar','32000','-ac','2',d], { stdio: 'inherit' });
}
const list = ROOT + '/_tmp/' + KEY + '-list.txt';
fs.writeFileSync(list, `file '${nA.replace(/\\/g,'/')}'\nfile '${nB.replace(/\\/g,'/')}'\n`, 'utf8');
const out = ROOT + '/_tmp/' + KEY + '-split.mp4';
execFileSync(FF, ['-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',list,'-c','copy',out], { stdio: 'inherit' });
console.log('✅ 拼接完成:', out, fs.statSync(out).size, 'bytes');
fs.writeFileSync(ROOT + '/_tmp/' + KEY + '-split.json', JSON.stringify({ key: KEY, a: st[0].src, out }, null, 1), 'utf8');
// 替换本地
const targets = [
  ROOT + '/12-v2新视频/' + KEY + '-*.mp4',
  ROOT + '/★网站最新/视频/*' + KEY + '*.mp4',
];
const { globSync } = await import('node:fs');
for (const pat of targets) {
  const dir = pat.substring(0, pat.lastIndexOf('/'));
  const pre = pat.substring(pat.lastIndexOf('/') + 1).replace('*', '');
  if (!fs.existsSync(dir)) continue;
  for (const f of fs.readdirSync(dir)) {
    if (pre && !f.includes(pre.replace('.mp4', ''))) continue;
    if (!f.endsWith('.mp4')) continue;
    fs.copyFileSync(out, dir + '/' + f);
    console.log('   已替换:', f);
  }
}
await page.waitForTimeout(10000);
await ctx.close();
