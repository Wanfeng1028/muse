#!/usr/bin/env node
/*
 * i18n key checker for drama-factory static console.
 *
 * Usage:
 *   cd drama-factory
 *   node scripts/i18n-keycheck.js
 *
 * Exit codes:
 *   0 - no MISSING keys (UNUSED may still be reported as warnings)
 *   1 - MISSING keys found
 *
 * This script has zero third-party dependencies. It uses regex-based
 * scanning rather than a full JS parser; malformed files are reported
 * as warnings and skipped instead of crashing the run.
 */
'use strict';

const fs = require('fs');
const path = require('path');

const STATIC_DIR = path.resolve(__dirname, '..', 'src', 'main', 'resources', 'static');

function walk(dir, ext, out) {
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch (e) {
    return;
  }
  for (const ent of entries) {
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) {
      if (ent.name === 'node_modules' || ent.name === '.git') continue;
      walk(full, ext, out);
    } else if (ent.isFile() && full.endsWith(ext)) {
      out.push(full);
    }
  }
}

function readFileSafe(file) {
  try {
    return fs.readFileSync(file, 'utf8');
  } catch (e) {
    return null;
  }
}

function rel(file) {
  return path.relative(process.cwd(), file) || file;
}

function warn(msg) {
  process.stderr.write('warning: ' + msg + '\n');
}

// ---------- HTML scanning ----------

const HTML_ATTR_RE = /data-i18n(?:-ph|-title)?\s*=\s*"([^"]*)"/g;

function scanHtml(file, text, used) {
  let m;
  HTML_ATTR_RE.lastIndex = 0;
  while ((m = HTML_ATTR_RE.exec(text)) !== null) {
    const key = m[1].trim();
    if (key) used.add(key);
  }
}

// ---------- JS scanning ----------

// Match a single-quoted or double-quoted string literal, no interpolation.
const STR_RE = /'([^'\\\n]*)'|"([^"\\\n]*)"/;

function unquote(str) {
  return str;
}

// Extract the first-level keys of a literal object starting at `braceIndex`.
// Returns array of keys or null if parsing fails / contains spread.
function parseLiteralObjectKeys(text, braceIndex) {
  let i = braceIndex;
  // text[i] should be '{'
  if (text[i] !== '{') return null;
  i++;
  const keys = [];
  let depth = 1;
  let sawSpread = false;

  while (i < text.length) {
    // skip whitespace and comments
    while (i < text.length && /\s/.test(text[i])) i++;
    if (i >= text.length) break;

    if (text[i] === '}') {
      depth--;
      i++;
      if (depth === 0) return sawSpread ? null : keys;
      continue;
    }
    if (text[i] === ',') { i++; continue; }

    // comments
    if (text[i] === '/' && text[i + 1] === '/') {
      while (i < text.length && text[i] !== '\n') i++;
      continue;
    }
    if (text[i] === '/' && text[i + 1] === '*') {
      i += 2;
      while (i < text.length && !(text[i] === '*' && text[i + 1] === '/')) i++;
      i += 2;
      continue;
    }

    // spread
    if (text[i] === '.' && text[i + 1] === '.' && text[i + 2] === '.') {
      sawSpread = true;
      // skip to next top-level comma or closing brace
      i += 3;
      let inner = 0;
      while (i < text.length) {
        const c = text[i];
        if (c === '{' || c === '(' || c === '[') inner++;
        else if (c === '}' || c === ')' || c === ']') {
          if (inner === 0 && c === '}') break;
          inner--;
        } else if (c === ',' && inner === 0) break;
        i++;
      }
      continue;
    }

    // computed key
    if (text[i] === '[') {
      warn('computed key in object literal; skipping whole object');
      return null;
    }

    // Try to read a key: string literal or identifier
    let key = null;
    if (text[i] === '\'' || text[i] === '"') {
      const q = text[i];
      i++;
      let buf = '';
      let closed = false;
      while (i < text.length) {
        const c = text[i];
        if (c === '\\') { buf += text[i + 1]; i += 2; continue; }
        if (c === q) { closed = true; i++; break; }
        buf += c;
        i++;
      }
      if (!closed) return null;
      key = buf;
    } else if (/[A-Za-z_$]/.test(text[i])) {
      let buf = '';
      while (i < text.length && /[A-Za-z0-9_$]/.test(text[i])) {
        buf += text[i];
        i++;
      }
      key = buf;
    } else {
      // unrecognized token; bail
      return null;
    }

    // skip whitespace
    while (i < text.length && /\s/.test(text[i])) i++;
    if (text[i] !== ':') {
      // shorthand or method; skip
    } else {
      keys.push(key);
      i++; // skip ':'
      // skip value to next top-level comma or closing brace
      let inner = 0;
      while (i < text.length) {
        const c = text[i];
        if (c === '\'' || c === '"' || c === '`') {
          const q = c;
          i++;
          while (i < text.length) {
            if (text[i] === '\\') { i += 2; continue; }
            if (text[i] === q) { i++; break; }
            i++;
          }
          continue;
        }
        if (c === '/' && text[i + 1] === '/') {
          while (i < text.length && text[i] !== '\n') i++;
          continue;
        }
        if (c === '/' && text[i + 1] === '*') {
          i += 2;
          while (i < text.length && !(text[i] === '*' && text[i + 1] === '/')) i++;
          i += 2;
          continue;
        }
        if (c === '{' || c === '(' || c === '[') inner++;
        else if (c === '}' || c === ')' || c === ']') {
          if (inner === 0 && c === '}') break;
          inner--;
        } else if (c === ',' && inner === 0) break;
        i++;
      }
    }
  }
  return sawSpread ? null : keys;
}

