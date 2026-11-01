'use strict';

// Client/server contract check (no cloud, no network).
// Parses the client for callFn('functionName', { action: '...' }) call
// sites and asserts each one exists in the matching cloud function:
//   - the function directory must exist, and
//   - when an action literal is given, the function source must mention it.
// Functions called without an action (login, config default get) only need
// the directory to exist. Run:
//   node cloudfunctions/tests/contract-check.js
// Exit code 0 = all call sites covered, 1 = any gap.

const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const clientSrc = path.join(root, '..', 'client', 'src');

function walk(dir, out) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(full, out);
    } else if (entry.name.endsWith('.ts') || entry.name.endsWith('.tsx')) {
      out.push(full);
    }
  }
  return out;
}

const files = walk(clientSrc, []);
// Match the function name first (the generic type argument may contain
// '>' characters, so do not try to parse it); then scan the following
// argument object for an action literal.
const fnRe = /callFn\s*(?:<[\s\S]*?>)?\s*\(\s*'([^']+)'\s*,\s*\{/g;
const calls = [];
for (const file of files) {
  const text = fs.readFileSync(file, 'utf8');
  let m;
  while ((m = fnRe.exec(text)) !== null) {
    const rest = text.slice(fnRe.lastIndex, fnRe.lastIndex + 400);
    const actionMatch = /action:\s*'([^']+)'/.exec(rest);
    calls.push({ fn: m[1], action: actionMatch ? actionMatch[1] : null, file: path.relative(clientSrc, file) });
  }
}

let failures = 0;
const seen = new Set();
for (const call of calls) {
  const key = call.fn + ':' + (call.action || '');
  if (seen.has(key)) {
    continue;
  }
  seen.add(key);
  const fnDir = path.join(root, call.fn);
  const indexJs = path.join(fnDir, 'index.js');
  if (!fs.existsSync(indexJs)) {
    console.error('FAIL function missing: ' + call.fn + ' (called from ' + call.file + ')');
    failures++;
    continue;
  }
  if (call.action) {
    const src = fs.readFileSync(indexJs, 'utf8');
    if (src.indexOf("'" + call.action + "'") === -1) {
      console.error('FAIL action missing: ' + call.fn + '.' + call.action + ' (called from ' + call.file + ')');
      failures++;
      continue;
    }
  }
  console.log('PASS ' + call.fn + (call.action ? '.' + call.action : ' (no action)'));
}

if (calls.length === 0) {
  console.error('FAIL no callFn call sites found in client source');
  process.exit(1);
}

// Second pass: dynamic actions passed as plain string arguments to
// *Action helpers (e.g. chartAction('setDefault', id)) cannot be tied to
// one callFn site by the scan above. Each such literal must still exist
// in at least one cloud function source file.
const serverSources = fs.readdirSync(root, { withFileTypes: true })
  .filter(function (e) { return e.isDirectory() && fs.existsSync(path.join(root, e.name, 'index.js')); })
  .map(function (e) { return fs.readFileSync(path.join(root, e.name, 'index.js'), 'utf8'); })
  .join('\n');
const dynamicRe = /Action\(\s*'([^']+)'/g;
const dynamicSeen = new Set();
for (const file of files) {
  const text = fs.readFileSync(file, 'utf8');
  let m;
  while ((m = dynamicRe.exec(text)) !== null) {
    if (dynamicSeen.has(m[1])) {
      continue;
    }
    dynamicSeen.add(m[1]);
    if (serverSources.indexOf("'" + m[1] + "'") === -1) {
      console.error('FAIL dynamic action missing: ' + m[1] + ' (from ' + path.relative(clientSrc, file) + ')');
      failures++;
    } else {
      console.log('PASS dynamic action ' + m[1]);
    }
  }
}
console.log(seen.size + ' distinct call sites checked, ' + failures + ' failures');
process.exit(failures ? 1 : 0);
