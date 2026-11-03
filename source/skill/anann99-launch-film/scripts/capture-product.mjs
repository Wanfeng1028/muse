#!/usr/bin/env node
// Capture real product UI for a launch film: 4K screenshots + per-element bounding boxes.
//
// EXPLORE a page first (prints nav/buttons/inputs + visible text, saves a 1× screenshot):
//   node capture-product.mjs --explore https://demo.example.com/app out/explore
//
// CAPTURE every story state from a config:
//   node capture-product.mjs shots.config.json public/shots
//
// shots.config.json
// {
//   "viewport": [1920, 1080], "dpr": 2, "colorScheme": "dark",
//   "storageState": "auth.json",            // OPTIONAL: a sandbox session the USER saved (never type their passwords)
//   "shots": [
//     { "name": "home",        "url": "https://demo.example.com/app" },
//     { "name": "home_review", "actions": [{ "scroll": 520 }] },                       // continues on the same page
//     { "name": "goal_blank",  "url": "https://demo.example.com/app/agents" },
//     { "name": "goal_typed",  "actions": [{ "click": "textarea" }, { "type": "Lift activation by +2pp" }] },
//     { "name": "task",        "url": "https://demo.example.com/app/task/123", "actions": [{ "clickText": "Agents" }, { "wait": 2000 }] }
//   ]
// }
// actions: {click: css} {clickText: text} {type: text} {press: key} {scroll: px} {hover: css} {wait: ms} {eval: js}
//
// Each shot writes <name>.png (viewport × dpr) and <name>.rects.json: [{tag, kind: text|card|control, text, x, y, w, h}]
// in VIEWPORT coordinates (1920×1080 space) — scene builders aim push-ins and focus rings with these.
// Capture "<input>_blank" and "<input>_typed" pairs: identical geometry → the typing animation is a pixel-exact wipe.
// Privacy: use a public demo or sandbox tenant only. Never capture real customer data, PII, keys or internal URLs.
import fs from 'fs';
import path from 'path';
import { createRequire } from 'module';
import { execSync } from 'child_process';

// Resolve Playwright from: this script's location → the current project (cwd) → the global npm root.
// (Install it in the film project: `cd video && npm i -D playwright && npx playwright install chromium`.)
const loadPlaywright = async () => {
  try { return await import('playwright'); } catch {}
  for (const base of [process.cwd(), (() => { try { return execSync('npm root -g').toString().trim(); } catch { return null; } })()]) {
    if (!base) continue;
    try { return createRequire(path.join(base, 'noop.js'))('playwright'); } catch {}
  }
  console.error('Playwright not found. Run: npm i -D playwright && npx playwright install chromium');
  process.exit(1);
};
const { chromium } = await loadPlaywright();

const args = process.argv.slice(2);
const explore = args[0] === '--explore';
fs.mkdirSync(args[explore ? 2 : 1] || 'shots', { recursive: true });

const forceVisible = async (page) => {
  // Some apps defer loading while the tab is hidden (headless/background). Pretend we're visible and focused.
  await page.evaluate(() => {
    try {
      Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' });
      Object.defineProperty(document, 'hidden', { configurable: true, get: () => false });
      document.dispatchEvent(new Event('visibilitychange'));
      window.dispatchEvent(new Event('focus'));
    } catch {}
  });
};
const goto = async (page, u) => {
  try { await page.goto(u, { waitUntil: 'networkidle', timeout: 30000 }); }
  catch { await page.goto(u, { waitUntil: 'load', timeout: 60000 }).catch(() => {}); }
  await forceVisible(page);
  await page.waitForTimeout(3000);
};
const rects = (page) => page.evaluate(({ vw, vh }) => {
  const out = [];
  for (const el of document.querySelectorAll('h1,h2,h3,h4,h5,p,span,a,button,li,td,th,label,div,code,pre,textarea,input,img,svg')) {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4 || r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw) continue;
    const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join(' ').trim();
    const isControl = ['BUTTON', 'TEXTAREA', 'INPUT'].includes(el.tagName) || el.getAttribute('role') === 'button';
    let isCard = false;
    if (!own && !isControl && el.tagName === 'DIV' && r.width > 120 && r.height > 40) {
      const s = getComputedStyle(el);
      const txt = (el.innerText || '').trim();
      isCard = txt.length > 0 && txt.length < 400 && (s.borderTopWidth !== '0px' || s.boxShadow !== 'none' || s.backgroundColor !== 'rgba(0, 0, 0, 0)');
    }
    if (!own && !isCard && !isControl) continue;
    const text = (own || el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ');
    out.push({ tag: el.tagName, kind: own ? 'text' : isCard ? 'card' : 'control', text: text.slice(0, 160), x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) });
  }
  return out;
}, { vw: page.viewportSize().width, vh: page.viewportSize().height });

