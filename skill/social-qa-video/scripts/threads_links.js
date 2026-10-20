// Lay permalink cua tung reply, roi mo tung cai de gom them reply con
const puppeteer = require('puppeteer-core');
const fs = require('fs');

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const [URL, OUT] = process.argv.slice(2);

async function openAndDump(page, url) {
  await page.goto(url, { waitUntil: 'networkidle2', timeout: 120000 });
  await new Promise(r => setTimeout(r, 3000));
  await page.evaluate(() => {
    for (const d of document.querySelectorAll('[role="dialog"]')) d.remove();
  });
  for (let i = 0; i < 6; i++) {
    await page.evaluate(() => window.scrollBy(0, window.innerHeight * 0.9));
    await new Promise(r => setTimeout(r, 900));
  }
  return page.evaluate(() => {
    return [...document.querySelectorAll('div[data-pressable-container="true"]')]
      .map(p => {
        const txt = (p.innerText || '').replace(/\u00a0/g, ' ').trim();
        const a = p.querySelector('a[href*="/post/"]');
        return { text: txt, len: txt.length, href: a ? a.getAttribute('href') : null };
      })
      .filter(x => x.len > 20);
  });
}

(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--use-gl=swiftshader', '--no-sandbox', '--hide-scrollbars',
           '--disable-dev-shm-usage', '--lang=vi-VN'],
    defaultViewport: { width: 900, height: 1600, deviceScaleFactor: 1 },
  });
  const page = await browser.newPage();
  await page.setExtraHTTPHeaders({ 'Accept-Language': 'vi-VN,vi;q=0.9' });

  const root = await openAndDump(page, URL);
  console.log(`Trang goc: ${root.length} khoi`);

  const seen = new Set(root.map(r => r.text));
  const all = [...root];
  const links = [...new Set(root.map(r => r.href).filter(Boolean))];
  console.log(`Co ${links.length} permalink, dang mo tung cai...\n`);

  for (const href of links) {
    const url = href.startsWith('http') ? href : 'https://www.threads.com' + href;
    try {
      const rows = await openAndDump(page, url);
      let moi = 0;
      for (const r of rows) {
        if (!seen.has(r.text)) { seen.add(r.text); all.push(r); moi++; }
      }
      console.log(`  ${url.slice(-30)}: ${rows.length} khoi, ${moi} moi`);
    } catch (e) {
      console.log(`  ${url.slice(-30)}: loi ${e.message.slice(0, 40)}`);
    }
  }

  all.sort((a, b) => b.len - a.len);
  fs.writeFileSync(OUT, JSON.stringify(all, null, 2), 'utf8');
  console.log(`\nTONG CONG ${all.length} khoi\n`);
  for (const r of all) {
    console.log(`--- ${r.len} chu ---`);
    console.log(r.text.replace(/\n/g, ' | ').slice(0, 300));
    console.log();
  }
  await browser.close();
})();
