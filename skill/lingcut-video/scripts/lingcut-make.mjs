import { PROJ, PW, CHROME, PROFILE, FFMPEG, TOOLS, WORKDIR, PROJDIR, PROBEDIR, SHOTDIR, LIB, HOMEDIR, PYTHON, DIR, SECRETS, launch, dismissModals, injectEngine, cookieHeader, sleep, CANVAS_URL, API, TASKS, PROJECT_ID } from './_config.mjs';
/**
 * 建节点 + 命名（走 startRename 持久化）+ 上传素材 + 生成。
 * 用法:
 *   node lingcut-make.mjs new <image|video> "<名称>" <x> <y>
 *   node lingcut-make.mjs upload <nodeId> <文件>
 *   node lingcut-make.mjs rename <nodeId> "<名称>"
 *   node lingcut-make.mjs gen <refId|none> <genId> <modelKey> <时长> <promptFile> [RUN]
 */
import { readFileSync, existsSync } from 'node:fs';

const m = await import(PW);
const chromium = m.chromium || m.default?.chromium;

const SHOTS = SHOTDIR;
const [mode, A, B, C, D, E, F] = process.argv.slice(2);
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

const ctx = await chromium.launchPersistentContext(`${PROBEDIR}/chrome-profile`, {
  headless: true, executablePath: CHROME, viewport: { width: 1440, height: 900 }, args: ['--no-sandbox'], locale: 'zh-CN',
});
const page = ctx.pages()[0] || await ctx.newPage();
page.setDefaultTimeout(20000);
await page.goto('https://www.lingcut.cn/canvas/<ID>', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(10000);
for (let i = 0; i < 4; i++) { await page.evaluate(() => { const b = [...document.querySelectorAll('button')].find(x => /^(开始使用|我知道了)$/.test((x.textContent || '').trim())); if (b) b.click(); }); await page.waitForTimeout(900); }

const INJECT = `(() => {
  if (window.__lc && window.__lc.eng) return 'cached';
  const cv = document.querySelector('canvas.leafer-canvas-view'); if (!cv) return 'no-canvas';
  const isEngine = o => o && typeof o === 'object' && o.nodeMap instanceof Map && typeof o.addNode === 'function';
  let found=null; const seen=new Set();
  const scan=(o,d)=>{ if(found||!o||d>6||typeof o!=='object'||seen.has(o))return; seen.add(o);
    try{ if(isEngine(o)){found=o;return;} }catch(e){}
    let ks=[]; try{ks=Object.keys(o)}catch(e){return}
    for(const k of ks){ if(k==='return'||k==='child'||k==='sibling'||k==='_owner')continue; let v; try{v=o[k]}catch(e){continue}
      if(v&&typeof v==='object')scan(v,d+1); } };
  for(const el of cv.ownerDocument.querySelectorAll('*')){
    const key=Object.keys(el).find(x=>x.startsWith('__reactContainer$')||x.startsWith('__reactFiber$'));
    if(!key)continue; let f=el[key],g=0;
    while(f&&g++<5000){ scan(f.stateNode,0); if(found)break;
      let h=f.memoizedState,hg=0; while(h&&hg++<60){scan(h.memoizedState,0); if(found)break; h=h.next;}
      if(found)break; scan(f,0); if(found)break; f=f.return; }
    if(found)break; }
  if(!found)return 'no-engine';
  window.__lc = { eng: found,
    node: id => (found.nodes||[]).find(n => n.id===id),
    name: id => { const n=(found.nodes||[]).find(x=>x.id===id); return n ? (n.data||{}).name : null; },
    focusNode: (id,wx,wy,sx,sy,k) => { wx=wx??200; wy=wy??140; sx=sx??450; sy=sy??291; k=k||0.8;
      try{found.updateNodePosition&&found.updateNodePosition(id,wx,wy)}catch(e){}
      try{found.setTransform(sx/k-wx, sy/k-wy, k)}catch(e){}
      try{found.forceUpdate&&found.forceUpdate()}catch(e){} },
    box: id => { const n=(found.nodes||[]).find(x=>x.id===id); if(!n)return null;
      const t=found.getTransform?found.getTransform():{x:0,y:0,k:1};
      const nx=n.x??200, ny=n.y??140, w=n.width||650, h=n.height||360;
      return { center:[(nx+w/2+t.x)*t.k,(ny+h/2+t.y)*t.k], topLeft:[(nx+t.x)*t.k,(ny+t.y)*t.k] }; },
  };
  return 'ok:'+(found.nodes||[]).length;
})()`;
log('注入:', await page.evaluate(INJECT));

async function selectNode(id) {
  await page.evaluate(id => window.__lc.focusNode(id, 200, 140, 450, 291, 0.8), id);
  await page.waitForTimeout(1200);
  const bi = await page.evaluate(id => window.__lc.box(id), id);
  const cvb = await page.locator('canvas.leafer-canvas-view').boundingBox();
  const cands = bi ? [bi.center, [bi.topLeft[0] + 80, bi.topLeft[1] + 80], [bi.topLeft[0] + 220, bi.topLeft[1] + 160]] : [[450, 291]];
  for (const [cx, cy] of cands) {
    await page.mouse.click(cvb.x + cx, cvb.y + cy);
    await page.waitForTimeout(1600);
    const sel = await page.evaluate(() => { try { const x = window.__lc.eng.getSelectedNode(); return x && (x.id || x); } catch (e) { return null; } });
    if (sel === id) return true;
  }
  return false;
}

async function rename(id, name) {
  await page.evaluate(id => window.__lc.eng.startRename(id), id);
  await page.waitForTimeout(400);
  const inp = page.locator('input[type=text]').first();
  if (!(await page.locator('input[type=text]').count())) return false;
  await inp.click({ timeout: 4000 }).catch(() => {});
  await page.keyboard.press('Control+A').catch(() => {});
  await inp.fill(name).catch(() => {});
  await page.waitForTimeout(150);
  await page.keyboard.press('Enter').catch(() => {});
  await page.waitForTimeout(350);
  return true;
}

if (mode === 'new') {
  const [type, name, x, y] = [A, B, Number(C) || 0, Number(D) || 0];
  const id = await page.evaluate(({ type, x, y }) => window.__lc.eng.addNode(type, x, y), { type, x, y });
  await page.waitForTimeout(1800);
  log('新建:', id);
  await rename(id, name);
  log('命名:', await page.evaluate(id => window.__lc.name(id), id));
  console.log('NODEID=' + id);
  await page.waitForTimeout(6000);
  await page.screenshot({ path: `${SHOTS}/pw-new-${id.replace('p3535_', '')}.png` });
}

if (mode === 'rename') {
  log('改名:', A, '→', B);
  log('  ', await rename(A, B));
  log('  现在:', await page.evaluate(id => window.__lc.name(id), A));
  await page.waitForTimeout(4000);
}

if (mode === 'upload') {
  const [nodeId, file] = [A, B];
  if (!existsSync(file)) { log('❌ 无文件', file); await ctx.close(); process.exit(1); }
  log('上传', file, '→', nodeId, '(', await page.evaluate(id => window.__lc.name(id), nodeId), ')');
  const sel = await selectNode(nodeId);
  log('  选中:', sel);
  if (!sel) { log('❌ 选不中'); await ctx.close(); process.exit(1); }
  const [chooser] = await Promise.all([
    page.waitForEvent('filechooser', { timeout: 8000 }).catch(() => null),
    page.evaluate(() => {
      const btns = [...document.querySelectorAll('button')].filter(b => {
        const r = b.getBoundingClientRect();
        return Math.round(r.width) === 32 && Math.round(r.height) === 32 && r.y < 200 && r.x < 620;
      }).sort((a, b) => a.getBoundingClientRect().x - b.getBoundingClientRect().x);
      if (btns[0]) { btns[0].click(); return 'clicked'; }
      return 'no-button';
    }),
  ]);
  if (chooser) { await chooser.setFiles(file); log('  filechooser'); }
  else {
    const inp = page.locator('input[type=file][accept="video/*"], input[type=file][accept="image/*"]');
    if (await inp.count()) { await inp.first().setInputFiles(file); log('  setInputFiles'); }
    else { log('  ❌ 无 input'); await page.screenshot({ path: `${SHOTS}/pw-noinput.png` }); await ctx.close(); process.exit(1); }
  }
  for (let i = 0; i < 45; i++) {
    await page.waitForTimeout(3000);
    const url = await page.evaluate(id => {
      const n = window.__lc.node(id); const s = JSON.stringify((n && n.data) || {});
      const mm = s.match(/https?:\/\/[^"']+\.(mp4|webm|mov|png|jpg|jpeg|webp)/i);
      return mm ? mm[0] : null;
    }, nodeId);
    if (url) { log('  ✅ 完成:', url); console.log('URL=' + url); break; }
  }
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${SHOTS}/pw-up-${nodeId.replace('p3535_', '')}.png` });
}

if (mode === 'gen') {
  const [refId, genId, spec, dur, promptFile, runFlag] = [A, B, C, D, E, F];
  let PROMPT = null;
  if (promptFile && existsSync(promptFile)) PROMPT = readFileSync(promptFile, 'utf8').trim();
  log('gen', { refId, genId, spec, dur, promptLen: PROMPT ? PROMPT.length : 0, run: runFlag === 'RUN' });

  if (refId && refId !== 'none') {
    // ★ 支持逗号分隔多个参考；必须同一会话内全部连好再生成（addConnection 不跨刷新持久化）
    const refs = refId.split(',').map(s => s.trim()).filter(Boolean);
    for (const r of refs) {
      for (let attempt = 1; attempt <= 3; attempt++) {
        await page.evaluate(({ a, b }) => { try { window.__lc.eng.addConnection(a, b); return 'ok'; } catch (e) { return 'ERR'; } }, { a: r, b: genId });
        await page.waitForTimeout(900);
        const exists = await page.evaluate(({ a, b }) => {
          const f2 = window.__lc.eng; const c2 = f2.connections;
          if (!c2) return false;
          const arr = Array.isArray(c2) ? c2 : (c2 instanceof Map ? [...c2.values()] : Object.values(c2));
          return arr.some(e => (e.sourceId === a && e.targetId === b));
        }, { a: r, b: genId });
        if (exists) { log('  连线', r, '→ ok'); break; }
        log('  连线重试' + attempt, r);
      }
    }
    await page.waitForTimeout(1200);
  }
  // 打印本节点的所有入边
  const edges = await page.evaluate(id => {
    const c2 = window.__lc.eng.connections;
    if (!c2) return null;
    const arr = Array.isArray(c2) ? c2 : (c2 instanceof Map ? [...c2.values()] : Object.values(c2));
    return arr.filter(e => e.targetId === id).map(e => e.sourceId);
  }, genId);
  log('  ★ 参考入边:', JSON.stringify(edges));
  const sel = await selectNode(genId);
  log('  选中:', sel);
  if (!sel) { log('❌ 选不中'); await ctx.close(); process.exit(1); }

  if (spec && spec !== 'none') {
    await page.evaluate(() => { const b = [...document.querySelectorAll('button')].find(x => /LingCut（|wan3|Seedance/i.test(x.textContent || '')); if (b) b.click(); });
    await page.waitForTimeout(1500);
    log('  模型:', await page.evaluate(s => {
      const key = s.split('（')[0].split('/')[0];
      const o = [...document.querySelectorAll('*')].find(e => e.children.length === 0 && (e.textContent || '').includes(key) && e.getBoundingClientRect().width > 0);
      if (!o) return 'not-found'; o.click(); return 'clicked:' + (o.textContent || '').trim().slice(0, 40);
    }, spec));
    await page.waitForTimeout(1800);
  }
  if (dur && dur !== 'none') {
    await page.evaluate(() => { const b = [...document.querySelectorAll('button')].find(x => /^\d+s[▼]?$/.test((x.textContent || '').trim())); if (b) b.click(); });
    await page.waitForTimeout(1200);
    log('  时长:', await page.evaluate(d => {
      const o = [...document.querySelectorAll('*')].find(e => e.children.length === 0 && (e.textContent || '').trim() === d && e.getBoundingClientRect().width > 0);
      if (o) { o.click(); return 'set:' + d; } return 'not-found';
    }, dur));
    await page.waitForTimeout(1000);
  }
  if (PROMPT) {
    // ★ 两条路都要走：data.prompt（生成真正读的）+ contenteditable（UI 显示/提交钩子）
    const setData = await page.evaluate(({ id, p }) => {
      try { window.__lc.eng.updateNodeData(id, { prompt: p }, true); return 'data ok'; } catch (e) { return 'data ERR ' + String(e).slice(0, 80); }
    }, { id: genId, p: PROMPT });
    log('  data.prompt:', setData, '→', await page.evaluate(id => (window.__lc.node(id).data.prompt || '').length, genId));
    await page.waitForTimeout(800);
    log('  输入框:', await page.evaluate(p => {
      const ce = [...document.querySelectorAll('[contenteditable="true"]')].find(e => e.getBoundingClientRect().width > 300);
      if (!ce) return 'no-box';
      ce.focus(); const s = window.getSelection(), r = document.createRange();
      r.selectNodeContents(ce); s.removeAllRanges(); s.addRange(r);
      document.execCommand('delete', false, null); document.execCommand('insertText', false, p);
      ce.dispatchEvent(new Event('input', { bubbles: true }));
      ce.dispatchEvent(new Event('blur', { bubbles: true }));
      return 'len=' + (ce.innerText || '').length;
    }, PROMPT));
    await page.waitForTimeout(1500);
  }
  await page.screenshot({ path: `${SHOTS}/pw-ready-${genId.replace('p3535_', '')}.png` });

  if (runFlag === 'RUN') {
    log('  ★ 生成（付费）…');
    log('  ', await page.evaluate(() => { const b = [...document.querySelectorAll('button')].find(x => (x.textContent || '').trim() === '↑'); if (!b) return 'no-arrow'; b.click(); return 'clicked'; }));
    await page.waitForTimeout(6000);
    for (let i = 0; i < 100; i++) {
      await page.waitForTimeout(10000);
      const st = await page.evaluate(id => {
        const n = window.__lc.node(id); const d = (n && n.data) || {}; const s = JSON.stringify(d);
        const mm = s.match(/https?:\/\/[^"']+\.mp4/i);
        return { gen: !!d.generating, err: d.genError ? String(d.genError).slice(0, 140) : null, url: mm ? mm[0] : null };
      }, genId);
      if (st.url) { log('  ✅ 出片:', st.url); console.log('VIDEO=' + st.url); break; }
      if (!st.gen && st.err) { log('  ❌', st.err); break; }
      if (!st.gen && i >= 3) { log('  ⚠️ 停止但无 URL'); break; }
      if (i % 3 === 0) log('    生成中…', i * 10, 's');
    }
    await page.screenshot({ path: `${SHOTS}/pw-done-${genId.replace('p3535_', '')}.png` });
  } else log('  ⚠️ 未点生成');
}

await ctx.close();
log('完成');
