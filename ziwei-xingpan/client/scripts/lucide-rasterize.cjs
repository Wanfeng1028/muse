// Lucide icon rasterizer (weapp-shippable PNGs).
// Why: WeChat <image> cannot render SVG, and Taro inlines small imported
// images as base64 (which <image> also cannot display). So each needed
// Lucide SVG (lucide-static, ISC, kept verbatim under
// src/assets/lucide/svg/) is rasterized here to a transparent 144px PNG
// (large enough to stay above Taro's 1024-byte inline limit and to stay
// crisp at 20-24pt display sizes). Four stroke tones cover every use:
// blue = light-theme primary (#346bf0), sky = dark-theme primary
// (#8db4ff), gray = inactive/secondary (#9a9ba2), white = on-gradient
// buttons (#ffffff). Re-run after adding icons to the list below.
// Run: NODE_PATH=~/workspace/muse-build/shot/node_modules node
//   scripts/lucide-rasterize.cjs   (from the client directory)
const { chromium } = require('playwright-core');
const fs = require('node:fs');
const path = require('node:path');

const HERE = __dirname;
const SVG_DIR = path.join(HERE, '..', 'src', 'assets', 'lucide', 'svg');
const OUT_DIR = path.join(HERE, '..', 'src', 'assets', 'lucide', 'png');
const SHELL = process.env.HOME + '/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell';

const ICONS = ['home', 'message-circle', 'book-open', 'user', 'users', 'user-plus', 'crown', 'coins', 'history', 'layers', 'share-2', 'clipboard-list', 'settings', 'message-square', 'info', 'layout-grid', 'log-in', 'log-out', 'refresh-cw', 'chevron-right', 'chevron-left', 'copy', 'check', 'trash-2', 'maximize-2', 'x', 'eye', 'eye-off', 'mail', 'lock', 'chrome', 'apple', 'calendar', 'map-pin', 'clock', 'sparkles', 'arrow-up', 'arrow-right', 'moon', 'sun', 'inbox', 'star', 'gift', 'pen-line', 'zap', 'save', 'search', 'plus', 'minus'];
const TONES = { blue: '#346bf0', sky: '#8db4ff', gray: '#9a9ba2', white: '#ffffff' };

async function main() {
const browser = await chromium.launch({ executablePath: SHELL, args: ['--no-sandbox'] });
fs.mkdirSync(OUT_DIR, { recursive: true });
for (const [tone, color] of Object.entries(TONES)) {
  const blocks = ICONS.map((n) => {
    const svg = fs.readFileSync(path.join(SVG_DIR, n + '.svg'), 'utf8');
    return `<div id="ic-${n}" style="width:144px;height:144px;color:${color}">${svg}</div>`;
  }).join('\n');
  const page = await browser.newPage({ viewport: { width: 1600, height: 1200 }, deviceScaleFactor: 1 });
  await page.setContent(`<html><head><style>body{margin:0}svg{width:144px;height:144px;display:block}</style></head><body>${blocks}</body></html>`);
  await page.waitForTimeout(500);
  for (const n of ICONS) {
    // omitBackground is REQUIRED: without it Playwright bakes the white
    // page background into the PNG, turning every glyph into a solid
    // white square (invisible on light bars, a white box on dark ones).
    await page.locator('#ic-' + n).screenshot({ path: path.join(OUT_DIR, n + '-' + tone + '.png'), omitBackground: true });
  }
  await page.close();
  console.log('tone done:', tone);
}
await browser.close();
const files = fs.readdirSync(OUT_DIR);
const small = files.filter((f) => fs.statSync(path.join(OUT_DIR, f)).size < 1024);
// Small files are fine: config/index.ts forces file emission for every
// image (imageUrlLoaderOption.limit = true), so none of these inlines.
console.log('png count:', files.length, 'below-1024B (harmless, config forces files):', small.length, small.join(' '));
}
main().catch((e) => { console.error(e); process.exit(1); });
