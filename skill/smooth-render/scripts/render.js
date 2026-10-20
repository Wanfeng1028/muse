// Smooth logical-time renderer for HTML/CSS animations.
// Defeats CDP screencast frame-coalescing (which makes gradual CSS transitions / blur / glass
// effects look choppy) with two tricks:
//   1) SLOW CLOCK   — the page advances its logical time `t` by dt*window.__RATE, so each
//      logical second spans more wall-clock time → more captured frames per logical second.
//   2) HEARTBEAT    — a 1px corner dot mutated every rAF so the screencast never coalesces
//      a "still" region and keeps emitting frames at a uniform high rate.
// Each captured frame is tagged with the page's logical time, then remapped so playback timing
// is exact (no wall-clock drift, no upscale blur). Output: per-frame JPEGs + frames.json.
//
// The PAGE must expose: a global `t` (logical seconds), `TOTAL`, `seek(t)`, `play()`, and must
// scale its CSS transition/animation DURATIONS by 1/__RATE so motion stays correctly timed in
// logical time (see SKILL.md "Wiring your page"). RATE 0.6–0.8 is a good range (≥30 logical fps).
const puppeteer = require('puppeteer-core');
const fs = require('fs'); const path = require('path');
const CHROME = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const URL = process.env.RENDER_URL || 'http://localhost:8755/index.html';
const OUT = process.env.RENDER_OUT || path.join(process.cwd(), 'frames');
const W = parseInt(process.env.RENDER_W || '2560', 10);
const H = parseInt(process.env.RENDER_H || '1440', 10);
const QUALITY = parseInt(process.env.RENDER_Q || '85', 10);
const RATE = parseFloat(process.env.RENDER_RATE || '0.7');   // logical-clock slowdown
process.on('unhandledRejection', e => { console.error('REJECT', e); process.exit(1); });

(async () => {
  fs.rmSync(OUT, { recursive: true, force: true }); fs.mkdirSync(OUT, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: 'new',
    args: ['--no-sandbox', '--autoplay-policy=no-user-gesture-required', '--mute-audio',
           `--window-size=${W},${H}`, '--hide-scrollbars', '--force-device-scale-factor=1',
           '--ignore-gpu-blocklist', '--enable-gpu-rasterization', '--enable-zero-copy',
           '--use-angle=metal', '--enable-features=Metal'],
    defaultViewport: { width: W, height: H, deviceScaleFactor: 1 },
  });
  const page = await browser.newPage();
  await page.goto(URL, { waitUntil: 'networkidle0', timeout: 60000 });
  await page.evaluate(r => { window.__RATE = r; window.__TK = 1 / r; }, RATE);
  await page.evaluate(() => {
    const a = document.getElementById('vo'); if (a) { a.muted = true; a.play = () => Promise.resolve(); }
    window.__log = [];
    const d = document.createElement('div');               // heartbeat
    d.style.cssText = 'position:fixed;right:0;bottom:0;width:3px;height:3px;z-index:99999;';
    document.body.appendChild(d); let k = 0;
    (function rec(){ window.__log.push([performance.now(), t]); d.style.background = (k++ & 1) ? '#000' : '#020203'; requestAnimationFrame(rec); })();
  });
  const TOTAL = await page.evaluate(() => TOTAL);
  const client = await page.target().createCDPSession();
  const frames = []; const pending = [];
  client.on('Page.screencastFrame', (f) => {
    client.send('Page.screencastFrameAck', { sessionId: f.sessionId }).catch(()=>{});
    const seq = frames.length; frames.push(f.metadata.timestamp);
    pending.push(fs.promises.writeFile(path.join(OUT, `f${String(seq).padStart(6,'0')}.jpg`), Buffer.from(f.data, 'base64')));
  });
  await client.send('Page.startScreencast', { format: 'jpeg', quality: QUALITY, everyNthFrame: 1 });
  await page.evaluate(() => { seek(0); play(); });
  const deadline = Date.now() + (TOTAL / RATE + 20) * 1000;
  while (Date.now() < deadline) { if (await page.evaluate(() => t >= TOTAL - 0.04)) break; await new Promise(r => setTimeout(r, 120)); }
  await new Promise(r => setTimeout(r, 300));
  await client.send('Page.stopScreencast'); await Promise.all(pending);
  const meta = await page.evaluate(() => ({ log: window.__log, origin: performance.timeOrigin }));
  await browser.close();
  const log = meta.log;
  const logicalAt = (perfnow) => {
    if (perfnow <= log[0][0]) return log[0][1];
    if (perfnow >= log[log.length-1][0]) return log[log.length-1][1];
    let lo=0, hi=log.length-1; while (hi-lo>1){ const m=(lo+hi)>>1; if (log[m][0] < perfnow) lo=m; else hi=m; }
    const [t0,v0]=log[lo], [t1,v1]=log[hi]; return v0 + (v1-v0)*((perfnow-t0)/Math.max(1e-6,(t1-t0)));
  };
  const tl = frames.map(ts => +logicalAt(ts*1000 - meta.origin).toFixed(4));
  for (let i=1;i<tl.length;i++) if (tl[i] <= tl[i-1]) tl[i] = tl[i-1] + 0.001;
  fs.writeFileSync(path.join(OUT, 'frames.json'), JSON.stringify({ frames: tl, total: TOTAL }));
  console.log(`captured ${tl.length} frames, logical span ${tl[tl.length-1].toFixed(1)}s / TOTAL ${TOTAL} @ ${W}x${H}`);
})();
