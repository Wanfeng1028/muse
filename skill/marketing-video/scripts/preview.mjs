// Frames to look at before any render: one per beat, half a beat after the
// hit (where a state has resolved), as a contact sheet per format. Also dumps
// the scene's META and CUES for audio.py, and checks a loop's seam.
// Usage: node preview.mjs [scene.built.html] [WxH ...]      default sizes 1440x1440 1080x1920
import { chromium } from "playwright";
import { execFileSync } from "child_process";
import { mkdirSync, rmSync, writeFileSync } from "fs";
import path from "path";

// arguments in any order: sizes look like 1920x1080, anything else is the scene
const argv = process.argv.slice(2), isSize = (a) => /^\d+x\d+$/.test(a);
const html = path.resolve(argv.find((a) => !isSize(a)) || "scene.built.html");
const sizes = (argv.some(isSize) ? argv.filter(isSize) : ["1440x1440", "1080x1920"])
  .map((s) => s.split("x").map(Number));
mkdirSync("preview", { recursive: true });
mkdirSync("audio", { recursive: true });

const browser = await chromium.launch();
const problems = [];
for (const [W, H] of sizes) {
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  page.on("console", (m) => { if (["warning", "error"].includes(m.type())) problems.push(`${W}x${H} console: ${m.text()}`); });
  page.on("pageerror", (e) => problems.push(`${W}x${H} page error: ${e.message}`));
  await page.goto("file://" + html);
  await page.evaluate(() => document.fonts.ready);
  const meta = await page.evaluate(() => window.META);
  writeFileSync("audio/meta.json", JSON.stringify(meta, null, 2));
  writeFileSync("audio/cues.json", JSON.stringify(await page.evaluate(() => window.CUES || []), null, 2));
  const settle = () => page.evaluate(() => Promise.all([...document.images]
    .filter((i) => i.getAttribute("src")).map((i) => i.decode().catch(() => {}))));
  const beat = 60 / meta.bpm, n = Math.floor(meta.dur / beat), dir = `preview/${W}x${H}`;
  rmSync(dir, { recursive: true, force: true });     // frames from a longer previous cut would join the sheet
  mkdirSync(dir, { recursive: true });
  // the scene's first font family must be an inlined face, or the render falls back silently
  const fam = await page.evaluate(() => {
    const first = (window.CONFIG?.font || "").split(",")[0].trim().replace(/['"]/g, "");
    const generic = ["system-ui", "sans-serif", "serif", "monospace", "ui-sans-serif", ""];
    return generic.includes(first) || [...document.fonts].some((f) => f.family.replace(/['"]/g, "") === first) ? null : first;
  });
  if (fam) problems.push(`${W}x${H}: font "${fam}" is not in fonts.json, so the render uses a fallback face`);
  for (let i = 0; i < n; i++) {
    await page.evaluate((t) => window.seek(t), i * beat + beat * 0.52);
    await settle();
    await page.screenshot({ path: `${dir}/${String(i).padStart(3, "0")}.png` });
  }
  if (meta.loop) {
    const shot = async (t) => { await page.evaluate((x) => window.seek(x), t); await settle(); return page.screenshot(); };
    const a = await shot(0), z = await shot(meta.dur);
    if (Buffer.compare(a, z) !== 0) problems.push(`${W}x${H}: loop seam differs (first and last frame are not identical)`);
  }
  const cols = Math.min(8, n), tile = Math.round(2000 / cols);
  execFileSync("ffmpeg", ["-v", "error", "-y", "-pattern_type", "glob", "-i", `${dir}/*.png`, "-vf",
    `scale=${tile}:-2,tile=${cols}x${Math.ceil(n / cols)}:padding=6:color=0x8a8a8a`, "-frames:v", "1",
    `preview/sheet-${W}x${H}.png`]);
  console.log(`preview/sheet-${W}x${H}.png  (${n} beats, frame i = beat i + half a beat)`);
  await page.close();
}
await browser.close();
if (problems.length) { console.log("PROBLEMS:\n" + problems.join("\n")); process.exit(1); }
console.log("no console errors");
