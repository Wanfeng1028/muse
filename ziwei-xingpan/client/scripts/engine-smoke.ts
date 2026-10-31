import { generateChart } from '../src/engine/algorithm';
import type { BirthInfo } from '../src/engine/types';

const PALACE_12 = ['命宫', '兄弟', '夫妻', '子女', '财帛', '疾厄', '迁移', '仆役', '官禄', '田宅', '福德', '父母'];
const BR = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥'];
let failures = 0;
const fail = (m: string) => { console.error('  FAIL', m); failures++; };

const samples: BirthInfo[] = [];
for (let y = 1960; y <= 2010; y += 7)
  for (let m = 1; m <= 12; m += 3)
    for (let d = 5; d <= 26; d += 10)
      for (let h = 0; h < 12; h += 3)
        for (const g of ['male', 'female'] as const)
          samples.push({ year: y, month: m, day: d, hour: h, gender: g });

for (const bi of samples) {
  let chart;
  try { chart = generateChart(bi); } catch (e) { fail(`throw @ ${JSON.stringify(bi)}: ${(e as Error).message}`); continue; }
  if (chart.palaces.length !== 12) { fail(`palace count @ ${JSON.stringify(bi)}`); continue; }
  if (JSON.stringify(chart.palaces.map((p) => p.name).sort()) !== JSON.stringify([...PALACE_12].sort())) { fail(`palace names @ ${JSON.stringify(bi)}`); continue; }
  if (JSON.stringify(chart.palaces.map((p) => p.branch).sort((a, b) => a - b)) !== JSON.stringify([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])) { fail(`branches @ ${JSON.stringify(bi)}`); continue; }
  const ming = chart.palaces.find((p) => p.name === '命宫')!;
  for (let k = 0; k < 12; k++) {
    const expectBranch = ((ming.branch - k) % 12 + 12) % 12;
    const p = chart.palaces.find((x) => x.name === PALACE_12[k])!;
    if (p.branch !== expectBranch) { fail(`layout ${PALACE_12[k]} @ ${JSON.stringify(bi)}`); break; }
  }
  let zi = -1; let fu = -1;
  for (const p of chart.palaces) for (const s of p.stars) {
    if (s.name === '紫微') zi = p.branch;
    if (s.name === '天府') fu = p.branch;
  }
  if (zi >= 0 && fu >= 0 && (zi + fu) % 12 !== 4) fail(`zi-fu symmetry @ ${JSON.stringify(bi)}`);
  const sihuaStars = chart.palaces.flatMap((p) => p.stars.filter((s) => s.siHua).map((s) => s.name));
  if (new Set(sihuaStars).size < 4) fail(`natal sihua <4 distinct @ ${JSON.stringify(bi)}: ${sihuaStars.join(',')}`);
}

const known = generateChart({ year: 1995, month: 6, day: 15, hour: 6, gender: 'male', name: '示例', province: '北京市', city: '北京', longitude: 116.4 });
console.log('\nKnown case 1995-06-15 午时 男 北京:');
console.log(`  lunar ${known.lunarInfo.lunarYear}-${known.lunarInfo.lunarMonth}-${known.lunarInfo.lunarDay} ${known.wuxingJuName} 命宫${BR[known.mingGongBranch]} 身宫${BR[known.shenGongBranch]} 命主${known.mingZhu} 身主${known.shenZhu}`);
for (const p of [...known.palaces].sort((a, b) => a.branch - b.branch)) {
  const majors = p.stars.filter((s) => s.type === 'major').map((s) => `${s.name}${s.brightnessRaw ?? ''}${s.siHua ? '化' + s.siHua : ''}`).join(' ');
  console.log(`  ${BR[p.branch]} ${p.name}: ${majors || '(空宫)'}`);
}
console.log(`\nSamples: ${samples.length} charts, failures: ${failures}`);
if (failures) process.exit(1);
console.log('ENGINE SMOKE OK');