const browser = await chromium.launch();

if (explore) {
  const [, url, outDir] = args;
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
  const page = await ctx.newPage();
  await goto(page, url);
  await page.screenshot({ path: path.join(outDir, 'explore.png') });
  const dump = await page.evaluate(() => ({
    url: location.href,
    links: [...document.querySelectorAll('a[href]')].map((a) => `${(a.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 60)} -> ${a.getAttribute('href')}`),
    buttons: [...document.querySelectorAll('button,[role=button]')].map((b) => (b.innerText || b.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 60)).filter(Boolean),
    inputs: [...document.querySelectorAll('input,textarea')].map((i) => `${i.tagName.toLowerCase()} placeholder="${i.placeholder || ''}"`),
    text: document.body.innerText.slice(0, 6000),
  }));
  fs.writeFileSync(path.join(outDir, 'explore.json'), JSON.stringify(dump, null, 2));
  console.log(`LINKS\n${[...new Set(dump.links)].join('\n')}\n\nBUTTONS\n${[...new Set(dump.buttons)].join(' | ')}\n\nINPUTS\n${dump.inputs.join('\n')}\n\nTEXT\n${dump.text}`);
  await browser.close();
  process.exit(0);
}

const [configPath, outDir] = args;
const cfg = JSON.parse(fs.readFileSync(configPath, 'utf8'));
const [vw, vh] = cfg.viewport || [1920, 1080];
const ctx = await browser.newContext({
  viewport: { width: vw, height: vh },
  deviceScaleFactor: cfg.dpr || 2,
  colorScheme: cfg.colorScheme || 'dark',
  ...(cfg.storageState ? { storageState: cfg.storageState } : {}),
});
const page = await ctx.newPage();
for (const shot of cfg.shots) {
  try {
    if (shot.url) await goto(page, shot.url);
    for (const a of shot.actions || []) {
      if (a.click) await page.locator(a.click).first().click({ timeout: 8000 });
      else if (a.clickText) await page.getByText(a.clickText, { exact: !!a.exact }).first().click({ timeout: 8000 });
      else if (a.type) await page.keyboard.type(a.type, { delay: 20 });
      else if (a.press) await page.keyboard.press(a.press);
      else if (a.scroll) { await page.mouse.move(vw * 0.6, vh * 0.55); await page.mouse.wheel(0, a.scroll); }
      else if (a.hover) await page.locator(a.hover).first().hover();
      else if (a.eval) await page.evaluate(a.eval);
      await page.waitForTimeout(a.wait ?? 900);
    }
    await page.mouse.move(vw - 5, vh - 5); // keep the real cursor/hover states out of frame
    await forceVisible(page);
    await page.waitForTimeout(shot.settle ?? 1200);
    await page.screenshot({ path: path.join(outDir, `${shot.name}.png`), fullPage: !!shot.fullPage });
    const r = await rects(page);
    fs.writeFileSync(path.join(outDir, `${shot.name}.rects.json`), JSON.stringify(r));
    console.log(`saved ${shot.name} (${r.length} rects)`);
  } catch (e) {
    console.log(`FAIL ${shot.name}: ${e.message.split('\n')[0]}`);
  }
}
await browser.close();
