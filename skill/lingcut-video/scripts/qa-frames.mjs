import { PROJ, PW, CHROME, PROFILE, FFMPEG, TOOLS, WORKDIR, PROJDIR, PROBEDIR, SHOTDIR, LIB, HOMEDIR, PYTHON, DIR, SECRETS, launch, dismissModals, injectEngine, cookieHeader, sleep, CANVAS_URL, API, TASKS, PROJECT_ID } from './_config.mjs';
/**
 * 逐帧 QA：每 0.5 秒抽帧 + 拼成联络表，供识图检查。
 *
 * 用法: node qa-frames.mjs <视频文件或目录> <输出目录> [每行张数=5]
 *
 * 产出: <输出目录>/<视频名>/f_001.jpg ... 与 <输出目录>/<视频名>_sheet.jpg
 * 然后用 read_image 看联络表，按 PLAYBOOK 6.3 的清单逐条核对。
 */
import { mkdirSync, readdirSync, statSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { basename, extname, join, resolve } from 'node:path';

const SHEET_PY = join(import.meta.dirname, 'contact_sheet.py');

const [, , input, outRoot, colsArg] = process.argv;
if (!input || !outRoot) {
  console.error('用法: node qa-frames.mjs <视频文件或目录> <输出目录> [每行张数]');
  process.exit(1);
}
const cols = colsArg || '5';

if (!existsSync(FFMPEG)) {
  console.error('找不到 ffmpeg:', FFMPEG, '\n先运行: node get-ffmpeg.mjs');
  process.exit(1);
}

const videos = statSync(input).isDirectory()
  ? readdirSync(input).filter(f => /\.(mp4|mov|mkv|webm)$/i.test(f)).map(f => join(input, f))
  : [input];

let pass = 0;
for (const video of videos) {
  const name = basename(video, extname(video));
  const dir = resolve(outRoot, name);
  mkdirSync(dir, { recursive: true });

  // 2fps = 每 0.5 秒一帧
  execFileSync(FFMPEG, ['-hide_banner', '-loglevel', 'error', '-i', video,
    '-vf', 'fps=2,scale=640:-1', '-q:v', '3', join(dir, 'f_%03d.jpg'), '-y'],
    { stdio: ['ignore', 'pipe', 'pipe'] });

  const n = readdirSync(dir).filter(f => f.endsWith('.jpg')).length;
  const sheet = resolve(outRoot, `${name}_sheet.jpg`);
  execFileSync(PYTHON, [SHEET_PY, dir, sheet, cols], { stdio: ['ignore', 'pipe', 'pipe'] });

  console.log(`OK  ${name}  ${n} 帧（每 0.5 秒）→ ${sheet}`);
  pass++;
}
console.log(`\n完成 ${pass} 个视频。用 read_image 看 *_sheet.jpg 逐帧核对。`);
