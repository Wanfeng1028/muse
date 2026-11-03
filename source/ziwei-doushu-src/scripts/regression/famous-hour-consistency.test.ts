/**
 * 样本时辰一致性回归（对应 issue #26）
 *
 * FAMOUS_PERSONS 里的 `hour` 是**时辰地支索引 0–11**（0=子 … 11=亥），
 * 不是 0–23 的小时数。历史上注释与索引曾经对不上（11 条里错 7 条：
 * hour 5 写成「午时」实为巳时、3 写成「寅时」实为卯时、4 写成「卯时」实为辰时）。
 *
 * 这条回归钉住两件事：
 *   1. 每条样本的 hour 必须落在 0–11；
 *   2. 带「X时」注释的样本，注释必须与索引对应的地支一致。
 *
 * 走源码解析而非运行时 import —— famous.ts 带 `server-only`，
 * 直接跑需要额外的 node 条件参数，解析源码更省事也更跨平台。
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const BRANCH_NAMES = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥'];
const src = readFileSync(new URL('../../lib/ziwei/famous.ts', import.meta.url), 'utf8');

const rows = [...src.matchAll(/hour:\s*(\d+),?[ \t]*(?:\/\/[ \t]*(.*))?/g)];
assert.ok(rows.length > 0, 'famous.ts 里没解析到任何 hour 字段，正则或文件结构变了');

let annotated = 0;
for (const [, raw, comment] of rows) {
  const hour = Number(raw);
  assert.ok(
    Number.isInteger(hour) && hour >= 0 && hour <= 11,
    `hour 必须是 0–11 的时辰地支索引，实际 ${raw}`,
  );
  if (!comment) continue;
  const named = BRANCH_NAMES.find((b) => comment.includes(`${b}时`));
  if (!named) continue;
  annotated++;
  assert.equal(
    named,
    BRANCH_NAMES[hour],
    `hour: ${hour} 的注释写着「${named}时」，但索引 ${hour} 实际是「${BRANCH_NAMES[hour]}时」`,
  );
}

console.log(`✅ 样本时辰一致性：${rows.length} 条样本 hour 均在 0–11，其中 ${annotated} 条带时辰注释且与索引一致`);
