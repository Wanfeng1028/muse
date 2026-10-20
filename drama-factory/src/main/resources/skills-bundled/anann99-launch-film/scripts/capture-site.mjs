#!/usr/bin/env node
// Capture a marketing website for a launch film: 2× section screenshots + brand tokens + copy + logos.
//
//   node capture-site.mjs https://example.com out/site [--dark] [--pages=/,/product,/customers]
//
// Writes to <outDir>:
//   site_<page>_<NN>.png   3840×2160 screenshots, scrolling 900 CSS px per frame
//   brand.json             title, description, og:image, CSS custom properties (:root) + their sRGB hex,
//                          font families, most-used text/background colours (with hex), icon links
//   copy.txt               visible text in reading order (per page) — positioning, pillars, proof, CTAs live here
//   links.json             nav/footer links (to find /customers, /case-studies, demo, docs)
//   logo-<n>.svg           inline SVGs from the header/nav (usually the logo mark)
// Requires: npm i -D playwright && npx playwright install chromium   (run from any folder with playwright installed)
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
const url = args.find((a) => /^https?:\/\//.test(a));
const outDir = args.find((a) => !a.startsWith('--') && a !== url) || 'site';
const dark = args.includes('--dark');
const pagesArg = (args.find((a) => a.startsWith('--pages=')) || '--pages=/').slice(8);
if (!url) { console.error('usage: node capture-site.mjs <url> <outDir> [--dark] [--pages=/,/product]'); process.exit(1); }
fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2, colorScheme: dark ? 'dark' : 'light' });
const page = await ctx.newPage();

const goto = async (u) => {
  try { await page.goto(u, { waitUntil: 'networkidle', timeout: 30000 }); }
  catch { await page.goto(u, { waitUntil: 'load', timeout: 60000 }).catch(() => {}); }
  await page.waitForTimeout(2500);
};
// Privacy-preserving: try to DECLINE non-essential cookies if a banner is present.
const declineCookies = async () => {
  for (const re of [/reject all/i, /decline/i, /only necessary|necessary only|essential only/i, /deny/i]) {
    const b = page.getByRole('button', { name: re }).first();
    if (await b.isVisible().catch(() => false)) { await b.click().catch(() => {}); await page.waitForTimeout(800); return; }
  }
};

const brand = { url, pages: [] };
let copy = '';
const links = new Map();
let logoCount = 0;

