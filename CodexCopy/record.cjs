const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const DIST = '/home/hatch/workspace/muse-repo/CodexCopy/dist';
const BASE = 'http://localhost:8931';
const FRAMES = '/home/hatch/workspace/muse-repo/CodexCopy/frames4';
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' };

(async () => {
  fs.rmSync(FRAMES, { recursive: true, force: true });
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
  const shot = async (ms = 200, times = 1) => {
    for (let i = 0; i < times; i++) {
      await page.screenshot({ path: path.join(FRAMES, 'f' + String(n++).padStart(4, '0') + '.png') });
      await page.waitForTimeout(ms);
    }
  };
  const move = async (x, y) => { await page.mouse.move(x, y, { steps: 8 }); await shot(120, 2); };

  // 1. 主界面（带窗口 chrome）
  await shot(300, 6);

  // 2. 展开 tool card
  const card = page.locator('.tool-head').first();
  const bb = await card.boundingBox();
  await move(bb.x + bb.width / 2, bb.y + bb.height / 2);
  await card.click();
  await shot(250, 6);

  // 3. Cmd+K 命令面板
  await page.keyboard.press('Control+k');
  await page.waitForTimeout(500);
  await shot(250, 6);
  await page.keyboard.press('Escape');
  await shot(200, 2);

  // 4. 设置中心
  await page.locator('.settings-btn[title="Codex settings"]').click();
  await page.waitForTimeout(500);
  await shot(250, 6);
  // 切换 Appearance
  await page.locator('.set-nav-item').nth(1).click();
  await page.waitForTimeout(400);
  await shot(250, 5);
  // 切换 Models
  await page.locator('.set-nav-item').nth(2).click();
  await page.waitForTimeout(400);
  await shot(250, 5);

  // 5. 自动化视图
  await page.locator('.settings-btn[title="Automations"]').click();
  await page.waitForTimeout(500);
  await shot(250, 6);
  // 暂停一个
  const pauseBtns = page.locator('.auto-card .icon-btn');
  await pauseBtns.first().click();
  await shot(250, 4);

  // 6. 回到 thread，新建 + 发送消息（含 DiffBlock 回复）
  await page.locator('.thread-item').first().click();
  await page.waitForTimeout(500);
  await shot(250, 4);
  const nb = page.locator('.new-thread-btn');
  const nbb = await nb.boundingBox();
  await move(nbb.x + 60, nbb.y + 18);
  await nb.click();
  await page.waitForTimeout(500);
  await shot(250, 4);
  await page.locator('.composer textarea').fill('把主题 token 改成深色模式变量');
  await shot(250, 3);
  const send = page.locator('.send-btn');
  const sbb = await send.boundingBox();
  await move(sbb.x + 16, sbb.y + 16);
  await send.click();
  await shot(250, 5);
  await page.waitForTimeout(3400);
  await shot(250, 10); // DiffBlock 回复

  // 7. Accept diff
  const accept = page.locator('.diff-foot .btn-ghost.ok');
  if (await accept.count() > 0) {
    const abb = await accept.boundingBox();
    await move(abb.x + 40, abb.y + 14);
    await accept.click();
    await shot(250, 5);
  }

  console.log('frames:', n);
  await browser.close();

  execSync(
    `ffmpeg -y -v error -framerate 5 -i ${FRAMES}/f%04d.png -c:v libx264 -profile:v baseline -level 3.1 -pix_fmt yuv420p -movflags +faststart /home/hatch/workspace/muse-repo/CodexCopy/CodexCopy-demo.mp4`,
    { stdio: 'inherit' }
  );
  console.log('video done');
})();