// Scan `DFI18N.register({ ... })` / `DFI18N.register(IDENT)` / `register(IDENT)` calls in a JS file.
// IDENT 形式会回查同一文件内的 `var IDENT = { ... }` 字面量。
function scanRegisterCalls(file, text, defined) {
  var re = /(?:DFI18N\s*\.\s*)?register\s*\(\s*(\{|[A-Za-z_$][A-Za-z0-9_$]*)/g;
  var m;
  while ((m = re.exec(text)) !== null) {
    // 跳过 `function register(` 定义本身
    var before = text.slice(Math.max(0, m.index - 9), m.index);
    if (/function\s*$/.test(before)) continue;
    var keys = null;
    if (m[1] === '{') {
      var braceIndex = m.index + m[0].length - 1;
      keys = parseLiteralObjectKeys(text, braceIndex);
    } else {
      keys = resolveVarObjectKeys(text, m[1]);
    }
    if (keys == null) {
      warn(rel(file) + ': register(' + m[1] + ') could not be fully parsed (variable/spread) — keys skipped');
      continue;
    }
    keys.forEach(function (k) { defined.add(k); });
  }
}

// 在文本中查找 `var IDENT = { ... }`（或 `IDENT = { ... }`）并解析字面量 key。
function resolveVarObjectKeys(text, name) {
  var re = new RegExp('\\b' + name.replace(/[$]/g, '\\$') + '\\s*=\\s*\\{', 'g');
  var m = re.exec(text);
  if (!m) return null;
  var braceIndex = m.index + m[0].length - 1;
  return parseLiteralObjectKeys(text, braceIndex);
}

// Scan a variable named `*_I18N` assigned to a literal object.
function scanI18nVars(file, text, defined) {
  const re = /\b([A-Za-z_$][A-Za-z0-9_$]*_I18N)\s*=\s*\{/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const braceIndex = m.index + m[0].length - 1;
    const keys = parseLiteralObjectKeys(text, braceIndex);
    if (keys == null) {
      warn(rel(file) + ': ' + m[1] + ' literal object could not be fully parsed (variable/spread) — keys skipped');
      continue;
    }
    keys.forEach(function (k) { defined.add(k); });
  }
}

// Scan tr('...') / _t('...') / DFI18N.tr('...') calls.
function scanTrCalls(text, used) {
  const re = /(?:DFI18N\s*\.\s*tr|\btr|\b_t)\s*\(\s*(['"])([^'"\\\n]*)\1/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const key = m[2].trim();
    if (key) used.add(key);
  }
}

// ---------- main ----------

function main() {
  if (!fs.existsSync(STATIC_DIR)) {
    process.stderr.write('error: static dir not found: ' + STATIC_DIR + '\n');
    process.exit(2);
  }

  const htmlFiles = [];
  const jsFiles = [];
  walk(STATIC_DIR, '.html', htmlFiles);
  walk(STATIC_DIR, '.js', jsFiles);

  const used = new Set();
  const defined = new Set();

  for (const f of htmlFiles) {
    const text = readFileSafe(f);
    if (text == null) { warn('cannot read ' + rel(f)); continue; }
    try {
      scanHtml(f, text, used);
    } catch (e) {
      warn(rel(f) + ': ' + e.message);
    }
    // 内联 <script> 里也可能定义字典（login.html/register.html 的 LOGIN_I18N/REG_I18N）
    try {
      scanRegisterCalls(f, text, defined);
      scanI18nVars(f, text, defined);
    } catch (e) {
      warn(rel(f) + ': inline script dict scan failed: ' + e.message);
    }
  }

  for (const f of jsFiles) {
    const text = readFileSafe(f);
    if (text == null) { warn('cannot read ' + rel(f)); continue; }
    try {
      scanRegisterCalls(f, text, defined);
    } catch (e) {
      warn(rel(f) + ': register scan failed: ' + e.message);
    }
    try {
      scanI18nVars(f, text, defined);
    } catch (e) {
      warn(rel(f) + ': *_I18N scan failed: ' + e.message);
    }
    try {
      scanTrCalls(text, used);
    } catch (e) {
      warn(rel(f) + ': tr() scan failed: ' + e.message);
    }
  }

  const missing = [];
  used.forEach(function (k) {
    if (!defined.has(k)) missing.push(k);
  });
  missing.sort();

  const unused = [];
  defined.forEach(function (k) {
    if (!used.has(k)) unused.push(k);
  });
  unused.sort();

  process.stdout.write('i18n key check\n');
  process.stdout.write('  html files:  ' + htmlFiles.length + '\n');
  process.stdout.write('  js files:    ' + jsFiles.length + '\n');
  process.stdout.write('  defined keys: ' + defined.size + '\n');
  process.stdout.write('  used keys:    ' + used.size + '\n\n');

  if (missing.length) {
    process.stdout.write('MISSING (' + missing.length + ') — used but not defined:\n');
    missing.forEach(function (k) { process.stdout.write('  - ' + k + '\n'); });
    process.stdout.write('\n');
  } else {
    process.stdout.write('MISSING: none\n\n');
  }

  if (unused.length) {
    process.stdout.write('UNUSED (' + unused.length + ') — defined but never referenced (safe to clean up):\n');
    unused.forEach(function (k) { process.stdout.write('  - ' + k + '\n'); });
    process.stdout.write('\n');
  } else {
    process.stdout.write('UNUSED: none\n\n');
  }

  process.stdout.write('OK: ' + (defined.size - unused.length) + ' key(s) matched, ' + missing.length + ' missing\n');

  process.exit(missing.length ? 1 : 0);
}

main();
