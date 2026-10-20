import { PROJ, PW, CHROME, PROFILE, FFMPEG, TOOLS, WORKDIR, PROJDIR, PROBEDIR, SHOTDIR, LIB, HOMEDIR, PYTHON, DIR, SECRETS, launch, dismissModals, injectEngine, cookieHeader, sleep, CANVAS_URL, API, TASKS, PROJECT_ID } from './_config.mjs';
/**
 * 获取静态 ffmpeg（Windows 无预装）
 *
 * 用法: node get-ffmpeg.mjs [输出目录]
 *
 * ⚠️ GitHub 直连极慢（实测 15 分钟没下完），必须用 npmmirror 镜像（实测 12 秒）。
 */
import { writeFileSync, mkdirSync, statSync, existsSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';

const OUT = process.argv[2] || TOOLS;
mkdirSync(OUT, { recursive: true });
const target = OUT + '/ffmpeg.exe';

if (existsSync(target)) {
  console.log('已存在:', target, (statSync(target).size / 1024 / 1024).toFixed(1), 'MB');
  process.exit(0);
}

const urls = [
  'https://registry.npmmirror.com/-/binary/ffmpeg-static/b6.1.1/ffmpeg-win32-x64.gz',
  'https://cdn.npmmirror.com/binaries/ffmpeg-static/b6.1.1/ffmpeg-win32-x64.gz',
];

for (const url of urls) {
  const t0 = Date.now();
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 120000);
    const r = await fetch(url, { signal: ctrl.signal, redirect: 'follow' });
    clearTimeout(timer);
    if (!r.ok) { console.log(`SKIP ${r.status}  ${url}`); continue; }
    const gz = Buffer.from(await r.arrayBuffer());
    console.log(`下载完成 ${(gz.length / 1024 / 1024).toFixed(1)}MB，用时 ${((Date.now() - t0) / 1000).toFixed(1)}s`);
    writeFileSync(target, gunzipSync(gz));
    console.log('saved', target, (statSync(target).size / 1024 / 1024).toFixed(1), 'MB');
    break;
  } catch (e) {
    console.log(`ERR  ${url}  ${e.message}`);
  }
}
