// Cần playwright: npm i -g playwright  (hoặc npm i playwright trong thư mục làm việc)
// Chạy mặc định:  node 16_get_stock_photos.mjs
// Chạy 1 query:   node 16_get_stock_photos.mjs "live stream shopping seller" livestream unsplash
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
const OUT = 'photos';
fs.mkdirSync(OUT, { recursive: true });
const argv = process.argv.slice(2);
const jobs = argv.length >= 2 ? [[argv[1], argv[0], argv[2] || 'unsplash']] : [
  ['livestream', 'live stream shopping seller', 'unsplash'],
  ['packing', 'packing orders boxes small business', 'unsplash'],
  ['phoneshop', 'woman online shopping smartphone', 'unsplash'],
  ['analytics', 'business chart growth laptop', 'unsplash'],
  ['warehouse', 'small business warehouse boxes', 'pixabay'],
  ['chat', 'customer service chat smartphone', 'pixabay'],
  ['social', 'social media marketing phone', 'pixabay'],
  ['review', 'happy customer review five star', 'pixabay'],
];
const mk = { unsplash: q => `https://unsplash.com/s/photos/${encodeURIComponent(q)}`, pixabay: q => `https://pixabay.com/images/search/${encodeURIComponent(q)}/` };
const marker = { unsplash: 'images.unsplash.com/photo-', pixabay: 'cdn.pixabay.com/photo' };
// Ưu tiên Chrome đã cài trên máy; không có thì dùng chromium của playwright.
let browser;
try {
  browser = await chromium.launch({ headless: true, channel: 'chrome' });
} catch {
  browser = await chromium.launch({ headless: true });
}
const page = await browser.newPage({ viewport: { width: 1400, height: 1100 }, userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36' });
const manifest = [];
for (const [tag, q, site] of jobs) {
  try {
    await page.goto(mk[site](q), { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForTimeout(3500);
    for (let i = 0; i < 2; i++) { await page.evaluate(() => window.scrollBy(0, 800)); await page.waitForTimeout(900); }
    let urls = await page.evaluate(m => [...document.images]
      .map(i => i.currentSrc || i.src)
      .filter(s => s.includes(m))
      .filter(s => !s.includes('profile') && !s.includes('_150.') && !s.includes('avatar')), marker[site]);
    urls = [...new Set(urls.map(u => site === 'unsplash' ? u.split('?')[0] + '?w=1400&q=80' : u.replace(/_\d+\.(jpg|png)/, '_1280.$1')))].slice(0, 3);
    let k = 0;
    for (const u of urls) {
      k++;
      const resp = await page.request.get(u, { timeout: 30000 }).catch(() => null);
      if (!resp || !resp.ok()) continue;
      const buf = await resp.body();
      if (buf.length < 40000) continue;
      const fn = `${tag}-${k}.jpg`;
      fs.writeFileSync(path.join(OUT, fn), buf);
      manifest.push({ file: fn, query: q, site, url: u });
      console.log('saved', fn, buf.length);
    }
  } catch (e) { console.log(tag, 'FAIL', e.message.slice(0, 60)); }
}
fs.writeFileSync(path.join(OUT, '_manifest.json'), JSON.stringify(manifest, null, 1));
await browser.close();
console.log('TOTAL', manifest.length);
