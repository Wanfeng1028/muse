// Liet ke cac binh luan THUC SU duoc ve ra trong trang da luu
const puppeteer = require('puppeteer-core');
const path = require('path');

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--use-gl=swiftshader', '--no-sandbox', '--allow-file-access-from-files',
           '--hide-scrollbars'],
    defaultViewport: { width: 900, height: 2600, deviceScaleFactor: 1 },
  });
  const page = await browser.newPage();
  await page.goto('file:///' + path.resolve(process.argv[2]).replace(/\\/g, '/'),
                  { waitUntil: 'load', timeout: 120000 });
  await new Promise(r => setTimeout(r, 3500));

  const rows = await page.evaluate(() => {
    return [...document.querySelectorAll('div[role="article"]')]
      .map(a => {
        const r = a.getBoundingClientRect();
        const label = a.getAttribute('aria-label') || '';
        const m = label.match(/Bình luận dưới tên (.+?) vào/);
        let txt = (a.innerText || '').replace(/\s+/g, ' ').trim();
        txt = txt.replace(/^.*?·\s*\d+\s*(ngày|giờ|phút)\s*(· Theo dõi)?\s*/, '');
        txt = txt.replace(/(Thích)?Trả lời(Gửi tin nhắn)?(Chia sẻ)?\s*\d*(Xem \d+ câu trả lời)?\s*$/, '').trim();
        return {
          name: m ? m[1] : '(bài đăng)',
          w: Math.round(r.width), h: Math.round(r.height),
          len: txt.length, text: txt,
        };
      })
      .filter(x => x.w > 100 && x.h > 30 && x.len > 40)
      .sort((a, b) => b.len - a.len);
  });

  console.log(`${rows.length} binh luan hien thi that:\n`);
  for (const r of rows) {
    console.log(`--- ${r.name} | ${r.w}x${r.h} | ${r.len} chu ---`);
    console.log(r.text.slice(0, 500));
    console.log();
  }
  await browser.close();
})();
