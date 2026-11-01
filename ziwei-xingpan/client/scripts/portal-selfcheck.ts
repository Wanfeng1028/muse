// Portal round self-checks (run: npx tsx scripts/portal-selfcheck.ts).
// No test framework: plain asserts, non-zero exit on any failure.
import { HEXAGRAMS } from '../src/lib/tools-data';
import { MBTI_QUESTIONS, mbtiType } from '../src/lib/tools-data';
import { generateChart } from '../src/engine/algorithm';
import { fortuneToday, calendarMonth, dayInfo } from '../src/lib/fortune';

let failures = 0;
const check = (cond: boolean, msg: string) => {
  if (!cond) { console.error('  FAIL', msg); failures++; }
  else console.log('  ok', msg);
};

// 1. 六爻 64 卦：数量 + (上卦, 下卦) 组合唯一 + 八纯卦对角。
check(HEXAGRAMS.length === 64, 'hexagrams count = 64');
const pairs = new Set(HEXAGRAMS.map((h) => h.upper + '/' + h.lower));
check(pairs.size === 64, 'hexagram (upper, lower) pairs unique');
for (const t of ['乾', '坤', '震', '巽', '坎', '离', '艮', '兑']) {
  check(HEXAGRAMS.some((h) => h.name === t && h.upper === t && h.lower === t), `pure trigram ${t}`);
}

// 2. MBTI：全 A -> ESTJ，全 B -> INFP，混合 -> ENTP。
check(MBTI_QUESTIONS.length === 16, 'mbti questions = 16');
check(mbtiType(Array(16).fill(0)) === 'ESTJ', 'mbti all-A = ESTJ');
check(mbtiType(Array(16).fill(1)) === 'INFP', 'mbti all-B = INFP');
check(mbtiType([0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1]) === 'ENTP', 'mbti mixed = ENTP');

// 3. 运势：样本盘四维与综合均在 [35, 95] 内。
const chart = generateChart({ year: 1995, month: 6, day: 15, hour: 6, gender: 'male' });
const f = fortuneToday(chart, new Date(2026, 10, 1));
for (const [k, v] of [['love', f.love], ['wealth', f.wealth], ['career', f.career], ['study', f.study], ['total', f.total]] as const) {
  check(v >= 35 && v <= 95, `fortune ${k} = ${v} in [35, 95]`);
}
check(f.lunarLabel === '农历九月廿三', `fortune lunar label = ${f.lunarLabel}`);
check(f.dayBranch === 3, `fortune day branch 2026-11-01 = ${f.dayBranch} (卯)`);

// 4. 万年历：2026 年 11 月格子全覆盖，立冬标在 7 日，11 月 1 日值日宿为昴。
const weeks = calendarMonth(2026, 11, new Date(2026, 10, 1));
const nov7 = weeks.flat().find((c) => c.inMonth && c.d === 7);
check(nov7?.jieqi === '立冬', `2026-11-07 jieqi = ${nov7?.jieqi}`);
const nov1 = dayInfo(2026, 11, 1);
check(nov1.xiu === '昴', `2026-11-01 xiu = ${nov1.xiu}`);
check(nov1.yi.includes('祈福'), '2026-11-01 yi includes 祈福');

if (failures > 0) { console.error(`portal-selfcheck: ${failures} FAILURES`); process.exit(1); }
console.log('portal-selfcheck: all green');
