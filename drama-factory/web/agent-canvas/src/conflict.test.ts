import { parseConflictBody, conflictMessage, THEME_WHITELIST } from './conflict.js';

// readThemeWhitelist 依赖 getComputedStyle/DOM，不在 node 里测；
// 白名单读取时机（仅 connectedCallback 调用）由浏览器 harness 截图验证。

function eq(a: unknown, b: unknown, name: string): void {
  const x = JSON.stringify(a);
  const y = JSON.stringify(b);
  if (x !== y) {
    throw new Error(`FAIL ${name}: ${x} !== ${y}`);
  }
}

eq(
  parseConflictBody({ current_version: 3, updated_by: 'agent', status: 409 }),
  { currentVersion: 3, updatedBy: 'agent' },
  'parse ok',
);
eq(parseConflictBody({}), null, 'parse empty');
eq(parseConflictBody(null), null, 'parse null');
eq(parseConflictBody({ current_version: '3', updated_by: 'agent' }), null, 'parse wrong type');
eq(
  conflictMessage({ currentVersion: 3, updatedBy: 'agent' }),
  '内容已被 agent 修改，是否刷新？',
  'msg agent',
);
eq(
  conflictMessage({ currentVersion: 3, updatedBy: 'editor' }),
  '内容已被其他编辑者修改，是否刷新？',
  'msg editor',
);
eq(
  THEME_WHITELIST.every((v) => v.startsWith('--ph-')),
  true,
  'whitelist prefix',
);
eq(THEME_WHITELIST.length, 5, 'whitelist size');

console.log('conflict logic: 8 checks passed');
