const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const WEB = '/home/hatch/workspace/muse-repo/CodexCopy/web';
const BASE = 'http://localhost:8931';
const FRAMES = '/home/hatch/workspace/muse-repo/CodexCopy/frames';
const MIME = { '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };

(async () => {
  fs.mkdirSync(FRAMES, { recursive: true });
  const browser = await chromium.launch({
    executablePath: '/opt/meta-chromium/chrome',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  await ctx.addInitScript(() => {
    const store = {};
    try {
      Object.defineProperty(window, 'localStorage', {
        value: {
          getItem: (k) => (k in store ? store[k] : null),
          setItem: (k, v) => { store[k] = String(v); },
          removeItem: (k) => { delete store[k]; },
          clear: () => {},
          get length() { return 0; },
          key: () => null,
        },
        configurable: true,
      });
    } catch (e) {}
  });
  await ctx.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const fp = path.join(WEB, decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname));
    try {
      const data = fs.readFileSync(fp);
      await route.fulfill({ body: data, contentType: MIME[path.extname(fp)] || 'application/octet-stream', headers: { 'Access-Control-Allow-Origin': '*' } });
    } catch (e) { await route.fulfill({ status: 404, body: 'nf' }); }
  });

  const page = await ctx.newPage();
  let html = fs.readFileSync(path.join(WEB, 'index.html'), 'utf-8');
  html = html.replace(/<meta http-equiv="Content-Security-Policy"[^>]*>/, '');
  html = html.split('"./').join('"' + BASE + '/');

  let n = 0;
  const shot = async () => {
    await page.screenshot({ path: path.join(FRAMES, 'f' + String(n++).padStart(4, '0') + '.png') });
  };

  // Scene 1: 空白页 -> 开始加载
  await page.goto('about:blank');
  await shot(); await shot();
  await page.setContent(html, { url: BASE + '/' });
  // Scene 2: 启动过程（密集截图捕捉 loader -> logo）
  for (let i = 0; i < 16; i++) { await page.waitForTimeout(500); await shot(); }
  // Scene 3: 在控制台验证 shim 标记与零错误
  await page.evaluate(() => console.log('CODEXCOPY MARKER:', JSON.stringify(window.__CODEXCOPY__)));
  for (let i = 0; i < 6; i++) { await page.waitForTimeout(500); await shot(); }

  console.log('frames:', n);
  await browser.close();
})();
