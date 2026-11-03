// Mo bai Threads cong khai, cuon de tai them reply, xuat noi dung ra JSON
const puppeteer = require('puppeteer-core');
const fs = require('fs');

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const [URL, OUT] = process.argv.slice(2);
const SCROLLS = parseInt(process.env.SCROLLS || '14', 10);

(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--use-gl=swiftshader', '--no-sandbox', '--hide-scrollbars',
           '--disable-dev-shm-usage', '--lang=vi-VN'],
    defaultViewport: { width: 900, height: 1400, deviceScaleFactor: 2 },
  });
  const page = await browser.newPage();
  await page.setExtraHTTPHeaders({ 'Accept-Language': 'vi-VN,vi;q=0.9' });
  await page.goto(URL, { waitUntil: 'networkidle2', timeout: 120000 });
  await new Promise(r => setTimeout(r, 4000));

  // dong popup dang nhap neu co
  await page.evaluate(() => {
    for (const b of document.querySelectorAll('div[role="button"],button')) {
      const t = (b.getAttribute('aria-label') || b.innerText || '').trim();
      if (/^(Close|Đóng|Not now|Để sau)$/i.test(t)) b.click();
    }
  });
  await new Promise(r => setTimeout(r, 1500));

  // cuon de tai them reply
  for (let i = 0; i < SCROLLS; i++) {
    await page.evaluate(() => window.scrollBy(0, window.innerHeight * 0.9));
    await new Promise(r => setTimeout(r, 1200));
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await new Promise(r => setTimeout(r, 1500));

  const data = await page.evaluate(() => {
    const posts = [...document.querySelectorAll('div[data-pressable-container="true"]')];
    const rows = posts.map((p, i) => {
      const r = p.getBoundingClientRect();
      const txt = (p.innerText || '').replace(/\u00a0/g, ' ').trim();
      return { i, w: Math.round(r.width), h: Math.round(r.height), len: txt.length, text: txt };
    }).filter(x => x.len > 20);
    return { count: posts.length, rows, title: document.title, url: location.href };
  });

  console.log('URL:', data.url);
  console.log('title:', data.title);
  console.log('so khoi:', data.count, '| co noi dung:', data.rows.length, '\n');
  const sorted = [...data.rows].sort((a, b) => b.len - a.len);
  for (const r of sorted.slice(0, 16)) {
    console.log(`--- [${r.i}] ${r.w}x${r.h} | ${r.len} chu ---`);
    console.log(r.text.replace(/\n/g, ' | ').slice(0, 400));
    console.log();
  }
  fs.writeFileSync(OUT, JSON.stringify(data.rows, null, 2), 'utf8');
  await page.screenshot({ path: OUT.replace(/\.json$/, '_view.png') });
  await browser.close();
})();
