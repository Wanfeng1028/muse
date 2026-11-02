// One-off rasterizer for the HealthChat verbatim port (2026-11-02).
// Standard 4 tones for the 3 new library icons (list, calendar, mic),
// plus 4 reference-exact one-off tones used ONLY by the verbatim port
// chips/send (kept under png/ref/, not in the library map):
//   list-red #df6a6a, message-square-green #5b9c70,
//   calendar-amber #d8a52c, arrow-dark #2b3036.
// Same technique as scripts/lucide-rasterize.cjs (Playwright headless
// shell, omitBackground for true transparency).
const { chromium } = require('playwright-core');
const fs = require('node:fs');
const path = require('node:path');
const HERE = __dirname;
const SVG_DIR = path.join(HERE, '..', 'src', 'assets', 'lucide', 'svg');
const PNG_DIR = path.join(HERE, '..', 'src', 'assets', 'lucide', 'png');
const SHELL = process.env.HOME + '/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell';
const TONES = { blue: '#346bf0', sky: '#8db4ff', gray: '#9a9ba2', white: '#ffffff' };
const STANDARD = ['list', 'calendar', 'mic'];
const REF = [
  ['list', '#df6a6a', 'ref/list-red.png'],
  ['message-square', '#5b9c70', 'ref/message-square-green.png'],
  ['calendar', '#d8a52c', 'ref/calendar-amber.png'],
  ['arrow-up', '#2b3036', 'ref/arrow-dark.png'],
];
async function main() {
  const browser = await chromium.launch({ executablePath: SHELL, args: ['--no-sandbox'] });
  const jobs = [];
  for (const n of STANDARD) {
    const svg = fs.readFileSync(path.join(SVG_DIR, n + '.svg'), 'utf8');
    for (const [tone, color] of Object.entries(TONES)) {
      jobs.push({ svg, color, out: path.join(PNG_DIR, n + '-' + tone + '.png') });
    }
  }
  for (const [n, color, rel] of REF) {
    const svg = fs.readFileSync(path.join(SVG_DIR, n + '.svg'), 'utf8');
    jobs.push({ svg, color, out: path.join(PNG_DIR, rel) });
  }
  fs.mkdirSync(path.join(PNG_DIR, 'ref'), { recursive: true });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1200 }, deviceScaleFactor: 1 });
  for (let i = 0; i < jobs.length; i++) {
    const j = jobs[i];
    await page.setContent(`<html><head><style>body{margin:0}svg{width:144px;height:144px;display:block}</style></head><body><div id="ic" style="width:144px;height:144px;color:${j.color}">${j.svg}</div></body></html>`);
    await page.waitForTimeout(200);
    await page.locator('#ic').screenshot({ path: j.out, omitBackground: true });
    const sz = fs.statSync(j.out).size;
    console.log(path.relative(PNG_DIR, j.out), sz, 'bytes');
    if (sz < 500) { console.error('SUSPICIOUSLY SMALL:', j.out); process.exitCode = 1; }
  }
  await browser.close();
}
main().catch((e) => { console.error(e); process.exit(1); });
