#!/usr/bin/env node
/**
 * excerpt.js — capture a paper/article excerpt image plus highlight metadata for docCard()
 *
 *   node excerpt.js <work> <url> --text "a passage from the page" [--name slug]
 *   node excerpt.js <work> <url> --selector ".css-selector" [--name slug]
 *   node excerpt.js <work> --pdf /path/paper.pdf --page 3 --rect x,y,w,h [--name slug]
 *
 * Writes <work>/excerpts/<name>.png (URL mode: the element's box + 24px padding at 2x pixels;
 * PDF mode: the --rect crop of a 200-DPI page render), rewrites <work>/excerpts.js as
 * window.EXCERPTS with the highlight rectangle as 0–1 fractions of the image, and appends the
 * source to <work>/credits.json marked unlicensed — a quoted excerpt carries no licence.
 */
const path = require('path');
const fs = require('fs');
const { spawnSync } = require('child_process');
const { chromium } = require(path.join(__dirname, 'node_modules', 'playwright-core'));

const VIEWPORT = { width: 1280, height: 900 };
const PADDING = 24;
const PDF_DPI = 200;

function fail(message, next) {
  console.error(message);
  if (next) console.error(`Next: ${next}`);
  process.exit(1);
}

function usage(message) {
  console.error(message);
  console.error('Usage: excerpt.js <work> <url> --text "passage" | --selector <css> | --pdf <file> --page <n> --rect x,y,w,h [--name slug]');
  process.exit(1);
}

function parseArgs(argv) {
  const positional = [];
  const flags = {};
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg.startsWith('--')) {
      const key = arg.slice(2);
      if (!['text', 'selector', 'name', 'pdf', 'page', 'rect'].includes(key)) usage(`Unknown flag: ${arg}`);
      if (i + 1 >= argv.length) usage(`${arg} needs a value`);
      flags[key] = argv[++i];
    } else {
      positional.push(arg);
    }
  }
  return { positional, flags };
}

function slugify(text) {
  const slug = String(text).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40).replace(/-+$/g, '');
  return /^[a-z0-9]/.test(slug) ? slug : `excerpt-${slug || 'untitled'}`;
}

function checkName(work, name) {
  if (!/^[a-z0-9][a-z0-9-]*$/.test(name)) {
    fail(`--name must be lowercase letters, digits and dashes, got ${name}`, 'e.g. --name smith-2024-findings');
  }
  const existing = readExcerpts(work);
  if (existing[name]) {
    fail(`excerpts.js already has an excerpt named "${name}"`, 'pass --name to choose another, or delete the old entry and its PNG first');
  }
}

