// Chup anh that cua bai dang + reply tren Threads (bai cong khai, khong can dang nhap).
// Dung: node shot/threads_shot.js <url> <targets.json> <thu-muc-xuat>
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const [URL, TARGETS, OUTDIR] = process.argv.slice(2);
const ZOOM = parseFloat(process.env.SHOT_ZOOM || '1');

(async () => {
  const targets = JSON.parse(fs.readFileSync(TARGETS, 'utf8'));
  fs.mkdirSync(OUTDIR, { recursive: true });

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--use-gl=swiftshader', '--no-sandbox', '--hide-scrollbars',
           '--disable-dev-shm-usage', '--lang=vi-VN'],
    // Threads khong render neu khung nhin qua cao -> dung khung thuong
    // roi cuon toi tung khoi truoc khi chup.
    defaultViewport: { width: 900, height: 1600, deviceScaleFactor: 3 },
  });
  const page = await browser.newPage();
  await page.setExtraHTTPHeaders({ 'Accept-Language': 'vi-VN,vi;q=0.9' });
  // Threads mac dinh nen toi; ep giao dien sang cho giong card trong video mau
  await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'light' }]);
  await page.goto(URL, { waitUntil: 'networkidle2', timeout: 120000 });
  await new Promise(r => setTimeout(r, 4500));

  // dong popup dang nhap + an thanh noi (banner tai app, nut dang nhap)
  await page.evaluate(() => {
    for (const b of document.querySelectorAll('div[role="button"],button')) {
      const t = (b.getAttribute('aria-label') || b.innerText || '').trim();
      if (/^(Close|Đóng|Not now|Để sau)$/i.test(t)) b.click();
    }
    // Threads bat popup dang nhap kem lop phu den mo toan trang -> anh chup
    // bi toi di. Go han popup va lop phu, nhung KHONG an moi position:fixed
    // vi khung noi dung chinh cua Threads cung la fixed.
    for (const d of document.querySelectorAll('[role="dialog"]')) d.remove();
    for (const f of document.querySelectorAll('div')) {
      const cs = getComputedStyle(f);
      if (cs.position !== 'fixed') continue;
      const r = f.getBoundingClientRect();
      const bg = cs.backgroundColor || '';
      const m = bg.match(/rgba?\(([^)]+)\)/);
      const alpha = m ? parseFloat((m[1].split(',')[3] || '1').trim()) : 0;
      const phuKin = r.width >= window.innerWidth * 0.9 && r.height >= window.innerHeight * 0.9;
      if (phuKin && alpha > 0.05 && !f.querySelector('div[data-pressable-container="true"]')) {
        f.remove();
      }
    }
  });
  await new Promise(r => setTimeout(r, 1200));

  if (ZOOM !== 1) {
    await page.evaluate((z) => { document.body.style.zoom = String(z); }, ZOOM);
    await new Promise(r => setTimeout(r, 1500));
  }

  // mo trang goc mot lan; sau do moi target co the co URL rieng
  let current = URL;

  const prepare = async (url) => {
    if (url === current) return;
    await page.goto(url, { waitUntil: 'networkidle2', timeout: 120000 });
    await new Promise(r => setTimeout(r, 3500));
    await page.evaluate(() => {
      for (const d of document.querySelectorAll('[role="dialog"]')) d.remove();
      for (const f of document.querySelectorAll('div')) {
        const cs = getComputedStyle(f);
        if (cs.position !== 'fixed') continue;
        const r = f.getBoundingClientRect();
        const bg = cs.backgroundColor || '';
        const m = bg.match(/rgba?\(([^)]+)\)/);
        const alpha = m ? parseFloat((m[1].split(',')[3] || '1').trim()) : 0;
        const phuKin = r.width >= window.innerWidth * 0.9 && r.height >= window.innerHeight * 0.9;
        if (phuKin && alpha > 0.05 && !f.querySelector('div[data-pressable-container="true"]')) {
          f.remove();
        }
      }
    });
    if (ZOOM !== 1) {
      await page.evaluate((z) => { document.body.style.zoom = String(z); }, ZOOM);
      await new Promise(r => setTimeout(r, 1200));
    }
    current = url;
  };

  const report = [];
  for (const t of targets) {
    await prepare(t.url || URL);
    const box = await page.evaluate((t) => {
      const blocks = [...document.querySelectorAll('div[data-pressable-container="true"]')]
        .filter(b => (b.innerText || '').includes(t.needle))
        .filter(b => {
          const r = b.getBoundingClientRect();
          return r.width > 50 && r.height > 20;
        });
      // chon khoi nho nhat dang hien thi (tranh container bao nhieu reply)
      blocks.sort((a, b) => (a.innerText || '').length - (b.innerText || '').length);
      const el = blocks[0];
      if (!el) return null;

      if (t.blurName) {
        for (const a of el.querySelectorAll('a')) {
          const href = a.getAttribute('href') || '';
          if (/^\/@/.test(href)) { a.style.filter = 'blur(7px)'; }
        }
      }
      // Threads luu theme rieng (khong theo prefers-color-scheme), nen phai
      // doi mau thu cong: nen trang, chu den, giu nguyen anh dai dien.
      if (!t.keepDark) {
        el.style.background = '#ffffff';
        for (const d of el.querySelectorAll('*')) {
          const cs = getComputedStyle(d);
          if (cs.backgroundColor && cs.backgroundColor !== 'rgba(0, 0, 0, 0)') {
            d.style.backgroundColor = 'transparent';
          }
          const c = cs.color;
          if (c) {
            const m = c.match(/\d+/g);
            if (m) {
              const lum = (+m[0] * 0.299 + +m[1] * 0.587 + +m[2] * 0.114);
              // chu sang (tren nen toi) -> doi thanh den; chu xam nhat -> xam dam
              d.style.color = lum > 170 ? '#0a0a0a' : (lum > 110 ? '#6b6b6b' : cs.color);
            }
          }
          if (cs.borderTopColor) d.style.borderColor = '#e4e4e4';
        }
      }
      // an anh/video dinh kem (giu avatar nho) de card khong qua cao
      if (t.hideMedia) {
        for (const m of el.querySelectorAll('img,video,picture')) {
          const r = m.getBoundingClientRect();
          if (r.width > 120 || r.height > 120) {
            let box = m;
            for (let i = 0; i < 4 && box.parentElement && box.parentElement !== el; i++) {
              box = box.parentElement;
            }
            box.style.display = 'none';
          }
        }
      }
      el.style.borderRadius = '22px';
      el.style.padding = '10px 16px';
      el.style.boxSizing = 'content-box';
      el.scrollIntoView({ block: 'center' });

      const r = el.getBoundingClientRect();
      return { x: r.x, y: r.y, width: r.width, height: r.height,
               text: (el.innerText || '').replace(/\s+/g, ' ').slice(0, 70) };
    }, t);

    if (!box || box.width < 10 || box.height < 10) {
      console.log(`!! BO QUA: ${t.key} (${t.needle.slice(0, 40)}) ${JSON.stringify(box)}`);
      continue;
    }
    await new Promise(r => setTimeout(r, 400));

    const out = path.join(OUTDIR, `${t.key}.png`);
    await page.screenshot({
      path: out,
      captureBeyondViewport: false,
      clip: { x: Math.max(0, box.x), y: Math.max(0, box.y),
              width: box.width, height: box.height },
    });
    console.log(`${t.key}: ${Math.round(box.width)}x${Math.round(box.height)} -> ${out}`);
    console.log(`       ${box.text}`);
    report.push({ key: t.key, w: box.width, h: box.height, text: box.text });
  }

  fs.writeFileSync(path.join(OUTDIR, 'report.json'), JSON.stringify(report, null, 2));
  await browser.close();
})();
