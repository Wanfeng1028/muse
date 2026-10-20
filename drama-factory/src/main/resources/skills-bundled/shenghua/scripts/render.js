#!/usr/bin/env node
/**
 * render.js — drive a composition deterministically in headless Chromium
 *
 *   node render.js stills <index.html> <out-dir> <t1,t2,…>
 *   node render.js frames <index.html> <out-dir> <from-frame> <to-frame> [subframes]  (to-frame is exclusive)
 *   node render.js stream <index.html> <from-frame> <to-frame> [subframes]  (PNG/JPEG bytes to stdout, image2pipe)
 *   node render.js cues   <index.html> <cues.json>
 *   node render.js check  <index.html> [report.json]
 *   node render.js board  <board.html> <board.png>      (fill_template.py --board writes board.html)
 *
 * The page must expose window.renderAt(t) and window.SFX. Viewport size is read from the
 * composition's --W / --H CSS variables so one renderer serves vertical and landscape.
 *
 * Frames render at 2x device pixels and are saved at 1x as lossless PNG (supersampled: crisp
 * edges, no JPEG chroma bleed on red text). VV_QUALITY=draft saves 1x JPEG instead, ~4x faster.
 * VV_SCALE=2 (render-frames.sh --resolution 4k, or a 4k fill's render.json) keeps the composition
 * at 1080p but saves the 2x device pixels at full size — a 2160x3840 master with no downscale.
 * VV_BLUR_SAMPLES=N overrides the subframes count when blur is on, for a fast draft approximation.
 */
const path = require('path');
const fs = require('fs');
const { chromium } = require(path.join(__dirname, 'node_modules', 'playwright-core'));

const FPS = 30;
const DRAFT = process.env.VV_QUALITY === 'draft';
// VV_SCALE=2 saves the 2x device pixels at full size (4K master); the default supersamples to 1x
const SCALE = process.env.VV_SCALE === '2' ? 2 : 1;
const [,, mode, htmlFile, target, a, b, subframeArg] = process.argv;

function usage(message) {
  console.error(message);
  console.error('Usage: render.js stills|frames|stream|cues|check|board <index.html> [out] [args]');
  process.exit(1);
}

if (!['stills', 'frames', 'stream', 'cues', 'check', 'board'].includes(mode)) usage(`Unknown mode: ${mode}`);
if (mode === 'board' && !target) usage('board needs an output path, e.g. board.png');
if (!htmlFile || !fs.existsSync(htmlFile)) usage(`No such composition: ${htmlFile}`);
// stream puts the frame range where frames puts the output dir; normalise so both modes share one range
const range = mode === 'stream' ? { from: target, to: a, sub: b } : { from: a, to: b, sub: subframeArg };
const isFrameMode = mode === 'frames' || mode === 'stream';
if (isFrameMode && (Number.isNaN(Number(range.to)) || Number.isNaN(Number(range.from)) || range.to === undefined)) {
  usage(`${mode} needs <from-frame> <to-frame> as two separate numbers, got: ${range.from} ${range.to}`);
}
let subframes = Number(range.sub ?? 1);
if (isFrameMode && !(/^\d+$/.test(String(range.sub ?? 1)) && subframes >= 1 && subframes <= 16)) {
  usage(`${mode} [subframes] must be an integer from 1 to 16, got: ${range.sub}`);
}
const blurSamplesEnv = process.env.VV_BLUR_SAMPLES;
if (blurSamplesEnv !== undefined) {
  if (!/^\d+$/.test(blurSamplesEnv) || Number(blurSamplesEnv) < 2 || Number(blurSamplesEnv) > 16) {
    usage(`VV_BLUR_SAMPLES must be an integer from 2 to 16, got: ${blurSamplesEnv}`);
  }
  if (subframes > 1) subframes = Number(blurSamplesEnv);
}

