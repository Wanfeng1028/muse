// Render an Explainer Video HTML at native resolution via fast CDP screencast,
// logging the player's logical time (t) so each frame is remapped to it →
// high fps AND perfect audio sync (no upscale blur, no wall-clock drift).
//
// Config via env vars:
//   EXPLAINER_URL   page URL served locally   (default http://localhost:8753/explainer.html)
//   EXPLAINER_OUT   frames output dir          (default ./frames next to this script)
//   EXPLAINER_W / EXPLAINER_H   resolution     (default 2560x1440)
//   CHROME_PATH     path to Chrome/Chromium    (default macOS Google Chrome)
//
// The page must expose globals: TOTAL, t, seek(t), play()  (the engine does).
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const CHROME = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const URL = process.env.EXPLAINER_URL || 'http://localhost:8753/explainer.html';
const OUT = process.env.EXPLAINER_OUT || path.join(process.cwd(), 'frames');
const W = parseInt(process.env.EXPLAINER_W || '2560', 10);
const H = parseInt(process.env.EXPLAINER_H || '1440', 10);

(async () => {
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });

  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: 'new',
    args: ['--no-sandbox', '--autoplay-policy=no-user-gesture-required', '--mute-audio',
           `--window-size=${W},${H}`, '--hide-scrollbars', '--force-device-scale-factor=1'],
    defaultViewport: { width: W, height: H, deviceScaleFactor: 1 },
  });
  const page = await browser.newPage();
  await page.goto(URL, { waitUntil: 'networkidle0', timeout: 60000 });
  await page.addStyleTag({ content: `
    body{align-items:flex-start!important;justify-content:flex-start!important;}
    #app{width:${W}px!important;}
    .controls,.scenes,.hint{display:none!important;}
    .stage{border-radius:0!important;box-shadow:none!important;}
    .scenebadge{display:none!important;}
  `});
  // audio off during render (rAF wall clock drives t); install a logical-time logger
  await page.evaluate(() => {
    const a = document.getElementById('vo'); if (a) { a.muted = true; a.play = () => Promise.resolve(); }
    window.__log = [];
    (function rec(){ window.__log.push([performance.now(), t]); requestAnimationFrame(rec); })();
  });

  const TOTAL = await page.evaluate(() => TOTAL);
  const client = await page.target().createCDPSession();
  const frames = [];          // {seq, ts}
  const pending = [];
  client.on('Page.screencastFrame', (f) => {
    client.send('Page.screencastFrameAck', { sessionId: f.sessionId }).catch(()=>{});
    const seq = frames.length;
    frames.push(f.metadata.timestamp);
    pending.push(fs.promises.writeFile(path.join(OUT, `f${String(seq).padStart(6,'0')}.jpg`), Buffer.from(f.data, 'base64')));
  });
  await client.send('Page.startScreencast', { format: 'jpeg', quality: 88, everyNthFrame: 1 });
  await page.evaluate(() => { seek(0); play(); });

  const deadline = Date.now() + (TOTAL + 8) * 1000;
  while (Date.now() < deadline) { if (await page.evaluate(() => t >= TOTAL - 0.04)) break; await new Promise(r => setTimeout(r, 150)); }
  await new Promise(r => setTimeout(r, 300));
  await client.send('Page.stopScreencast');
  await Promise.all(pending);

  const meta = await page.evaluate(() => ({ log: window.__log, origin: performance.timeOrigin }));
  await browser.close();

  // remap each screencast frame (wall ts, seconds-since-epoch) → logical t via the log
  const log = meta.log;                 // [ [perfnow_ms, t], ... ]
  function logicalAt(perfnow){
    if (perfnow <= log[0][0]) return log[0][1];
    if (perfnow >= log[log.length-1][0]) return log[log.length-1][1];
    let lo=0, hi=log.length-1;
    while (hi-lo>1){ const m=(lo+hi)>>1; if (log[m][0] < perfnow) lo=m; else hi=m; }
    const [t0,v0]=log[lo], [t1,v1]=log[hi];
    return v0 + (v1-v0)*((perfnow-t0)/Math.max(1e-6,(t1-t0)));
  }
  const tl = frames.map(ts => +logicalAt(ts*1000 - meta.origin).toFixed(4));
  // ensure monotonic
  for (let i=1;i<tl.length;i++) if (tl[i] <= tl[i-1]) tl[i] = tl[i-1] + 0.001;
  fs.writeFileSync(path.join(OUT, 'frames.json'), JSON.stringify({ frames: tl, total: TOTAL }));
  const fps = (tl.length / (tl[tl.length-1]-tl[0])).toFixed(1);
  console.log(`captured ${tl.length} frames, logical span ${tl[tl.length-1].toFixed(1)}s / TOTAL ${TOTAL}, ~${fps} fps @ ${W}x${H}`);
})();
