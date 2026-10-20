import { PROJ, PW, CHROME, PROFILE, FFMPEG, TOOLS, WORKDIR, PROJDIR, PROBEDIR, SHOTDIR, LIB, HOMEDIR, PYTHON, DIR, SECRETS, launch, dismissModals, injectEngine, cookieHeader, sleep, CANVAS_URL, API, TASKS, PROJECT_ID } from './_config.mjs';
/**
 * 给重建的旧版成片补旁白（用 03-音频 里提取好的）
 * 用法: node mux-oldnarr.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const FF = FFMPEG;
const D = ROOT + '/★剪辑工作台/02-旧视频/旧版成片（重建）';
const N = ROOT + '/★剪辑工作台/03-音频/旁白-按章';

function dur(f) {
  try { execFileSync(FF, ['-hide_banner','-i',f], { encoding:'utf8', stdio:['ignore','pipe','pipe'] }); }
  catch (e) { const m = String(e.stderr||'').match(/Duration: (\d+):(\d+):([\d.]+)/); return m ? +m[1]*3600 + +m[2]*60 + +m[3] : 0; }
  return 0;
}
const chap = fs.readdirSync(D).filter(f => /^\d\d_/.test(f) && f.endsWith('.mp4')).sort();
console.log('待补旁白的章节:', chap.length);
let ok = 0, no = 0;
for (const f of chap) {
  const v = path.join(D, f);
  const narr = path.join(N, f.replace(/\.mp4$/, '') + '_旁白.wav');
  if (!fs.existsSync(narr)) { console.log(`   ⚠️ ${f} 没有对应旁白`); no++; continue; }
  // 先看现有音轨是不是已经混过旧旁白（旧版7章）
  const hasOld = ['00_楔子','01_第一章_天宝街未醒','02_第二章_小伙计送汤','03_第三章_邮差的死信','05_第五章_陈阿婆','06_第六章_宋铁生','07_第七章_两次真话'].includes(f.replace(/\.mp4$/,''));
  if (hasOld) { console.log(`   ✓ ${f} 已含旧旁白`); ok++; continue; }
  const vd = dur(v);
  const tmp = v.replace(/\.mp4$/, '_n.mp4');
  try {
    execFileSync(FF, ['-hide_banner','-loglevel','error','-y','-i',v,'-i',narr,
      '-filter_complex', `[1:a]apad=whole_dur=${vd}[a]`, '-map','0:v','-map','[a]',
      '-c:v','copy','-c:a','aac','-ar','32000','-ac','2','-shortest', tmp]);
    fs.renameSync(tmp, v);
    console.log(`   ✅ ${f}  ${vd.toFixed(2)}s  补上旁白`);
    ok++;
  } catch (e) { console.log(`   ❌ ${f}  ${String(e).slice(0, 60)}`); }
}
console.log(`\n补旁白: ${ok} 章成功, ${no} 章缺素材`);

// 重拼三卷 + 全片
console.log('\n═══ 重拼三卷 + 全片 ═══');
const VOLS = {
  '卷1': ['00_楔子','01_第一章_天宝街未醒','02_第二章_小伙计送汤','03_第三章_邮差的死信','04_第四章_苏娘','05_第五章_陈阿婆'],
  '卷2': ['06_第六章_宋铁生','07_第七章_两次真话','08_第八章_北原的灯','09_第九章_长命锁','10_第十章_老仵作','11_第十一章_小马','12_第十二章_北原来的女人','13_第十三章_地址有了'],
  '卷3': ['14_第十四章_灯油壶','15_第十五章_整条街','16_第十六章_柜子最上面','17_第十七章_问天宗的年轻人','18_第十八章_灯还亮着','19_尾声_他们都活着'],
};
function concat(list, out) {
  const t = D + '/_l.txt';
  fs.writeFileSync(t, list.map(f => `file '${f.replace(/\\/g,'/')}'`).join('\n'), 'utf8');
  execFileSync(FF, ['-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',t,'-c','copy',out]);
}
const vf = [];
for (const [vn, cs] of Object.entries(VOLS)) {
  const l = cs.map(c => path.join(D, c + '.mp4')).filter(fs.existsSync);
  concat(l, path.join(D, vn + '.mp4'));
  console.log(`   ${vn}  ${dur(path.join(D, vn + '.mp4')).toFixed(2)}s`);
  vf.push(path.join(D, vn + '.mp4'));
}
concat(vf, path.join(D, '全片-旧版.mp4'));
const tot = dur(path.join(D, '全片-旧版.mp4'));
console.log(`\n★ 全片（旧版·带旁白）  ${tot.toFixed(2)}s = ${Math.floor(tot/60)}分${Math.round(tot%60)}秒`);
console.log(`  原始交付版 1458.36s = 24分18秒`);
console.log(`\n文件:`);
for (const f of fs.readdirSync(D).filter(f => f.endsWith('.mp4')).sort()) {
  console.log(`   ${f.padEnd(28)} ${(fs.statSync(path.join(D,f)).size/1048576).toFixed(1)} MB`);
}
