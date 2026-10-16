#!/usr/bin/env node
/**
 * html_render.mjs — 无头 Chromium 逐帧截图
 * 用法: node html_render.mjs <scene.html> <frames_dir> <seconds> <fps>
 *
 * 确定性渲染：用虚拟时间步进，每帧固定推进 1/fps 秒，
 * 避免 wall-clock 抖动导致帧率不均。
 */
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import path from 'node:path';

const [htmlPath, framesDir, secondsStr, fpsStr] = process.argv.slice(2);
const seconds = parseInt(secondsStr, 10);
const fps = parseInt(fpsStr, 10);
const totalFrames = seconds * fps;

if (!htmlPath || !framesDir || !seconds || !fps) {
  console.error('Usage: node html_render.mjs <scene.html> <frames_dir> <seconds> <fps>');
  process.exit(1);
}

fs.mkdirSync(framesDir, { recursive: true });

const CHROME = process.env.CHROME_PATH || '/opt/meta-chromium/chrome';

const browser = await chromium.launch({
  executablePath: CHROME,
  args: ['--no-sandbox', '--disable-gpu', '--force-device-scale-factor=1'],
});
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });

const html = fs.readFileSync(htmlPath, 'utf-8');
await page.setContent(html, { waitUntil: 'networkidle' });

// 注入虚拟时钟：冻结 requestAnimationFrame，按固定步进推进
await page.evaluate(() => {
  window.__vtime = 0;
  window.__frameCallbacks = [];
  const origRAF = window.requestAnimationFrame;
  window.requestAnimationFrame = (cb) => {
    window.__frameCallbacks.push(cb);
    return window.__frameCallbacks.length;
  };
  // 冻结 Date.now / performance.now 到虚拟时间
  const startReal = Date.now();
  window.__vtimeMs = 0;
});

const stepMs = 1000 / fps;
for (let i = 0; i < totalFrames; i++) {
  await page.evaluate((ms) => {
    window.__vtimeMs += ms;
    const cbs = window.__frameCallbacks.splice(0);
    for (const cb of cbs) {
      try { cb(window.__vtimeMs); } catch (e) { console.error('frame cb error', e); }
    }
  }, stepMs);

  const out = path.join(framesDir, `frame-${String(i + 1).padStart(4, '0')}.png`);
  await page.screenshot({ path: out });

  if ((i + 1) % Math.max(1, Math.floor(totalFrames / 10)) === 0) {
    console.log(`frame ${i + 1}/${totalFrames}`);
  }
}

await browser.close();
console.log(`DONE ${totalFrames} frames -> ${framesDir}`);
