const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const DIST = '/home/hatch/workspace/muse-repo/CodexCopy/dist';
const BASE = 'http://localhost:8931';
const FRAMES = '/home/hatch/workspace/muse-repo/CodexCopy/frames2';
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' };

(async () => {
  fs.mkdirSync(FRAMES, { recursive: true });
  const browser = await chromium.launch({
    executablePath: '/opt/meta-chromium/chrome',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  await ctx.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    let p = url.pathname === '/' ? '/index.html' : url.pathname;
    const fp = path.join(DIST, decodeURIComponent(p));
    try {
      const data = fs.readFileSync(fp);
      await route.fulfill({ body: data, contentType: MIME[path.extname(fp)] || 'application/octet-stream' });
    } catch (e) { await route.fulfill({ status: 404, body: 'nf' }); }
  });
  const page = await ctx.newPage();
  let html = fs.readFileSync(path.join(DIST, 'index.html'), 'utf-8');
  html = html.split('"/assets/').join('"' + BASE + '/assets/');
  await page.setContent(html, { url: BASE + '/' });
  await page.waitForTimeout(2500);

  let n = 0;
  const shot = async (times = 2) => {
    for (let i = 0; i < times; i++) {
      await page.screenshot({ path: path.join(FRAMES, 'f' + String(n++).padStart(4, '0') + '.png') });
      await page.waitForTimeout(400);
    }
  };

  // 1. 首屏：已有会话
  await shot(4);

  // 2. 展开一个 tool card
  const cards = page.locator('.tool-head');
  if (await cards.count() > 0) { await cards.first().click(); await shot(3); }

  // 3. 展开 Thought
  const th = page.locator('.thinking-head');
  if (await th.count() > 0) { await th.first().click(); await shot(3); }

  // 4. 切换到另一个 thread
  const items = page.locator('.thread-item');
  if (await items.count() > 2) { await items.nth(2).click(); await page.waitForTimeout(800); await shot(4); }

  // 5. 新建 thread -> 空状态
  await page.locator('.new-thread-btn').click();
  await page.waitForTimeout(800);
  await shot(4);

  // 6. 输入并发送消息，等待模拟回复
  await page.locator('.composer textarea').fill('帮我把登录页改成深色模式');
  await shot(2);
  await page.locator('.send-btn').click();
  await shot(3); // streaming 状态
  await page.waitForTimeout(3000);
  await shot(5); // 回复出现

  // 7. 打开 model 选择器
  const modelBtns = page.locator('.composer-tool');
  if (await modelBtns.count() > 1) { await modelBtns.nth(1).click(); await shot(3); }

  console.log('frames:', n);
  await browser.close();

  // 合成视频
  execSync(
    `ffmpeg -y -v error -framerate 2.5 -i ${FRAMES}/f%04d.png -c:v libx264 -pix_fmt yuv420p -movflags +faststart /home/hatch/workspace/muse-repo/CodexCopy/CodexCopy-demo.mp4`,
    { stdio: 'inherit' }
  );
  console.log('video done');
})();
