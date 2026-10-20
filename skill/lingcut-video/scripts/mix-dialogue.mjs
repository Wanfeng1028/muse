import { PROJ, PW, CHROME, PROFILE, FFMPEG, TOOLS, WORKDIR, PROJDIR, PROBEDIR, SHOTDIR, LIB, HOMEDIR, PYTHON, DIR, SECRETS, launch, dismissModals, injectEngine, cookieHeader, sleep, CANVAS_URL, API, TASKS, PROJECT_ID } from './_config.mjs';
/**
 * 把对白音轨混进成片（时间轴对齐）
 *
 * 用法: node mix-dialogue.mjs <输入.mp4> <输出.mp4> <cues.json> [ffmpeg路径]
 * cues.json: [{ "file": "C:/.../line05.mp3", "at": 21.56, "gainDb": 2 }]
 *            at = 该句台词在成片中的起点（秒）
 *
 * 为什么需要这一步：
 *   LingCut 的音频节点只是「音色/口型参考」，模型不会把参考音频混进输出。
 *   实测：提示词里写了台词 + 连了音频参考后，模型自身音轨几乎静音
 *   （动态范围 44dB → 13dB，峰值 -21dB → -41dB）。
 *   所以对白必须由我们在后期按时间轴混入。
 */
import { readFileSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

const [inFile, outFile, cuesFile] = process.argv.slice(2);
const ffmpeg = process.argv[5] || `${TOOLS}/ffmpeg.exe`;

if (!existsSync(ffmpeg)) { console.error('找不到 ffmpeg:', ffmpeg); process.exit(1); }
const cues = JSON.parse(readFileSync(cuesFile, 'utf8').replace(/^\uFEFF/, ''));
if (!cues.length) { console.error('cues 为空'); process.exit(1); }

const args = ['-hide_banner', '-loglevel', 'warning', '-y', '-i', inFile];
cues.forEach(c => args.push('-i', c.file));

const parts = [];
const mixIns = ['[0:a]'];
cues.forEach((c, i) => {
  const ms = Math.round(c.at * 1000);
  const gain = c.gainDb != null ? `,volume=${c.gainDb}dB` : '';
  parts.push(`[${i + 1}:a]adelay=${ms}:all=1${gain}[d${i}]`);
  mixIns.push(`[d${i}]`);
});
parts.push(`${mixIns.join('')}amix=inputs=${mixIns.length}:duration=first:normalize=0[aout]`);

args.push('-filter_complex', parts.join(';'),
  '-map', '0:v', '-map', '[aout]',
  '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', outFile);

console.log('混入', cues.length, '句对白 →', outFile);
cues.forEach(c => console.log(`  +${c.at}s  ${c.file.split(/[\\/]/).pop()}`));
const out = execFileSync(ffmpeg, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
if (out) console.log(out);
console.log('✅ 完成');