function pngSize(file) {
  const buf = fs.readFileSync(file);
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

// excerpts.js is data the composition loads, so a partial write would break the render: tmp + rename
function readExcerpts(work) {
  const file = path.join(work, 'excerpts.js');
  if (!fs.existsSync(file)) return {};
  const match = fs.readFileSync(file, 'utf8').match(/window\.EXCERPTS\s*=\s*(\{[\s\S]*\})\s*;?\s*$/);
  try {
    return match ? JSON.parse(match[1]) : {};
  } catch {
    fail(`${file} does not parse — fix or delete it before adding another excerpt`);
  }
}

function writeExcerpts(work, excerpts) {
  const file = path.join(work, 'excerpts.js');
  const tmp = file + '.tmp';
  fs.writeFileSync(tmp, `window.EXCERPTS = ${JSON.stringify(excerpts, null, 2)};\n`);
  fs.renameSync(tmp, file);
}

// Same entry shape find_media.py's append_credit writes, so the report reads one list
function appendCredit(work, credit) {
  const file = path.join(work, 'credits.json');
  const credits = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : [];
  fs.writeFileSync(file, JSON.stringify([...credits.filter(c => c.file !== credit.file), credit], null, 2) + '\n');
}

const clamp01 = v => Math.min(1, Math.max(0, v));
const fraction = v => Number(clamp01(v).toFixed(4));

async function captureUrl(work, url, flags, name) {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: VIEWPORT, deviceScaleFactor: 2 });
    try {
      await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
    } catch (e) {
      fail(`failed to load ${url}: ${e.message.split('\n')[0]}`, 'check the URL and your connection, or capture the passage from another page');
    }
    // Animations must not move the passage between measurement and screenshot
    await page.addStyleTag({ content: '*, *::before, *::after { animation: none !important; transition: none !important; }' });
    await page.evaluate(() => document.fonts.ready);

    const found = flags.text !== undefined
      ? await page.evaluate(passage => {
          const target = passage.replace(/\s+/g, ' ').trim();
          const visible = el => {
            const style = getComputedStyle(el);
            return style.visibility !== 'hidden' && style.display !== 'none' && el.getClientRects().length > 0;
          };
          // Concatenate every visible text node into one whitespace-normalised string, keeping a
          // map from each normalised character back to its (node, offset) so the hit becomes a Range
          const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
            acceptNode: node => (node.parentElement && visible(node.parentElement) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT),
          });
          let text = '';
          const map = [];
          const push = (node, offset) => { text += ' '; map.push({ node, offset }); };
          let node;
          while ((node = walker.nextNode())) {
            const raw = node.nodeValue;
            for (let i = 0; i < raw.length; i++) {
              if (/\s/.test(raw[i])) {
                if (text.length && !text.endsWith(' ')) push(node, i);
              } else {
                text += raw[i];
                map.push({ node, offset: i });
              }
            }
            // Block boundaries join words without whitespace in the DOM ("one</p><p>two")
            if (text.length && !text.endsWith(' ') && /^(block|list-item|table|flex|grid)/.test(getComputedStyle(node.parentElement).display)) {
              push(node, raw.length - 1);
            }
          }
          const start = text.indexOf(target);
          if (start < 0) return null;
          const first = map[start], last = map[start + target.length - 1];
          const range = document.createRange();
          range.setStart(first.node, first.offset);
          range.setEnd(last.node, last.offset + 1);
          const container = range.commonAncestorContainer;
          const element = container.nodeType === 1 ? container : container.parentElement;
          element.scrollIntoView({ block: 'center', inline: 'nearest' });
          const box = element.getBoundingClientRect();
          return {
            box: { x: box.left, y: box.top, w: box.width, h: box.height },
            rects: [...range.getClientRects()].filter(r => r.width > 0 && r.height > 0)
              .map(r => ({ x: r.left, y: r.top, w: r.width, h: r.height })),
            vw: innerWidth, vh: innerHeight,
          };
        }, flags.text)
      : await page.evaluate(selector => {
          const element = document.querySelector(selector);
          if (!element) return null;
          const style = getComputedStyle(element);
          if (style.visibility === 'hidden' || style.display === 'none' || !element.getClientRects().length) return null;
          element.scrollIntoView({ block: 'center', inline: 'nearest' });
          const box = element.getBoundingClientRect();
          return {
            box: { x: box.left, y: box.top, w: box.width, h: box.height },
            rects: [{ x: box.left, y: box.top, w: box.width, h: box.height }],
            vw: innerWidth, vh: innerHeight,
          };
        }, flags.selector);

    if (!found) {
      const what = flags.text !== undefined ? `the passage "${flags.text.slice(0, 60)}${flags.text.length > 60 ? '…' : ''}"` : `a visible match for "${flags.selector}"`;
      fail(`no visible element on ${url} contains ${what}`,
        flags.text !== undefined ? 'copy the passage exactly as the page shows it (whitespace is normalised), or use --selector' : 'check the selector in the browser console first');
    }
    if (found.box.w < 2 || found.box.h < 2) {
      fail(`the match on ${url} measures ${Math.round(found.box.w)}x${Math.round(found.box.h)} px — nothing to capture`, 'pick a larger passage or a different selector');
    }

    const clip = {
      x: Math.max(0, Math.floor(found.box.x - PADDING)),
      y: Math.max(0, Math.floor(found.box.y - PADDING)),
      width: Math.min(found.vw, Math.ceil(found.box.x + found.box.w + PADDING)) - Math.max(0, Math.floor(found.box.x - PADDING)),
      height: Math.min(found.vh, Math.ceil(found.box.y + found.box.h + PADDING)) - Math.max(0, Math.floor(found.box.y - PADDING)),
    };
    if (!found.rects.length) {
      fail(`the passage on ${url} has no measurable text rectangles`, 'use --selector to capture the element instead');
    }
    // A multi-line match yields one rect per line; the highlight is their union
    const union = {
      x: Math.min(...found.rects.map(r => r.x)),
      y: Math.min(...found.rects.map(r => r.y)),
      right: Math.max(...found.rects.map(r => r.x + r.w)),
      bottom: Math.max(...found.rects.map(r => r.y + r.h)),
    };
    const highlight = {
      x: fraction((union.x - clip.x) / clip.width),
      y: fraction((union.y - clip.y) / clip.height),
      w: fraction((union.right - union.x) / clip.width),
      h: fraction((union.bottom - union.y) / clip.height),
    };

    const out = path.join(work, 'excerpts', `${name}.png`);
    fs.mkdirSync(path.dirname(out), { recursive: true });
    await page.screenshot({ path: out, clip, type: 'png' });
    const title = await page.title();
    return {
      highlight,
      source: { url, title: title || url, licence: 'unlicensed' },
      credit: { title: title || url, author: new URL(url).host.replace(/^www\./, ''), license: 'unknown (web excerpt)', source: url },
      host: new URL(url).host,
    };
  } finally {
    await browser.close();
  }
}

