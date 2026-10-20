import { PROJ, PW, CHROME, PROFILE, FFMPEG, TOOLS, WORKDIR, PROJDIR, PROBEDIR, SHOTDIR, LIB, HOMEDIR, PYTHON, DIR, SECRETS, launch, dismissModals, injectEngine, cookieHeader, sleep, CANVAS_URL, API, TASKS, PROJECT_ID } from './_config.mjs';
﻿/**
 * 最终重拼：画布集合 + 本地补充（A01/A11/T09 + D05/L11 的 20 秒版）
 *  + 混回旧章的旁白音轨
 *
 * 用法: node rebuild3.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const FF = FFMPEG;
const SRC = ROOT + '/★网站最新/视频';
const STAGE = ROOT + '/_final';
fs.rmSync(STAGE, { recursive: true, force: true });
fs.mkdirSync(STAGE, { recursive: true });

const UNIT_ORDER = ['楔子','第一章','第二章','第三章','第四章','第五章','第六章','第七章','第八章','第九章','第十章',
  '第十一章','第十二章','第十三章','第十四章','第十五章','第十六章','第十七章','第十八章','尾声'];

// ★ 本地补充：画布上没有的镜头
const SUPPLEMENT = [
  { unit: '楔子',   shot: 'A01', file: ROOT + '/06-楔子视频-v2/A01-全黑醒木.mp4' },
  // ★ A10：楔子的悬念钩子（14s，本地尾帧接续拼成 17s）
  { unit: '楔子',   shot: 'A10', file: ROOT + '/_tmp/A10-22s.mp4' },
  { unit: '楔子',   shot: 'A11', file: ROOT + '/06-楔子视频-v2/A11-片名字卡.mp4' },
  // ★ F10：守灯婆婆添灯油（5s）
  { unit: '第五章', shot: 'F10', file: ROOT + '/_tmp/F10.mp4' },
  { unit: '尾声',   shot: 'T09', file: ROOT + '/20-三卷视频/T09-片名字卡.mp4' },
  // ★ 20 秒版（本地拼接，画布上是 12s 前半段）
  { unit: '第三章', shot: 'D05', file: ROOT + '/_tmp/D05-split.mp4', override: true },
  { unit: '第十一章', shot: 'L11', file: ROOT + '/_tmp/L11-20s.mp4', override: true },
];

// ── 收集 ──────────────────────────────────────
const groups = {};
for (const f of fs.readdirSync(SRC)) {
  if (!f.endsWith('.mp4')) continue;
  const m = f.match(/^(\d+)_(.+?) ([A-Z]\d\d)(?:_(.*?))?\.mp4$/);
  if (!m) continue;
  const [, seq, unit, shot, title] = m;
  if (!UNIT_ORDER.includes(unit)) continue;
  (groups[unit] = groups[unit] || []).push({ shot, seq: +seq, title: title || '', file: path.join(SRC, f), from: 'canvas' });
}
for (const s of SUPPLEMENT) {
  if (!fs.existsSync(s.file)) { console.log(`⚠️ 补充文件不存在: ${s.file}`); continue; }
  const g = (groups[s.unit] = groups[s.unit] || []);
  const i = g.findIndex(x => x.shot === s.shot);
  if (i >= 0) {
    if (s.override) { g[i] = { shot: s.shot, seq: 0, title: g[i].title, file: s.file, from: 'local★' }; }
  } else {
    g.push({ shot: s.shot, seq: 0, title: '', file: s.file, from: 'local' });
  }
}

function dur(f) {
  try { execFileSync(FF, ['-hide_banner','-i',f], { encoding: 'utf8', stdio: ['ignore','pipe','pipe'] }); }
  catch (e) {
    const m = String(e.stderr || '').match(/Duration: (\d+):(\d+):([\d.]+)/);
    return m ? +m[1] * 3600 + +m[2] * 60 + +m[3] : 0;
  }
  return 0;
}
function norm(src, dst) {
  execFileSync(FF, ['-hide_banner','-loglevel','error','-y','-fflags','+genpts','-avoid_negative_ts','make_zero','-i',src,
    '-c:v','libx264','-preset','veryfast','-crf','20','-r','24','-vf','scale=1280:720,setsar=1','-pix_fmt','yuv420p',
    '-c:a','aac','-ar','32000','-ac','2', dst]);
}
function concat(list, out) {
  const txt = STAGE + '/_l.txt';
  fs.writeFileSync(txt, list.map(f => `file '${f.replace(/\\/g, '/')}'`).join('\n'), 'utf8');
  execFileSync(FF, ['-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',txt,'-c','copy',out]);
}
// 把旧章的旁白音轨套到新画面上（新画面更长则音频后面补静音）
function muxNarration(video, narrationSrc, out) {
  if (!narrationSrc || !fs.existsSync(narrationSrc)) { fs.copyFileSync(video, out); return false; }
  const vd = dur(video);
  execFileSync(FF, ['-hide_banner','-loglevel','error','-y','-i',video,'-i',narrationSrc,
    '-filter_complex', `[1:a]apad=whole_dur=${vd}[a]`, '-map','0:v','-map','[a]',
    '-c:v','copy','-c:a','aac','-ar','32000','-ac','2','-shortest', out]);
  return true;
}

// 旧章（带旁白）路径
const OLD = {
  '楔子':   ROOT + '/13-第一卷成片/楔子_带旁白_v3.mp4',
  '第一章': ROOT + '/13-第一卷成片/第一章_带旁白.mp4',
  '第二章': ROOT + '/13-第一卷成片/第二章_带旁白.mp4',
  '第三章': ROOT + '/13-第一卷成片/第三章_带旁白.mp4',
  '第四章': ROOT + '/13-第一卷成片/_ch4-第四章.mp4',
  '第五章': ROOT + '/13-第一卷成片/第五章_带旁白.mp4',
  '第六章': ROOT + '/18-二卷成片/第六章_宋铁生_带旁白.mp4',
  '第七章': ROOT + '/18-二卷成片/第七章_两次真话_带旁白.mp4',
  '第八章': ROOT + '/18-二卷成片/第八章_北原的灯.mp4',
  '第九章': ROOT + '/18-二卷成片/第九章_长命锁.mp4',
  '第十章': ROOT + '/18-二卷成片/第十章_老仵作.mp4',
  '第十一章': ROOT + '/18-二卷成片/第十一章_小马.mp4',
  '第十二章': ROOT + '/18-二卷成片/第十二章_北原来的女人.mp4',
  '第十三章': ROOT + '/18-二卷成片/第十三章_地址有了.mp4',
  '第十四章': ROOT + '/21-三卷成片/第十四章_灯油壶.mp4',
  '第十五章': ROOT + '/21-三卷成片/第十五章_整条街.mp4',
  '第十六章': ROOT + '/21-三卷成片/第十六章_柜子最上面.mp4',
  '第十七章': ROOT + '/21-三卷成片/第十七章_问天宗的年轻人.mp4',
  '第十八章': ROOT + '/21-三卷成片/第十八章_灯还亮着.mp4',
  '尾声':   ROOT + '/21-三卷成片/尾声_他们都活着.mp4',
};

console.log('═══ 逐章重拼（含旁白）═══');
const chap = [];
for (const u of UNIT_ORDER) {
  const g = (groups[u] || []).slice().sort((a, b) => a.shot.localeCompare(b.shot) || a.seq - b.seq);
  if (!g.length) { console.log(`  ⚠️ ${u} 没有镜头`); continue; }
  const norms = [];
  for (let i = 0; i < g.length; i++) { const n = `${STAGE}/n_${String(i).padStart(4,'0')}.mp4`; norm(g[i].file, n); norms.push(n); }
  const vid = `${STAGE}/v_${u}.mp4`;
  concat(norms, vid);
  const out = `${STAGE}/${u}.mp4`;
  const had = muxNarration(vid, OLD[u], out);
  const srcTag = g.map(x => x.from === 'canvas' ? '' : (x.shot + (x.from === 'local★' ? '★' : ''))).filter(Boolean).join(',');
  chap.push({ unit: u, file: out, d: dur(out), shots: g.length, localExtra: srcTag });
  console.log(`  ${u.padEnd(6)} ${String(g.length).padStart(2)} 镜  ${dur(out).toFixed(2)}s  旁白:${had ? '✓' : '✗'}  ${srcTag ? '本地补充:' + srcTag : ''}`);
}

console.log('\n═══ 三卷 + 全片 ═══');
const v1 = chap.filter(c => UNIT_ORDER.indexOf(c.unit) <= 5).map(c => c.file);
const v2 = chap.filter(c => UNIT_ORDER.indexOf(c.unit) >= 6 && UNIT_ORDER.indexOf(c.unit) <= 13).map(c => c.file);
const v3 = chap.filter(c => UNIT_ORDER.indexOf(c.unit) >= 14).map(c => c.file);
const vols = [['第一卷', v1], ['第二卷', v2], ['第三卷', v3]];
for (const [n, l] of vols) { concat(l, `${STAGE}/${n}.mp4`); console.log(`  ${n}  ${dur(`${STAGE}/${n}.mp4`).toFixed(2)}s`); }
concat(vols.map(v => `${STAGE}/${v[0]}.mp4`), `${STAGE}/全片.mp4`);
console.log(`  全片  ${dur(`${STAGE}/全片.mp4`).toFixed(2)}s`);
fs.writeFileSync(STAGE + '/chapters.json', JSON.stringify(chap, null, 1), 'utf8');
console.log('\n完成，输出在 ' + STAGE);
