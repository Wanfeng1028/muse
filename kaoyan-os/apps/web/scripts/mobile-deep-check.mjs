// apps/web/scripts/mobile-deep-check.mjs
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const APP_PATH = resolve(__dirname, '../src/App.tsx');
const CSS_PATH = resolve(__dirname, '../src/index.css');

let appSrc = '';
let cssSrc = '';
try {
  appSrc = readFileSync(APP_PATH, 'utf8');
} catch (e) {
  console.error(`[FAIL] 无法读取 App.tsx: ${APP_PATH} - ${e.message}`);
  process.exit(1);
}
try {
  cssSrc = readFileSync(CSS_PATH, 'utf8');
} catch (e) {
  console.error(`[FAIL] 无法读取 index.css: ${CSS_PATH} - ${e.message}`);
  process.exit(1);
}

const results = [];
function record(name, ok, reason) {
  results.push({ name, ok, reason });
  if (ok) {
    console.log(`[PASS] ${name}`);
  } else {
    console.log(`[FAIL] ${name} 原因: ${reason}`);
  }
}

// ---------- helpers ----------

function extractArrayLiteral(src, constName) {
  const re = new RegExp(`const\\s+${constName}\\s*(?::[^=]+)?=\\s*\\[`);
  const m = re.exec(src);
  if (!m) return null;
  let i = m.index + m[0].length - 1; // at '['
  let depth = 0;
  let inStr = null;
  let start = i;
  for (; i < src.length; i++) {
    const ch = src[i];
    if (inStr) {
      if (ch === '\\') { i++; continue; }
      if (ch === inStr) inStr = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') { inStr = ch; continue; }
    if (ch === '[') depth++;
    else if (ch === ']') {
      depth--;
      if (depth === 0) {
        return src.slice(start, i + 1);
      }
    }
  }
  return null;
}

function parseObjectEntries(arrayLiteral) {
  // arrayLiteral starts with [ ends with ]
  const inner = arrayLiteral.slice(1, -1);
  const items = [];
  let depth = 0;
  let inStr = null;
  let cur = '';
  for (let i = 0; i < inner.length; i++) {
    const ch = inner[i];
    if (inStr) {
      cur += ch;
      if (ch === '\\') { cur += inner[i + 1] ?? ''; i++; continue; }
      if (ch === inStr) inStr = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') { inStr = ch; cur += ch; continue; }
    if (ch === '{' || ch === '[' || ch === '(') { depth++; cur += ch; continue; }
    if (ch === '}' || ch === ']' || ch === ')') { depth--; cur += ch; continue; }
    if (ch === ',' && depth === 0) {
      if (cur.trim()) items.push(cur.trim());
      cur = '';
      continue;
    }
    cur += ch;
  }
  if (cur.trim()) items.push(cur.trim());

  return items.map((raw) => {
    // strip surrounding braces
    const body = raw.replace(/^\{/, '').replace(/\}$/, '');
    const fields = {};
    // split top-level commas within body
    const parts = [];
    let d = 0;
    let s = null;
    let c = '';
    for (let i = 0; i < body.length; i++) {
      const ch = body[i];
      if (s) {
        c += ch;
        if (ch === '\\') { c += body[i + 1] ?? ''; i++; continue; }
        if (ch === s) s = null;
        continue;
      }
      if (ch === '"' || ch === "'" || ch === '`') { s = ch; c += ch; continue; }
      if (ch === '{' || ch === '[' || ch === '(') { d++; c += ch; continue; }
      if (ch === '}' || ch === ']' || ch === ')') { d--; c += ch; continue; }
      if (ch === ',' && d === 0) { if (c.trim()) parts.push(c.trim()); c = ''; continue; }
      c += ch;
    }
    if (c.trim()) parts.push(c.trim());

    for (const p of parts) {
      const eq = p.indexOf(':');
      if (eq < 0) continue;
      const k = p.slice(0, eq).trim();
      const v = p.slice(eq + 1).trim();
      fields[k] = v;
    }
    return { raw, fields };
  });
}

function parseStringLiteral(v) {
  if (!v) return null;
  const m = /^(['"`])([\s\S]*)\1$/.exec(v.trim());
  if (!m) return null;
  return m[2];
}

function parseBoolLiteral(v) {
  if (v === 'true') return true;
  if (v === 'false') return false;
  return null;
}

function extractRoutesPaths(src) {
  const paths = [];
  const re = /<Route\s+path\s*=\s*"([^"]+)"/g;
  let m;
  while ((m = re.exec(src))) paths.push(m[1]);
  return paths;
}

// Extract all @media (max-width: 768px) blocks (brace matched)
function extractMobileMediaBlocks(css) {
  const blocks = [];
  const re = /@media\s*\(\s*max-width\s*:\s*768px\s*\)/g;
  let m;
  while ((m = re.exec(css))) {
    let i = m.index + m[0].length;
    // skip whitespace
    while (i < css.length && /\s/.test(css[i])) i++;
    if (css[i] !== '{') continue;
    let depth = 0;
    const start = i;
    let inStr = null;
    let inComment = false;
    for (; i < css.length; i++) {
      const ch = css[i];
      if (inComment) {
        if (ch === '*' && css[i + 1] === '/') { inComment = false; i++; }
        continue;
      }
      if (inStr) {
        if (ch === '\\') { i++; continue; }
        if (ch === inStr) inStr = null;
        continue;
      }
      if (ch === '/' && css[i + 1] === '*') { inComment = true; i++; continue; }
      if (ch === '"' || ch === "'") { inStr = ch; continue; }
      if (ch === '{') depth++;
      else if (ch === '}') {
        depth--;
        if (depth === 0) {
          blocks.push(css.slice(start + 1, i));
          break;
        }
      }
    }
  }
  return blocks;
}

// Extract text outside any @media (max-width: 768px) block
function extractDesktopCss(css) {
  const ranges = [];
  const re = /@media\s*\(\s*max-width\s*:\s*768px\s*\)/g;
  let m;
  while ((m = re.exec(css))) {
    let i = m.index + m[0].length;
    while (i < css.length && /\s/.test(css[i])) i++;
    if (css[i] !== '{') continue;
    let depth = 0;
    const start = i;
    let inStr = null;
    let inComment = false;
    let end = -1;
    for (; i < css.length; i++) {
      const ch = css[i];
      if (inComment) {
        if (ch === '*' && css[i + 1] === '/') { inComment = false; i++; }
        continue;
      }
      if (inStr) {
        if (ch === '\\') { i++; continue; }
        if (ch === inStr) inStr = null;
        continue;
      }
      if (ch === '/' && css[i + 1] === '*') { inComment = true; i++; continue; }
      if (ch === '"' || ch === "'") { inStr = ch; continue; }
      if (ch === '{') depth++;
      else if (ch === '}') {
        depth--;
        if (depth === 0) { end = i; break; }
      }
    }
    if (end >= 0) ranges.push([m.index, end + 1]);
  }
  if (ranges.length === 0) return css;
  let out = '';
  let cursor = 0;
  for (const [s, e] of ranges) {
    if (s > cursor) out += css.slice(cursor, s);
    cursor = e;
  }
  if (cursor < css.length) out += css.slice(cursor);
  return out;
}

// Find a rule body for a given selector inside a css text (single rule, no nested)
function findRuleBody(css, selector) {
  // match "selector {" preceded by start, }, {, or ; to avoid matching prefix
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp(`(^|[}\\);\\s,])${escaped}\\s*\\{`, 'g');
  let m;
  while ((m = re.exec(css))) {
    let i = m.index + m[0].length;
    let depth = 1;
    let inStr = null;
    let inComment = false;
    const start = i;
    for (; i < css.length; i++) {
      const ch = css[i];
      if (inComment) {
        if (ch === '*' && css[i + 1] === '/') { inComment = false; i++; }
        continue;
      }
      if (inStr) {
        if (ch === '\\') { i++; continue; }
        if (ch === inStr) inStr = null;
        continue;
      }
      if (ch === '/' && css[i + 1] === '*') { inComment = true; i++; continue; }
      if (ch === '"' || ch === "'") { inStr = ch; continue; }
      if (ch === '{') depth++;
      else if (ch === '}') {
        depth--;
        if (depth === 0) return css.slice(start, i);
      }
    }
  }
  return null;
}

function declValue(body, prop) {
  if (!body) return null;
  const re = new RegExp(`(?:^|[;{\\s])${prop}\\s*:\\s*([^;]+);`, 'g');
  const m = re.exec(body);
  return m ? m[1].trim() : null;
}

function firstPxNumber(value) {
  if (!value) return null;
  const m = /(-?\d+(?:\.\d+)?)px/.exec(value);
  return m ? parseFloat(m[1]) : null;
}

function firstNumericValue(value) {
  if (!value) return null;
  const m = /(-?\d+(?:\.\d+)?)/.exec(value);
  return m ? parseFloat(m[1]) : null;
}

// ---------- Check 1 ----------
(function check1() {
  const name = '1. 底部 Tab 数量与路由映射';
  try {
    const arr = extractArrayLiteral(appSrc, 'MOBILE_TABS');
    if (!arr) return record(name, false, '未找到 MOBILE_TABS 数组字面量');
    const items = parseObjectEntries(arr);
    if (items.length !== 5) return record(name, false, `MOBILE_TABS 项数应为 5，实际 ${items.length}`);

    const expected = [
      { to: '/', label: '仪表盘', end: true },
      { to: '/plans', label: '复习计划', end: false },
      { to: '/mistakes', label: '错题本', end: false },
      { to: '/words', label: '单词', end: false },
      { to: '/exams', label: '真题', end: false },
    ];

    const navArr = extractArrayLiteral(appSrc, 'NAV_ITEMS');
    if (!navArr) return record(name, false, '未找到 NAV_ITEMS 数组字面量');
    const navItems = parseObjectEntries(navArr);
    const navToSet = new Set();
    for (const it of navItems) {
      const t = parseStringLiteral(it.fields.to);
      if (t) navToSet.add(t);
    }

    const routesPaths = new Set(extractRoutesPaths(appSrc));

    for (let i = 0; i < expected.length; i++) {
      const got = items[i];
      const gotTo = parseStringLiteral(got.fields.to);
      const gotLabel = parseStringLiteral(got.fields.label);
      const gotEnd = parseBoolLiteral(got.fields.end);
      const exp = expected[i];
      if (gotTo !== exp.to) {
        return record(name, false, `MOBILE_TABS[${i}].to 应为 "${exp.to}"，实际 "${gotTo}"`);
      }
      if (gotLabel !== exp.label) {
        return record(name, false, `MOBILE_TABS[${i}].label 应为 "${exp.label}"，实际 "${gotLabel}"`);
      }
      if (gotEnd !== exp.end) {
        return record(name, false, `MOBILE_TABS[${i}].end 应为 ${exp.end}，实际 ${gotEnd}`);
      }
      if (!navToSet.has(exp.to)) {
        return record(name, false, `MOBILE_TABS[${i}].to "${exp.to}" 不在 NAV_ITEMS 中`);
      }
      if (!routesPaths.has(exp.to)) {
        return record(name, false, `MOBILE_TABS[${i}].to "${exp.to}" 不在 Routes path 中`);
      }
    }
    record(name, true);
  } catch (e) {
    record(name, false, `解析异常: ${e.message}`);
  }
})();

// ---------- Check 2 ----------
(function check2() {
  const name = '2. 更多动作表 actions 顺序与路由映射';
  try {
    const arr = extractArrayLiteral(appSrc, 'actions');
    if (!arr) return record(name, false, '未找到 actions 数组字面量');
    const items = parseObjectEntries(arr);
    if (items.length !== 7) return record(name, false, `actions 项数应为 7，实际 ${items.length}`);

    const expectedKeys = ['pomodoro', 'vocab', 'weekly', 'heatmap', 'data', 'theme', 'logout'];
    for (let i = 0; i < expectedKeys.length; i++) {
      const k = parseStringLiteral(items[i].fields.key);
      if (k !== expectedKeys[i]) {
        return record(name, false, `actions[${i}].key 应为 "${expectedKeys[i]}"，实际 "${k}"`);
      }
    }

    const routesPaths = new Set(extractRoutesPaths(appSrc));

    const toKeys = ['pomodoro', 'vocab', 'weekly', 'heatmap', 'data'];
    for (let i = 0; i < toKeys.length; i++) {
      const item = items[i];
      const to = parseStringLiteral(item.fields.to);
      if (!to) {
        return record(name, false, `actions[${i}] (${toKeys[i]}) 缺少 to 字段`);
      }
      if (!routesPaths.has(to)) {
        return record(name, false, `actions[${i}] (${toKeys[i]}) 的 to "${to}" 不在 Routes path 中`);
      }
      if ('onSelect' in item.fields) {
        return record(name, false, `actions[${i}] (${toKeys[i]}) 不应含 onSelect`);
      }
    }

    for (const idx of [5, 6]) {
      const item = items[idx];
      const key = expectedKeys[idx];
      if (!('onSelect' in item.fields)) {
        return record(name, false, `actions[${idx}] (${key}) 必须含 onSelect`);
      }
      if ('to' in item.fields) {
        return record(name, false, `actions[${idx}] (${key}) 不应含 to`);
      }
    }
    record(name, true);
  } catch (e) {
    record(name, false, `解析异常: ${e.message}`);
  }
})();

// ---------- Check 3 ----------
(function check3() {
  const name = '3. MobileNav 10 个类名在 index.css 中存在';
  try {
    const classes = [
      'mobile-nav',
      'mobile-nav-tab',
      'mobile-sheet-mask',
      'mobile-sheet',
      'mobile-sheet-header',
      'mobile-sheet-user',
      'mobile-sheet-countdown',
      'mobile-sheet-list',
      'mobile-sheet-item',
      'mobile-sheet-cancel',
    ];
    const missing = [];
    for (const cls of classes) {
      const escaped = cls.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      // match `.cls` where next char is not [\w-]
      const re = new RegExp(`\\.${escaped}(?![\\w-])`);
      if (!re.test(cssSrc)) missing.push(cls);
    }
    if (missing.length) return record(name, false, `index.css 中缺少类名: ${missing.join(', ')}`);
    record(name, true);
  } catch (e) {
    record(name, false, `解析异常: ${e.message}`);
  }
})();

// ---------- Check 4 ----------
(function check4() {
  const name = '4. 移动端媒体查询 sidebar/mobile-nav/main 关键样式';
  try {
    const blocks = extractMobileMediaBlocks(cssSrc);
    if (blocks.length === 0) return record(name, false, '未找到 @media (max-width: 768px) 块');

    let sidebarDisplay = null;
    let mobileNavDisplay = null;
    let mobileNavHeightFirstPx = null;
    let mainPaddingFirstPx = null;

    for (const b of blocks) {
      const sb = findRuleBody(b, '.sidebar');
      if (sb) {
        const d = declValue(sb, 'display');
        if (d && d.toLowerCase() === 'none') sidebarDisplay = 'none';
      }
      const mn = findRuleBody(b, '.mobile-nav');
      if (mn) {
        const d = declValue(mn, 'display');
        if (d) mobileNavDisplay = d.trim();
        const h = declValue(mn, 'height');
        if (h) {
          const n = firstPxNumber(h);
          if (n !== null) mobileNavHeightFirstPx = n;
        }
      }
      const main = findRuleBody(b, '.main');
      if (main) {
        const p = declValue(main, 'padding-bottom');
        if (p) {
          const n = firstPxNumber(p);
          if (n !== null) mainPaddingFirstPx = n;
        }
      }
    }

    if (sidebarDisplay !== 'none') return record(name, false, '.sidebar display 在 768px 块中应为 none');
    if (!mobileNavDisplay || mobileNavDisplay.toLowerCase() !== 'flex') {
      return record(name, false, '.mobile-nav display 在 768px 块中应为 flex');
    }
    if (mobileNavHeightFirstPx === null || mobileNavHeightFirstPx < 60) {
      return record(name, false, `.mobile-nav height 第一个 px 值应 >= 60，实际 ${mobileNavHeightFirstPx}`);
    }
    if (mainPaddingFirstPx === null || mainPaddingFirstPx < 60) {
      return record(name, false, `.main padding-bottom 第一个 px 值应 >= 60，实际 ${mainPaddingFirstPx}`);
    }
    record(name, true);
  } catch (e) {
    record(name, false, `解析异常: ${e.message}`);
  }
})();

// ---------- Check 5 ----------
(function check5() {
  const name = '5. 触控目标 padding/font-size 尺寸';
  try {
    const itemBody = findRuleBody(cssSrc, '.mobile-sheet-item');
    const cancelBody = findRuleBody(cssSrc, '.mobile-sheet-cancel');
    if (!itemBody) return record(name, false, '未找到 .mobile-sheet-item 规则');
    if (!cancelBody) return record(name, false, '未找到 .mobile-sheet-cancel 规则');

    const itemPad = declValue(itemBody, 'padding');
    const itemFs = declValue(itemBody, 'font-size');
    const cancelPad = declValue(cancelBody, 'padding');
    const cancelFs = declValue(cancelBody, 'font-size');

    const itemPadV = firstNumericValue(itemPad);
    const itemFsV = firstNumericValue(itemFs);
    const cancelPadV = firstNumericValue(cancelPad);
    const cancelFsV = firstNumericValue(cancelFs);

    if (itemPadV === null || itemPadV < 12) {
      return record(name, false, `.mobile-sheet-item padding 第一个数值应 >= 12，实际 ${itemPadV}`);
    }
    if (itemFsV === null || itemFsV < 14) {
      return record(name, false, `.mobile-sheet-item font-size 应 >= 14，实际 ${itemFsV}`);
    }
    if (cancelPadV === null || cancelPadV < 12) {
      return record(name, false, `.mobile-sheet-cancel padding 第一个数值应 >= 12，实际 ${cancelPadV}`);
    }
    if (cancelFsV === null || cancelFsV < 14) {
      return record(name, false, `.mobile-sheet-cancel font-size 应 >= 14，实际 ${cancelFsV}`);
    }
    record(name, true);
  } catch (e) {
    record(name, false, `解析异常: ${e.message}`);
  }
})();

// ---------- Check 6 ----------
(function check6() {
  const name = '6. 桌面端 .mobile-nav 不得 display: flex';
  try {
    const desktopCss = extractDesktopCss(cssSrc);
    // find .mobile-nav rule in desktop css (exact class, not .mobile-nav-tab)
    const re = /\.mobile-nav(?![-\w])/g;
    let m;
    while ((m = re.exec(desktopCss))) {
      // find next '{' and rule body
      let i = m.index + m[0].length;
      while (i < desktopCss.length && /\s/.test(desktopCss[i])) i++;
      if (desktopCss[i] !== '{') continue;
      let depth = 1;
      const start = i + 1;
      let inStr = null;
      let inComment = false;
      i++;
      for (; i < desktopCss.length; i++) {
        const ch = desktopCss[i];
        if (inComment) {
          if (ch === '*' && desktopCss[i + 1] === '/') { inComment = false; i++; }
          continue;
        }
        if (inStr) {
          if (ch === '\\') { i++; continue; }
          if (ch === inStr) inStr = null;
          continue;
        }
        if (ch === '/' && desktopCss[i + 1] === '*') { inComment = true; i++; continue; }
        if (ch === '"' || ch === "'") { inStr = ch; continue; }
        if (ch === '{') depth++;
        else if (ch === '}') {
          depth--;
          if (depth === 0) break;
        }
      }
      const body = desktopCss.slice(start, i);
      const d = declValue(body, 'display');
      if (d && d.trim().toLowerCase() === 'flex') {
        return record(name, false, '桌面端 CSS 中 .mobile-nav 出现了 display: flex');
      }
    }
    record(name, true);
  } catch (e) {
    record(name, false, `解析异常: ${e.message}`);
  }
})();

// ---------- Check 7 ----------
(function check7() {
  const name = '7. 11 页移动端 CSS 覆盖';
  try {
    const blocks = extractMobileMediaBlocks(cssSrc);
    if (blocks.length === 0) return record(name, false, '未找到 @media (max-width: 768px) 块');
    const allMobileCss = blocks.join('\n');

    const groups = [
      ['仪表盘', 'dash-'],
      ['复习计划', 'plans-'],
      ['番茄专注', 'pomo-'],
      ['错题本', 'mistakes-'],
      ['单词', 'flashcard'],
      ['词库浏览', 'vocab-'],
      ['真题统计', 'exams-'],
      ['周报', 'wk-'],
      ['自律热力图', 'hm-'],
      ['数据导入导出', 'data-transfer'],
      ['登录', 'login-'],
    ];

    const missing = [];
    for (const [label, token] of groups) {
      if (!allMobileCss.includes(token)) missing.push(`${label}(${token})`);
    }
    if (missing.length) return record(name, false, `缺少 token: ${missing.join(', ')}`);
    record(name, true);
  } catch (e) {
    record(name, false, `解析异常: ${e.message}`);
  }
})();

// ---------- Check 8 ----------
(function check8() {
  const name = '8. 脚本 ESM 路径与输出格式自检';
  try {
    // ESM: fileURLToPath 已经工作，说明 import.meta.url 正常
    // 路径解析: APP_PATH / CSS_PATH 应位于 ../../src/
    const expectedApp = resolve(__dirname, '../src/App.tsx');
    const expectedCss = resolve(__dirname, '../src/index.css');
    if (APP_PATH !== expectedApp) {
      return record(name, false, `App.tsx 路径解析错误: ${APP_PATH}`);
    }
    if (CSS_PATH !== expectedCss) {
      return record(name, false, `index.css 路径解析错误: ${CSS_PATH}`);
    }
    // 文件均已成功读取
    if (typeof appSrc !== 'string' || appSrc.length === 0) {
      return record(name, false, 'App.tsx 内容为空');
    }
    if (typeof cssSrc !== 'string' || cssSrc.length === 0) {
      return record(name, false, 'index.css 内容为空');
    }
    record(name, true);
  } catch (e) {
    record(name, false, `解析异常: ${e.message}`);
  }
})();

// ---------- summary ----------
const total = results.length;
const passed = results.filter((r) => r.ok).length;
const failed = total - passed;

console.log('');
console.log(`共 ${total} 项，通过 ${passed} 项，失败 ${failed} 项`);

process.exit(failed === 0 ? 0 : 1);