for (const p of pagesArg.split(',').map((s) => s.trim()).filter(Boolean)) {
  const u = new URL(p, url).toString();
  await goto(u);
  await declineCookies();
  const slug = p === '/' ? 'home' : p.replace(/[^a-z0-9]+/gi, '_').replace(/^_|_$/g, '');

  // screenshots, scrolling through the page
  const height = await page.evaluate(() => document.documentElement.scrollHeight);
  let i = 0;
  for (let y = 0; y < height && i < 40; y += 900, i++) {
    await page.evaluate((yy) => window.scrollTo(0, yy), y);
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(outDir, `site_${slug}_${String(i).padStart(2, '0')}.png`) });
  }
  await page.evaluate(() => window.scrollTo(0, 0));

  const info = await page.evaluate(() => {
    const meta = (n) => document.querySelector(`meta[name="${n}"], meta[property="${n}"]`)?.getAttribute('content') || null;
    // CSS custom properties declared on :root / html (all same-origin stylesheets)
    const vars = {};
    for (const sheet of [...document.styleSheets]) {
      let rules;
      try { rules = sheet.cssRules; } catch { continue; }
      for (const r of [...(rules || [])]) {
        if (r.selectorText && /(^|,)\s*(:root|html)\b/.test(r.selectorText) && r.style) {
          for (const prop of [...r.style]) if (prop.startsWith('--')) vars[prop] = r.style.getPropertyValue(prop).trim();
        }
      }
    }
    const cs = getComputedStyle(document.documentElement);
    for (const prop of [...cs]) if (prop.startsWith('--') && !(prop in vars)) vars[prop] = cs.getPropertyValue(prop).trim();
    // fonts actually used + colour frequencies on visible elements
    const fonts = {}, colors = {}, bgs = {};
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) continue;
      const s = getComputedStyle(el);
      if (s.visibility === 'hidden' || s.display === 'none') continue;
      const hasText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
      if (hasText) {
        const fam = s.fontFamily.split(',')[0].replace(/["']/g, '').trim();
        fonts[fam] = (fonts[fam] || 0) + 1;
        colors[s.color] = (colors[s.color] || 0) + 1;
      }
      if (s.backgroundColor && s.backgroundColor !== 'rgba(0, 0, 0, 0)') bgs[s.backgroundColor] = (bgs[s.backgroundColor] || 0) + r.width * r.height;
    }
    // any CSS colour (lab(), oklch(), hsl(), named…) → sRGB hex via a 1-px canvas readback
    const cv = document.createElement('canvas'); cv.width = cv.height = 1;
    const cx = cv.getContext('2d', { willReadFrequently: true });
    const hex = (c) => { try { cx.clearRect(0, 0, 1, 1); cx.fillStyle = '#000'; cx.fillStyle = c; cx.fillRect(0, 0, 1, 1); const d = cx.getImageData(0, 0, 1, 1).data; return d[3] === 0 ? null : '#' + [d[0], d[1], d[2]].map((v) => v.toString(16).padStart(2, '0')).join(''); } catch { return null; } };
    const isColor = (v) => /^(#[0-9a-f]{3,8}|rgba?\(|hsla?\(|lab\(|lch\(|oklab\(|oklch\(|color\()/i.test(v.trim());
    const top = (o, n) => Object.entries(o).sort((a, b) => b[1] - a[1]).slice(0, n).map(([k, v]) => ({ value: k, hex: hex(k), weight: Math.round(v) }));
    const cssColorsHex = Object.fromEntries(Object.entries(vars).filter(([, v]) => isColor(v)).map(([k, v]) => [k, hex(v)]));
    const svgs = [...document.querySelectorAll('header svg, nav svg, [class*="logo" i] svg, a[href="/"] svg')]
      .filter((s) => s.getBoundingClientRect().width >= 14)
      .slice(0, 4)
      .map((s) => s.outerHTML);
    const linkList = [...document.querySelectorAll('a[href]')].map((a) => ({ text: (a.innerText || a.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 80), href: a.href }));
    return {
      title: document.title,
      description: meta('description') || meta('og:description'),
      ogImage: meta('og:image'),
      icons: [...document.querySelectorAll('link[rel*="icon"]')].map((l) => l.href),
      cssVars: vars,
      cssColorsHex,
      fonts: top(fonts, 8),
      textColors: top(colors, 10),
      backgrounds: top(bgs, 10),
      fontFaces: [...document.fonts].map((f) => `${f.family} ${f.weight} ${f.style}`).filter((v, i, a) => a.indexOf(v) === i).slice(0, 30),
      svgs,
      links: linkList,
      text: (document.querySelector('main') || document.body).innerText,
    };
  });
  for (const s of info.svgs) fs.writeFileSync(path.join(outDir, `logo-${++logoCount}.svg`), s);
  for (const l of info.links) if (l.href.startsWith('http')) links.set(l.href, l.text);
  copy += `\n\n===== ${u} =====\n${info.text}`;
  delete info.svgs; delete info.links; delete info.text;
  brand.pages.push({ page: u, screenshots: i, ...info });
  console.log(`captured ${u}: ${i} screenshots, ${Object.keys(info.cssVars).length} CSS vars, fonts: ${info.fonts.map((f) => f.value).join(', ')}`);
}

fs.writeFileSync(path.join(outDir, 'brand.json'), JSON.stringify(brand, null, 2));
fs.writeFileSync(path.join(outDir, 'copy.txt'), copy.trim() + '\n');
fs.writeFileSync(path.join(outDir, 'links.json'), JSON.stringify([...links].map(([href, text]) => ({ text, href })), null, 2));
console.log(`wrote ${outDir}/brand.json, copy.txt, links.json, ${logoCount} logo svg(s)`);
await browser.close();
