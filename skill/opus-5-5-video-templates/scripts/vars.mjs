#!/usr/bin/env node
// Lists a project's variables, or sets their values.
//
//   node scripts/vars.mjs <folder>               print every variable
//   node scripts/vars.mjs <folder> values.json   write those values, then print
//
// values.json is one object, e.g. {"brand": "Acme", "accent": "#2459d6"}.
// The values become the composition's defaults in index.html, so
// `hyperframes preview`, `snapshot` and `render` all use them without flags.
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const [folder, valuesFile] = process.argv.slice(2);
if (!folder) {
  console.error('usage: node scripts/vars.mjs <folder> [values.json]');
  process.exit(1);
}

const file = path.join(folder, 'index.html');
const html = readFileSync(file, 'utf8');
const match = html.match(/data-composition-variables='([\s\S]*?)'/);
if (!match) {
  console.error(`no data-composition-variables in ${file}`);
  process.exit(1);
}
const vars = JSON.parse(match[1]);

if (valuesFile) {
  const values = JSON.parse(readFileSync(valuesFile, 'utf8'));
  const unknown = Object.keys(values).filter(
    (key) => !vars.some((v) => v.id === key)
  );
  if (unknown.length) {
    console.error(`not variables of this template: ${unknown.join(', ')}`);
    process.exit(1);
  }
  for (const v of vars) {
    if (!(v.id in values)) continue;
    const value = String(values[v.id]);
    if (v.type === 'color' && !/^#[0-9a-fA-F]{6}$/.test(value)) {
      console.error(`${v.id} must be a #rrggbb color, got "${value}"`);
      process.exit(1);
    }
    v.default = value;
  }
  // \u escapes keep quotes and markup in the values from breaking the
  // single-quoted HTML attribute; JSON.parse turns them back into text
  const json = JSON.stringify(vars, null, 2)
    .replace(/'/g, '\\u0027')
    .replace(/</g, '\\u003c')
    .replace(/&/g, '\\u0026');
  writeFileSync(
    file,
    html.replace(match[0], () => `data-composition-variables='${json}'`)
  );
  console.log(`set ${Object.keys(values).length} variables in ${file}\n`);
}

for (const v of vars) {
  console.log(`${v.id} (${v.type}) = ${JSON.stringify(v.default)}`);
  console.log(`    ${v.label}`);
}
