import assert from 'node:assert/strict';
import { generateChart } from '../../lib/ziwei/algorithm';
import type { BirthInfo } from '../../lib/ziwei/types';

const base: BirthInfo = { year: 1925, month: 3, day: 1, hour: 6, gender: 'male' };

// 不存在的公历日期要在排盘前拒绝，不能被顺延成下个月的盘
for (const [year, month, day] of [
  [1925, 2, 29], // 非闰年
  [1925, 2, 30],
  [1980, 2, 30], // 闰年也没有 2 月 30 日
  [1925, 4, 31],
  [1925, 13, 1],
  [1925, 0, 10],
  [1925, 6, 0],
]) {
  assert.throws(
    () => generateChart({ ...base, year, month, day }),
    RangeError,
    `${year}-${month}-${day} should be rejected`,
  );
}

// 真实存在的边界日期照常排盘
for (const [year, month, day] of [
  [1924, 2, 29], // 闰年
  [1980, 2, 29],
  [1925, 2, 28],
  [1925, 1, 31],
  [1925, 12, 31],
]) {
  const chart = generateChart({ ...base, year, month, day });
  assert.equal(chart.birthInfo.day, day, `${year}-${month}-${day} should be accepted`);
}

console.log('solar date existence regression passed');
