import { PROJ, PW, CHROME, PROFILE, FFMPEG, TOOLS, WORKDIR, PROJDIR, PROBEDIR, SHOTDIR, LIB, HOMEDIR, PYTHON, DIR, SECRETS, launch, dismissModals, injectEngine, cookieHeader, sleep, CANVAS_URL, API, TASKS, PROJECT_ID } from './_config.mjs';
/**
 * 把多个分镜视频无损拼成成片
 *
 * 用法: node concat.mjs <片段列表.json> <输出.mp4> [ffmpeg路径]
 * 片段列表.json: ["C:/.../video-01.mp4", "C:/.../video-02.mp4", ...]   （按顺序）
 *
 * 前提: 所有片段的编码参数一致。
 *   lingcut 出的片统一为 h264 High / yuv420p / 1280x720 / 24fps / AAC 32kHz，
 *   因此 -c copy 无损拼接可直接用。
 *   若参数不一致，改用: -c:v libx264 -crf 18 -c:a aac
 */
import { writeFileSync, readFileSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

const [listFile, outFile] = process.argv.slice(2);
const ffmpeg = process.argv[4] || `${TOOLS}/ffmpeg.exe`;

if (!existsSync(ffmpeg)) {
  console.error('找不到 ffmpeg:', ffmpeg, '\n先运行: node get-ffmpeg.mjs');
  process.exit(1);
}

const clips = JSON.parse(readFileSync(listFile, 'utf8').replace(/^\uFEFF/, ''));
const listPath = listFile.replace(/\.json$/, '') + '.txt';
writeFileSync(listPath, clips.map(p => `file '${p.replace(/\\/g, '/')}'`).join('\n') + '\n', 'utf8');

console.log('拼接', clips.length, '个片段 →', outFile);
const args = ['-hide_banner', '-loglevel', 'warning',
  '-f', 'concat', '-safe', '0', '-i', listPath,
  '-c', 'copy', '-movflags', '+faststart', '-y', outFile];
const out = execFileSync(ffmpeg, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
if (out) console.log(out);

// 回读校验
// ⚠️ ffmpeg 纯探测（-i 但不给输出文件）会以退出码 1 结束，execFileSync 会抛异常，必须捕获
let probe = '';
try {
  probe = execFileSync(ffmpeg, ['-hide_banner', '-i', outFile], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
} catch (e) {
  probe = String(e.stderr || '') + String(e.stdout || '');
}
const info = (probe.match(/Duration: [\d:.]+/) || [])[0];
const streams = (probe.match(/Stream #\d+:\d+.*/g) || []).map(s => s.trim());
console.log('✅', info || '(未能解析时长)');
streams.forEach(s => console.log('  ', s));
