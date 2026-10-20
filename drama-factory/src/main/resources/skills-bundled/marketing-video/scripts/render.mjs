// Final render: SUB subframes per output frame, piped into ffmpeg, where tmix
// averages each group into one frame of motion blur. Duration comes from the
// scene (window.DUR), so nothing has to be re-entered here.
// Usage: node render.mjs <scene.built.html> <W> <H> <out.mp4> [audio.wav] [--fps 60] [--sub 6]
import { chromium } from "playwright";
import { spawn } from "child_process";
import path from "path";
import { existsSync } from "fs";

const args = process.argv.slice(2), opt = (k, d) => { const i = args.indexOf(k); return i < 0 ? d : Number(args[i + 1]); };
const pos = args.filter((a, i) => !a.startsWith("--") && !(i > 0 && args[i - 1].startsWith("--")));
const [html, W, H, OUT, AUDIO] = [path.resolve(pos[0]), Number(pos[1]), Number(pos[2]), pos[3], pos[4]];
const FPS = opt("--fps", 60), SUB = opt("--sub", 6);   // 4 subframes comb a fast pointer into ghosts; 6 blurs it
if (AUDIO && !existsSync(AUDIO)) { console.error(`no such audio file: ${AUDIO} (run audio.py first)`); process.exit(1); }

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
await page.goto("file://" + html);
await page.evaluate(() => document.fonts.ready);
const DUR = await page.evaluate(() => window.DUR);
const FRAMES = Math.round(DUR * FPS);

const ff = spawn("ffmpeg", [
  "-hide_banner", "-loglevel", "error", "-y",
  "-f", "image2pipe", "-framerate", String(FPS * SUB), "-i", "pipe:0",
  ...(AUDIO ? ["-i", AUDIO] : []),
  "-filter_complex",
  `[0:v]tmix=frames=${SUB}:weights='${Array(SUB).fill(1).join(" ")}',` +
  `select='eq(mod(n\\,${SUB})\\,${SUB - 1})',setpts=N/${FPS}/TB[v]`,
  "-map", "[v]", ...(AUDIO ? ["-map", "1:a", "-c:a", "aac", "-b:a", "256k", "-shortest"] : []),
  "-r", String(FPS), "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
  "-movflags", "+faststart", OUT,
], { stdio: ["pipe", "inherit", "inherit"] });
let ffCode = null, ffErr = null;
const ffDone = new Promise((res) => ff.on("close", (c) => { ffCode = c; res(c); }));
ff.stdin.on("error", (e) => { ffErr = e; });
// if ffmpeg dies mid-render, fail now instead of waiting forever for "drain"
const write = (buf) => new Promise((res, rej) => {
  if (ffCode !== null || ffErr) return rej(ffErr || new Error(`ffmpeg exited ${ffCode} mid-render`));
  if (ff.stdin.write(buf)) return res();
  ff.stdin.once("drain", res);
  ffDone.then((c) => rej(new Error(`ffmpeg exited ${c} mid-render`)));
});

const t0 = Date.now();
for (let f = 0; f < FRAMES; f++) {
  for (let k = 0; k < SUB; k++) {
    await page.evaluate((t) => window.seek(t), (f + (k + 0.5) / SUB) / FPS);
    // footage frames are <img> swapped by seek(t): decode before capture or a frame comes out blank
    await page.evaluate(() => Promise.all([...document.images]
      .filter((i) => i.getAttribute("src")).map((i) => i.decode().catch(() => {}))));
    // a stalled compositor frame (heavy 3D) must not kill a long render: wait, then retry
    let shot = null;
    for (let tries = 0; !shot; tries++) {
      try { shot = await page.screenshot({ type: "png", timeout: 120000 }); }
      catch (e) { if (tries >= 2) throw e; process.stderr.write(`  retry frame ${f}\n`); }
    }
    await write(shot);
  }
  if (f % 120 === 0) process.stderr.write(`  ${f}/${FRAMES}  ${((Date.now() - t0) / 1000).toFixed(0)}s\n`);
}
await browser.close();
ff.stdin.end();
const code = await ffDone;
if (code !== 0) throw new Error(`ffmpeg exited ${code}`);
console.log(`wrote ${OUT}  ${W}x${H}  ${DUR}s  ${((Date.now() - t0) / 1000).toFixed(0)}s`);