// vendor/ and kit/ link into the skill's install dir; an update moves that dir and the links
// dangle, so fail before Chromium starts with the relink command instead of a missing-font cascade
const workDir = path.dirname(path.resolve(htmlFile));
const dangling = [];
for (const name of ['vendor', 'kit']) {
  const linkPath = path.join(workDir, name);
  try {
    if (fs.lstatSync(linkPath).isSymbolicLink() && !fs.existsSync(linkPath)) {
      dangling.push(`${name}/ → ${fs.readlinkSync(linkPath)}`);
    }
  } catch { /* absent entirely is reported as a missing file once the page loads */ }
}
if (dangling.length) {
  dangling.forEach(link => console.error(`${link} is a dangling symlink: the skill's install path moved (update or copy), so its assets are gone`));
  const duration = (fs.readFileSync(htmlFile, 'utf8').match(/const D = ([\d.]+)/) || [])[1] || '<duration>';
  console.error(`Next: python3 ${path.join(__dirname, 'fill_template.py')} ${workDir} ${duration} --relink`);
  process.exit(1);
}

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--allow-file-access-from-files'] });
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: DRAFT ? 1 : 2 });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('requestfailed', request => errors.push(`missing file ${request.url()}`));
  await page.goto('file://' + path.resolve(htmlFile), { waitUntil: 'load' });
  if (!(await page.evaluate(() => typeof window.renderAt === 'function'))) {
    errors.forEach(message => console.error(`PAGE ERROR ${message}`));
    console.error('Composition did not initialise (window.renderAt is missing).');
    console.error('Next: a missing vendor/ file means setup.sh has not completed — re-run it; otherwise fix the first PAGE ERROR');
    await browser.close();
    process.exit(2);
  }
  const size = await page.evaluate(() => {
    const style = getComputedStyle(document.documentElement);
    return { width: parseInt(style.getPropertyValue('--W')), height: parseInt(style.getPropertyValue('--H')) };
  });
  await page.setViewportSize(size);
  await page.evaluate(() => document.fonts.ready);

  // Load each kit family outright: a family with no faces at all (fonts.css lost it) or a broken file would
  // otherwise render silently in a fallback face. Loading by name also covers families a theme never uses
  const unloaded = await page.evaluate(async () => {
    const missing = [];
    for (const family of (window.BRAND && window.BRAND.fonts) || []) {
      try { if (!(await document.fonts.load(`16px "${family}"`)).length) missing.push(family); }
      catch { missing.push(family); }
    }
    return missing;
  });
  if (unloaded.length && mode !== 'cues') {
    unloaded.forEach(family => console.error(`font ${family} did not load; every word in it would render in a fallback face`));
    console.error('Next: re-run setup.sh with this kit (fill_template.py links the kit into the work folder), or fix its fonts');
    await browser.close();
    process.exit(1);
  }

  if (mode === 'board') {
    await page.screenshot({ path: target, type: 'png', scale: 'css' });
    errors.forEach(message => console.error(`PAGE ERROR ${message}`));
    if (errors.length) {
      console.error('Next: fix the first PAGE ERROR, usually a kit file setup.sh has not installed');
      await browser.close();
      process.exit(1);
    }
    console.log(`brand board → ${target}`);
    console.log('Next: show the board for approval, with brand_kit.py check for the contrast report');
    await browser.close();
    process.exit(0);
  }

  if (mode === 'cues') {
    const cues = await page.evaluate(() => window.SFX);
    fs.writeFileSync(target, JSON.stringify(cues));
    console.log(`${cues.length} sound cues → ${target}`);
  }

  // Layout QA without eyes: measure every shot at 25%, 50% and 85% of its window and report what a still would show
  if (mode === 'check') {
    const shots = await page.evaluate(() => window.SHOTS || []);
    if (!shots.length) {
      console.error('No shots registered in window.SHOTS');
      console.error('Next: author the timeline with shot()/faceCam(), or re-fill the template if it predates window.SHOTS');
      await browser.close();
      process.exit(2);
    }

    const report = [];
    for (const shotWindow of shots) {
      const samples = [0.25, 0.5, 0.85].map(p => Number((shotWindow.s + p * (shotWindow.e - shotWindow.s)).toFixed(2)));
      const measured = [];
      const measureAt = async time => {
        await page.evaluate(x => window.renderAt(x), time);
        return page.evaluate(({ id, W, H }) => {
          const section = document.getElementById(id);
          if (!section) return { missing: true, overflow: [], collide: [], visible: 0 };
          const decorative = /gridbg|glow|scan|track|pkt|bars|strike|vhs|ticker/;
          const named = el => (el.id ? '#' + el.id : '.' + ((el.getAttribute('class') || el.tagName.toLowerCase()).split(' ')[0]));
          const capbox = document.getElementById('capbox');
          const capRect = capbox && capbox.style.visibility !== 'hidden' && capbox.children.length
            ? capbox.getBoundingClientRect()
            : null;
          const out = { missing: false, overflow: [], collide: [], face: [], visible: 0, head: null };
          // Presenter mode: read the keyed frame's alpha (it is already decoded) to find the speaker,
          // so text over the head is flagged but panels beside the speaker in a split layout are not
          const headBox = (() => {
            if (!document.body.classList.contains('has-presenter')) return null;
            const layer = document.getElementById('presenter');
            const img = document.getElementById('prImg');
            if (!layer || !img || !img.complete || !img.naturalWidth) return null;
            if (parseFloat(getComputedStyle(layer).opacity) < 0.5) return null;
            const sw = 96, sh = Math.max(1, Math.round(sw * img.naturalHeight / img.naturalWidth));
            const canvas = document.createElement('canvas');
            canvas.width = sw; canvas.height = sh;
            const ctx = canvas.getContext('2d', { willReadFrequently: true });
            let pixels;
            try {
              ctx.drawImage(img, 0, 0, sw, sh);
              pixels = ctx.getImageData(0, 0, sw, sh).data;
            } catch { out.head = 'unreadable'; return null; }
            let minX = sw, minY = sh, maxX = -1, maxY = -1;
            for (let y = 0; y < sh; y++) for (let x = 0; x < sw; x++) {
              if (pixels[(y * sw + x) * 4 + 3] > 40) {
                if (x < minX) minX = x; if (x > maxX) maxX = x;
                if (y < minY) minY = y; if (y > maxY) maxY = y;
              }
            }
            if (maxX < 0) return null;   // a fully transparent frame: no speaker on screen
            out.head = 'ok';
            const rect = img.getBoundingClientRect();
            const pos = getComputedStyle(img).objectPosition.split(' ').map(parseFloat);
            const scale = Math.max(rect.width / img.naturalWidth, rect.height / img.naturalHeight);
            const offX = (rect.width - img.naturalWidth * scale) * (Number.isNaN(pos[0]) ? 0.5 : pos[0] / 100);
            const offY = (rect.height - img.naturalHeight * scale) * (Number.isNaN(pos[1]) ? 0.5 : pos[1] / 100);
            const mx = fx => rect.left + offX + (fx / sw) * img.naturalWidth * scale;
            const my = fy => rect.top + offY + (fy / sh) * img.naturalHeight * scale;
            // The head is roughly the top 35% of the silhouette, middle 60% across: shoulders and
            // outstretched arms stay fair game for type
            return {
              left: mx(minX + 0.2 * (maxX - minX)), right: mx(maxX - 0.2 * (maxX - minX)),
              top: my(minY), bottom: my(minY + 0.35 * (maxY - minY)),
            };
          })();
          // Opacity multiplies down the tree: text inside a parent waiting at opacity 0 to animate in is not on screen yet
          const shownOpacity = el => {
            let opacity = 1;
            for (let node = el; node && node !== document.body; node = node.parentElement) opacity *= parseFloat(getComputedStyle(node).opacity);
            return opacity;
          };
          const seenNames = new Map();
          for (const el of section.querySelectorAll('*')) {
            // Counted before any filter so an element keeps its index whether or not it offends at this sample
            const label = named(el);
            const nth = seenNames.get(label) || 0;
            seenNames.set(label, nth + 1);
            const classes = el.getAttribute('class') || '';
            if (decorative.test(classes) || el.closest('.ticker')) continue;
            const style = getComputedStyle(el);
            if (style.visibility === 'hidden' || style.display === 'none' || shownOpacity(el) < 0.05) continue;
            const rect = el.getBoundingClientRect();
            if (rect.width < 2 || rect.height < 2) continue;
            const isText = el.children.length === 0 && el.textContent.trim().length > 0;
            const isBlock = el.tagName === 'IMG' || /card|term|logo|stamp|badge/.test(classes);
            if (!isText && !isBlock) continue;
            out.visible += 1;
            // A centred .cx block spans the whole frame even when its text runs past the edge, so
            // measure the text itself; images and cards are measured by their own box
            let box = rect;
            // A pushed-in photo overflows its frame by design; the frame clips it, so measure the frame
            const frame = el.tagName === 'IMG' ? el.parentElement : null;
            if (frame && frame !== section && getComputedStyle(frame).overflow === 'hidden') box = frame.getBoundingClientRect();
            if (isText) {
              const range = document.createRange();
              range.selectNodeContents(el);
              const textRect = range.getBoundingClientRect();
              if (textRect.width > 1 && textRect.height > 1) box = textRect;
            }
            if (box.left < -2 || box.top < -2 || box.right > W + 2 || box.bottom > H + 2) {
              out.overflow.push({ nth, item: `${label} at ${Math.round(box.left)},${Math.round(box.top)} ${Math.round(box.width)}x${Math.round(box.height)}` });
            }
            if (capRect && isText && box.left < capRect.right && box.right > capRect.left && box.top < capRect.bottom && box.bottom > capRect.top) {
              out.collide.push({ nth, item: label });
            }
            if (headBox && box.left < headBox.right && box.right > headBox.left && box.top < headBox.bottom && box.bottom > headBox.top) {
              out.face.push({ nth, item: label });
            }
          }
          return out;
        }, { id: shotWindow.id, W: size.width, H: size.height });
      };
      for (const sampleTime of samples) {
        const found = await measureAt(sampleTime);
        // An entrance in flight (slam starts at 2.4x) is past the edge for a few frames by design; only what is still out once it lands counts
        const settleTime = Math.min(sampleTime + 0.3, shotWindow.e - 0.02);
        if (found.overflow.length && settleTime > sampleTime) {
          const settled = await measureAt(settleTime);
          const identity = ({ item, nth }) => `${item.split(' at ')[0]}#${nth}`;
          const still = new Set(settled.overflow.map(identity));
          found.overflow = found.overflow.filter(entry => still.has(identity(entry)));
        }
        measured.push(found);
      }
      // One line per element, keyed by name and occurrence so a moving element merges but same-class siblings stay apart; the first box seen is shown
      const merge = key => {
        const byItem = new Map();
        measured.forEach((found, index) => found[key].forEach(({ item, nth }) => {
          const identity = `${item.split(' at ')[0]}#${nth}`;
          const entry = byItem.get(identity) || { item, times: [] };
          entry.times.push(samples[index]);
          byItem.set(identity, entry);
        }));
        return [...byItem.values()];
      };
      // Empty only counts when every sample is empty; a shot empty at 25% is still animating in
      report.push({
        ...shotWindow, samples,
        missing: measured[0].missing,
        visible: Math.max(...measured.map(found => found.visible)),
        overflow: merge('overflow'),
        collide: merge('collide'),
        face: merge('face'),
        head: measured.some(found => found.head === 'ok') ? 'ok' : measured.some(found => found.head === 'unreadable') ? 'unreadable' : null,
      });
    }

    // Glyph coverage: a character the family lacks renders silently in a fallback face, which the
    // family check above can't see; a kit fonts.fallback makes covered characters deliberate
    let fallbackFamily = null;
    try {
      const kitManifest = JSON.parse(fs.readFileSync(path.join(workDir, 'kit', 'kit.json'), 'utf8'));
      fallbackFamily = (kitManifest.families || {}).fallback || null;
    } catch { /* no kit manifest: nothing declares a fallback */ }
    const glyphs = await page.evaluate(async fallback => {
      await document.fonts.ready;
      const byFamily = new Map();
      const add = (family, s) => {
        if (!family) return;
        let set = byFamily.get(family);
        if (!set) byFamily.set(family, set = new Set());
        for (const ch of String(s)) if (ch.trim() && ch.codePointAt(0) >= 32) set.add(ch);
      };
      const firstFamily = el => (getComputedStyle(el).fontFamily.split(',')[0] || '').trim().replace(/^["']+|["']+$/g, '');
      // Script and style text never renders; a non-ASCII character in a timeline comment is not a missing glyph
      document.querySelectorAll('body *:not(script):not(style):not(noscript):not(template)').forEach(el => {
        if (!el.children.length && el.textContent.trim()) add(firstFamily(el), el.textContent);
      });
      const capbox = document.getElementById('capbox');
      const captionFamily = capbox ? firstFamily(capbox) : null;
      (window.PHRASES || []).forEach(phrase => phrase.forEach(word => add(captionFamily, word.t)));
      (window.SPEECH || []).forEach(l => add(captionFamily, l.text));
      const missing = {}, deliberate = {};
      const faces = new Set([...document.fonts].map(face => face.family));
      for (const [family, chars] of byFamily) {
        if (!faces.has(family)) continue;   // a generic or system family has no faces to test; an unloaded kit family is the loader's error, already reported
        const spec = `16px ${JSON.stringify(family)}`;
        const lacks = [];
        for (const ch of chars) {
          // load() matches subset faces (unicode-range) for the character; an empty result means no
          // face covers it, so it renders in a fallback face — check(font, text) alone can't see that
          try { if (!(await document.fonts.load(spec, ch)).length) lacks.push(ch); } catch { /* keep */ }
        }
        if (!lacks.length) continue;
        lacks.sort();
        if (!fallback) { missing[family] = lacks; continue; }
        const fbSpec = `16px ${JSON.stringify(fallback)}`;
        const covered = [];
        for (const ch of lacks) {
          try { if ((await document.fonts.load(fbSpec, ch)).length) covered.push(ch); } catch { /* keep */ }
        }
        const rest = lacks.filter(ch => !covered.includes(ch));
        if (covered.length) deliberate[family] = covered;
        if (rest.length) missing[family] = rest;
      }
      return { missing, deliberate };
    }, fallbackFamily);
    const glyphFailures = Object.keys(glyphs.missing).length;

    const flagged = report.filter(r => r.missing || !r.visible || r.overflow.length || r.collide.length || r.face.length);
    const total = key => report.reduce((sum, r) => sum + r[key].length, 0);
    if (target) fs.writeFileSync(target, JSON.stringify(report, null, 2));
    const presenterChecked = report.some(r => r.head);
    console.log(`${report.length} shots checked · ${total('overflow')} past the frame edge · ${total('collide')} caption collisions${presenterChecked ? ` · ${total('face')} on the speaker's face` : ''} · ${report.filter(r => !r.missing && !r.visible).length} empty`);
    for (const r of flagged) {
      const seen = times => `(${times.map(t => t.toFixed(2) + 's').join('·')})`;
      if (r.missing) console.log(`  ${r.id} missing — no element with that id`);
      else if (!r.visible) console.log(`  ${r.id} empty ${seen(r.samples)} — nothing visible`);
      r.overflow.forEach(({ item, times }) => console.log(`  ${r.id} past the edge: ${item} ${seen(times)}`));
      r.collide.forEach(({ item, times }) => console.log(`  ${r.id} under the captions: ${item} ${seen(times)}`));
      r.face.forEach(({ item, times }) => console.log(`  ${r.id} over the speaker's face: ${item} ${seen(times)}`));
    }
    if (presenterChecked && !report.some(r => r.head === 'ok')) {
      console.error('note: the presenter frame’s alpha was unreadable, so the face-overlap check was skipped');
    }
    for (const [family, chars] of Object.entries(glyphs.deliberate)) {
      console.log(`  font ${family} has no ${chars.join(' ')}: those render in ${fallbackFamily}, the kit's fonts.fallback (deliberate)`);
    }
    for (const [family, chars] of Object.entries(glyphs.missing)) {
      console.log(`  font ${family} lacks glyphs for: ${chars.join(' ')} — those characters render in a fallback face`);
    }
    errors.forEach(message => console.error(`PAGE ERROR ${message}`));
    await browser.close();
    if (flagged.length || errors.length || glyphFailures) {
      if (flagged.length || errors.length) console.log('Next: fix those shots (resize the type, move it inside the safe zone, or hide captions with NOCAP), then re-run check');
      if (glyphFailures) console.log(`Next: swap those characters for ones the kit covers, or give the kit a fonts.fallback family that covers them (brand.json), then re-run check`);
      process.exit(1);
    }
    console.log('Next: render stills if you can view images, then render frames');
    process.exit(0);
  }

  if (mode === 'stills') {
    fs.mkdirSync(target, { recursive: true });
    if (!a) {
      usage('stills needs a comma-separated timestamp list');
    }
    const times = a.split(',').map(s => Number(s.trim())).filter(t => !Number.isNaN(t));
    if (!times.length) {
      usage('stills timestamp list parsed to zero valid numbers');
    }
    for (const t of times) {
      await page.evaluate(x => window.renderAt(x), t);
      await page.screenshot({ path: path.join(target, `t${String(t.toFixed(2)).padStart(7, '0')}.jpg`), type: 'jpeg', quality: 85, scale: 'css' });
    }
    console.log(`${times.length} stills → ${target}`);
  }

  // stream mode pipes the same frames to stdout as image2pipe input, so stdout must carry frame
  // bytes only: every message goes to stderr, and backpressure waits for the encoder to drain
  const writeFrame = mode === 'stream'
    ? buf => (process.stdout.write(buf) ? Promise.resolve() : new Promise(resolve => process.stdout.once('drain', resolve)))
    : null;
  if (mode === 'stream') {
    process.stdout.on('error', e => { console.error(`stdout pipe failed: ${e.message}`); process.exit(1); });
  }

  if (isFrameMode && subframes === 1) {
    if (mode === 'frames') fs.mkdirSync(target, { recursive: true });
    const [ext, other] = DRAFT ? ['jpg', 'png'] : ['png', 'jpg'];
    for (let f = Number(range.from); f < Number(range.to); f++) {
      await page.evaluate(x => window.renderAt(x), f / FPS);
      // 'device' keeps the 2x pixels (4K); 'css' supersamples them to 1x. dsf is 1 under DRAFT,
      // so 'device' still yields a 1x draft frame
      const shot = { scale: SCALE === 2 ? 'device' : 'css', ...(DRAFT ? { type: 'jpeg', quality: 92 } : { type: 'png' }) };
      if (mode === 'stream') {
        await writeFrame(await page.screenshot(shot));
      } else {
        const name = path.join(target, `f${String(f).padStart(5, '0')}`);
        await page.screenshot({ path: `${name}.${ext}`, ...shot });
        // A frame from an earlier render in the other quality would be encoded alongside this one
        fs.rmSync(`${name}.${other}`, { force: true });
      }
    }
    if (mode === 'stream') console.error(`${Number(range.to) - Number(range.from)} frames → stdout`);
  }

  if (isFrameMode && subframes > 1) {
    if (mode === 'frames') fs.mkdirSync(target, { recursive: true });
    const [ext, other] = DRAFT ? ['jpg', 'png'] : ['png', 'jpg'];
    // A scale-1 clip captures at CSS size, so the 2x page is supersampled to 1x; VV_SCALE=2
    // captures at device pixels (4K). The pixels match page.screenshot exactly and the
    // speed-optimised PNG encodes ~4x faster
    const clip = { x: 0, y: 0, width: size.width, height: size.height, scale: DRAFT ? 1 : SCALE };
    const cdp = await page.context().newCDPSession(page);
    const blend = await browser.newPage();
    // The blend canvas is the captured sub-frame's size, so 4K blends at 2x too
    await blend.evaluate(({ width, height }) => {
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      window.blendContext = canvas.getContext('2d', { willReadFrequently: true });
      window.blendSum = new Uint32Array(width * height * 4);
    }, { width: size.width * clip.scale, height: size.height * clip.scale });
    for (let f = Number(range.from); f < Number(range.to); f++) {
      await blend.evaluate(() => window.blendSum.fill(0));
      // VV_BLUR_SAMPLES may have lowered `subframes` so a draft approximates the blur cheaply
      for (let k = 0; k < subframes; k++) {
        // 180° shutter: sub-frames span half a frame, so renderAt's Math.round keeps frame f's grain and footage
        await page.evaluate(x => window.renderAt(x), f / FPS + k / (2 * subframes * FPS));
        const { data: png } = await cdp.send('Page.captureScreenshot', { format: 'png', optimizeForSpeed: true, clip });
        await blend.evaluate(async data => {
          const image = new Image();
          image.src = 'data:image/png;base64,' + data;
          await image.decode();
          const { width, height } = window.blendContext.canvas;
          if (image.naturalWidth !== width || image.naturalHeight !== height) {
            throw new Error(`sub-frame is ${image.naturalWidth}x${image.naturalHeight}, expected ${width}x${height}`);
          }
          window.blendContext.drawImage(image, 0, 0);
          const pixels = window.blendContext.getImageData(0, 0, width, height).data;
          for (let i = 0; i < pixels.length; i++) window.blendSum[i] += pixels[i];
        }, png);
      }
      const blended = await blend.evaluate(({ count, type }) => {
        const { width, height } = window.blendContext.canvas;
        const averaged = new ImageData(width, height);
        for (let i = 0; i < averaged.data.length; i++) averaged.data[i] = Math.round(window.blendSum[i] / count);
        window.blendContext.putImageData(averaged, 0, 0);
        return window.blendContext.canvas.toDataURL(type, 0.92).split(',')[1];
      }, { count: subframes, type: DRAFT ? 'image/jpeg' : 'image/png' });
      if (mode === 'stream') {
        await writeFrame(Buffer.from(blended, 'base64'));
      } else {
        const name = path.join(target, `f${String(f).padStart(5, '0')}`);
        fs.writeFileSync(`${name}.${ext}`, Buffer.from(blended, 'base64'));
        fs.rmSync(`${name}.${other}`, { force: true });
      }
    }
    if (mode === 'stream') console.error(`${Number(range.to) - Number(range.from)} frames → stdout`);
  }

  await browser.close();
  if (errors.length) {
    errors.forEach(message => console.error(`PAGE ERROR ${message}`));
    process.exit(2);
  }
})().catch(e => { console.error(e.message); process.exit(1); });