function capturePdf(work, flags, name) {
  if (!fs.existsSync(flags.pdf)) {
    fail(`No such PDF: ${flags.pdf}`, 'pass the full path with --pdf');
  }
  if (spawnSync('pdftoppm', ['-v'], { stdio: 'ignore' }).error) {
    fail('pdftoppm not found — install poppler-utils (apt) or poppler (brew)');
  }
  const page = Number(flags.page);
  if (!Number.isInteger(page) || page < 1) {
    fail(`--page must be a page number, got ${flags.page}`, 'e.g. --page 3');
  }
  const rect = String(flags.rect || '').split(',').map(Number);
  if (rect.length !== 4 || rect.some(v => !Number.isFinite(v) || v < 0) || rect[2] < 1 || rect[3] < 1) {
    fail(`--rect must be x,y,w,h in pixels at ${PDF_DPI} DPI, got ${flags.rect}`, 'e.g. --rect 120,300,1450,220');
  }
  const excerptsDir = path.join(work, 'excerpts');
  fs.mkdirSync(excerptsDir, { recursive: true });
  const out = path.join(excerptsDir, `${name}.png`);
  const tmpPrefix = path.join(excerptsDir, `.${name}.tmp`);
  // pdftoppm crops at render resolution, so --rect is passed straight through
  const run = spawnSync('pdftoppm', ['-f', String(page), '-l', String(page), '-r', String(PDF_DPI),
    '-png', '-singlefile', '-x', String(rect[0]), '-y', String(rect[1]), '-W', String(rect[2]), '-H', String(rect[3]),
    flags.pdf, tmpPrefix], { encoding: 'utf8' });
  if (run.status !== 0 || !fs.existsSync(`${tmpPrefix}.png`)) {
    fs.rmSync(`${tmpPrefix}.png`, { force: true });
    fail(`pdftoppm failed on ${flags.pdf}: ${(run.stderr || 'unknown error').trim().split('\n')[0]}`,
      `check that page ${page} exists and the rect fits inside it (at ${PDF_DPI} DPI a page is ${Math.round(8.5 * PDF_DPI)} px wide for US letter)`);
  }
  fs.renameSync(`${tmpPrefix}.png`, out);
  const title = path.basename(flags.pdf);
  return {
    // The crop is the excerpt, so the highlight covers the whole image
    highlight: { x: 0, y: 0, w: 1, h: 1 },
    source: { url: flags.pdf, title, licence: 'unlicensed' },
    credit: { title, author: 'unknown', license: 'unknown (PDF excerpt)', source: flags.pdf },
    host: title,
  };
}

(async () => {
  const { positional, flags } = parseArgs(process.argv.slice(2));
  const [work, url] = positional;
  if (!work) usage('excerpt.js needs a work directory');

  const modes = [Boolean(url), Boolean(flags.pdf)].filter(Boolean).length;
  if (modes !== 1) usage('give either a <url> or --pdf, not both');
  if (flags.pdf && (flags.text !== undefined || flags.selector !== undefined)) usage('--pdf takes --page and --rect, not --text/--selector');
  if (url && (flags.page !== undefined || flags.rect !== undefined)) usage('a URL takes --text or --selector, not --page/--rect');
  if (url && (flags.text === undefined) === (flags.selector === undefined)) usage('a URL needs exactly one of --text or --selector');
  if (flags.pdf && (flags.page === undefined || flags.rect === undefined)) usage('--pdf needs --page and --rect, e.g. --pdf paper.pdf --page 3 --rect 120,300,1450,220');

  const name = flags.name || slugify(flags.text || url || flags.pdf);
  checkName(work, name);

  const captured = flags.pdf ? capturePdf(work, flags, name) : await captureUrl(work, url, flags, name);

  const relImage = `excerpts/${name}.png`;
  const excerpts = readExcerpts(work);
  for (const key of Object.keys(excerpts)) {
    if (!fs.existsSync(path.join(work, excerpts[key].image))) delete excerpts[key]; // a deleted PNG leaves a dead entry
  }
  excerpts[name] = { image: relImage, highlight: captured.highlight, source: captured.source };
  writeExcerpts(work, excerpts);

  appendCredit(work, {
    file: relImage, title: captured.credit.title, author: captured.credit.author,
    license: captured.credit.license, source: captured.credit.source, section: null, unlicensed: true,
  });

  const size = pngSize(path.join(work, relImage));
  console.log(`excerpt ${name} · ${size.width}x${size.height} px · highlight at ${Math.round(captured.highlight.y * 100)}% ↓ · ${captured.host}`);
  console.log('Next: place it with docCard() — see references/scene-blocks.md');
})().catch(e => { console.error(e.message); process.exit(1); });
