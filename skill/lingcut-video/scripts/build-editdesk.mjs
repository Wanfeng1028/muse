import { PROJ, PW, CHROME, PROFILE, FFMPEG, TOOLS, WORKDIR, PROJDIR, PROBEDIR, SHOTDIR, LIB, HOMEDIR, PYTHON, DIR, SECRETS, launch, dismissModals, injectEngine, cookieHeader, sleep, CANVAS_URL, API, TASKS, PROJECT_ID } from './_config.mjs';
/**
 * 建剪辑工作台：新旧视频分开 + 音频 + 成片参考 + 素材
 * 用法: node build-editdesk.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const FF = FFMPEG;
const DESK = ROOT + '/★剪辑工作台';

const UNIT_VOL = {
  '楔子': 1, '第一章': 1, '第二章': 1, '第三章': 1, '第四章': 1, '第五章': 1,
  '第六章': 2, '第七章': 2, '第八章': 2, '第九章': 2, '第十章': 2,
  '第十一章': 2, '第十二章': 2, '第十三章': 2,
  '第十四章': 3, '第十五章': 3, '第十六章': 3, '第十七章': 3, '第十八章': 3, '尾声': 3,
};
const UNIT_ORDER = Object.keys(UNIT_VOL);
const UNIT_TITLE = {
  '楔子': '00_楔子', '第一章': '01_第一章_天宝街未醒', '第二章': '02_第二章_小伙计送汤',
  '第三章': '03_第三章_邮差的死信', '第四章': '04_第四章_苏娘', '第五章': '05_第五章_陈阿婆',
  '第六章': '06_第六章_宋铁生', '第七章': '07_第七章_两次真话', '第八章': '08_第八章_北原的灯',
  '第九章': '09_第九章_长命锁', '第十章': '10_第十章_老仵作', '第十一章': '11_第十一章_小马',
  '第十二章': '12_第十二章_北原来的女人', '第十三章': '13_第十三章_地址有了',
  '第十四章': '14_第十四章_灯油壶', '第十五章': '15_第十五章_整条街',
  '第十六章': '16_第十六章_柜子最上面', '第十七章': '17_第十七章_问天宗的年轻人',
  '第十八章': '18_第十八章_灯还亮着', '尾声': '19_尾声_他们都活着',
};
// 本地补充（画布上没有的）
const SUPP = [
  { unit: '楔子', shot: 'A10', name: 'A10_写过两次（17秒·尾帧接续）', file: ROOT + '/_tmp/A10-17s.mp4' },
  { unit: '楔子', shot: 'A11', name: 'A11_片名字卡', file: ROOT + '/06-楔子视频-v2/A11-片名字卡.mp4' },
  { unit: '尾声', shot: 'T09', name: 'T09_片名字卡', file: ROOT + '/20-三卷视频/T09-片名字卡.mp4' },
];

fs.rmSync(DESK, { recursive: true, force: true });
for (const d of ['01-新视频', '02-旧视频/旧成片（修复前）', '02-旧视频/v1素材', '03-音频/旁白-按章', '03-音频/LibTV旁白源文件', '04-成片参考', '05-素材图']) {
  fs.mkdirSync(path.join(DESK, d), { recursive: true });
}
function cp(src, dst) { if (fs.existsSync(src)) { fs.copyFileSync(src, dst); return true; } return false; }

// ── ① 新视频（按卷/章分文件夹）──────────────────
console.log('═══ ① 新视频 ═══');
const SRC = ROOT + '/★网站最新/视频';
const groups = {};
for (const f of fs.readdirSync(SRC)) {
  if (!f.endsWith('.mp4')) continue;
  const m = f.match(/^\d+_(.+?) ([A-Z]\d\d)(?:_(.*?))?\.mp4$/);
  if (!m) continue;
  const [, unit, shot, title] = m;
  if (!UNIT_ORDER.includes(unit)) continue;
  (groups[unit] = groups[unit] || []).push({ shot, title: title || '', file: path.join(SRC, f) });
}
for (const s of SUPP) { if (fs.existsSync(s.file)) (groups[s.unit] = groups[s.unit] || []).push({ shot: s.shot, title: s.name, file: s.file, supp: true }); }
let newCnt = 0;
for (const u of UNIT_ORDER) {
  const g = (groups[u] || []).slice().sort((a, b) => a.shot.localeCompare(b.shot));
  if (!g.length) continue;
  const dir = path.join(DESK, '01-新视频', `卷${UNIT_VOL[u]}`, UNIT_TITLE[u]);
  fs.mkdirSync(dir, { recursive: true });
  for (const x of g) {
    const t = x.title ? x.title.replace(/[\\/:*?"<>|]/g, '_') : '';
    const nm = `${x.shot}${t ? '_' + t : ''}.mp4`;
    if (cp(x.file, path.join(dir, nm))) newCnt++;
  }
  console.log(`   ${UNIT_TITLE[u].padEnd(22)} ${String(g.length).padStart(2)} 个`);
}
console.log(`   新视频合计 ${newCnt} 个`);

// ── ② 旧视频 ──────────────────────────────────
console.log('\n═══ ② 旧视频 ═══');
let oldCnt = 0;
const BK = ROOT + '/_旧版备份-2026-10-02';
if (fs.existsSync(BK)) for (const f of fs.readdirSync(BK)) {
  if (f.endsWith('.mp4') && cp(path.join(BK, f), path.join(DESK, '02-旧视频/旧成片（修复前）', f))) oldCnt++;
}
for (const [src, label] of [['06-楔子视频', '楔子v1'], ['08-一章视频', '第一章v1'], ['10-二章视频', '第二章v1']]) {
  const d = ROOT + '/' + src;
  if (!fs.existsSync(d)) continue;
  const out = path.join(DESK, '02-旧视频/v1素材', label);
  fs.mkdirSync(out, { recursive: true });
  for (const f of fs.readdirSync(d)) if (f.endsWith('.mp4') && !f.startsWith('_')) { if (cp(path.join(d, f), path.join(out, f))) oldCnt++; }
}
console.log(`   旧视频合计 ${oldCnt} 个`);

// ── ③ 音频 ────────────────────────────────────
console.log('\n═══ ③ 音频 ═══');
// 每章旁白（从成片提取纯音频）
const OLD_CH = {
  '楔子': ROOT + '/13-第一卷成片/楔子_带旁白_v3.mp4',
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
  '第十八章': ROOT + '/18-二卷成片/第十八章_灯还亮着.mp4',
  '尾声': ROOT + '/21-三卷成片/尾声_他们都活着.mp4',
};
let auCnt = 0;
for (const u of UNIT_ORDER) {
  const src = OLD_CH[u];
  const dst = path.join(DESK, '03-音频/旁白-按章', `${UNIT_TITLE[u]}_旁白.wav`);
  if (src && fs.existsSync(src)) {
    try {
      execFileSync(FF, ['-hide_banner','-loglevel','error','-y','-i',src,'-vn','-c:a','pcm_s16le','-ar','48000','-ac','2',dst], { stdio: 'inherit' });
      auCnt++;
    } catch (e) { console.log(`   ⚠️ ${u} 提取失败`); }
  }
}
console.log(`   按章旁白 ${auCnt} 个`);
// LibTV 源文件
let libCnt = 0;
for (const sub of ['narration-full/lines', 'narration-vol23/lines', 'vol3miss/lines', 'narration-unified']) {
  const d = LIB + '/' + sub;
  if (!fs.existsSync(d)) continue;
  const out = path.join(DESK, '03-音频/LibTV旁白源文件', sub.replace('/', '_'));
  fs.mkdirSync(out, { recursive: true });
  for (const f of fs.readdirSync(d)) if (/\.(mp3|wav)$/i.test(f)) { if (cp(path.join(d, f), path.join(out, f))) libCnt++; }
}
for (const f of ['narration-full/旁白-全片完整版.mp3', 'narration-vol23/旁白-第二三卷-统一.mp3']) {
  const p = LIB + '/' + f;
  if (fs.existsSync(p) && cp(p, path.join(DESK, '03-音频/LibTV旁白源文件', path.basename(f)))) libCnt++;
}
console.log(`   LibTV 源文件 ${libCnt} 个`);

// ── ④ 成片参考 ────────────────────────────────
console.log('\n═══ ④ 成片参考 ═══');
let refCnt = 0;
const REFS = [
  ['00_全片_25分10秒.mp4', ROOT + '/22-全片/问道长生-代笔_全片.mp4'],
  ['卷一_天宝街_7分17秒.mp4', ROOT + '/13-第一卷成片/第一卷_天宝街_完整版_v3.mp4'],
  ['卷二_信_10分08秒.mp4', ROOT + '/18-二卷成片/第二卷_信_完整版.mp4'],
  ['卷三_灯_7分45秒.mp4', ROOT + '/21-三卷成片/第三卷_灯_完整版.mp4'],
];
for (const [n, p] of REFS) { if (cp(p, path.join(DESK, '04-成片参考', n))) { refCnt++; console.log(`   ✅ ${n}`); } }
// 分章
const chapDir = path.join(DESK, '04-成片参考', '分章（20个）');
fs.mkdirSync(chapDir, { recursive: true });
for (const [n, p] of Object.entries(OLD_CH)) { if (cp(p, path.join(chapDir, `${UNIT_TITLE[n]}.mp4`))) refCnt++; }
console.log(`   成片参考合计 ${refCnt} 个`);

// ── ⑤ 素材图 ──────────────────────────────────
console.log('\n═══ ⑤ 素材图 ═══');
let imgCnt = 0;
const IMG = ROOT + '/★网站最新/图片';
if (fs.existsSync(IMG)) for (const f of fs.readdirSync(IMG)) {
  if (/\.(png|jpg|jpeg|webp)$/i.test(f) && cp(path.join(IMG, f), path.join(DESK, '05-素材图', f))) imgCnt++;
}
console.log(`   素材图 ${imgCnt} 张`);

console.log('\n═══ 完成 ═══');
let tot = 0;
for (const d of fs.readdirSync(DESK)) {
  const p = path.join(DESK, d);
  if (!fs.statSync(p).isDirectory()) continue;
  const s = (function walk(x) { let n = 0; for (const f of fs.readdirSync(x)) { const q = path.join(x, f); const st = fs.statSync(q); n += st.isDirectory() ? walk(q) : st.size; } return n; })(p);
  tot += s;
  console.log(`   ${d.padEnd(20)} ${(s / 1048576).toFixed(0).padStart(5)} MB`);
}
console.log(`   合计 ${(tot / 1048576).toFixed(0)} MB`);
