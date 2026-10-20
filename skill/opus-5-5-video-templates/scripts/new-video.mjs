#!/usr/bin/env node
// Copies one template into a new project folder.
//
//   node scripts/new-video.mjs <template> [folder]
//
// <template> is a template id (23-caption-app-promo) or its number (23).
// [folder] defaults to the template id, in the current directory.
import {
  cpSync,
  existsSync,
  readdirSync,
  readFileSync,
  writeFileSync,
} from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const skillDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const templatesDir = path.join(skillDir, 'templates');
const [query, folder] = process.argv.slice(2);

const ids = readdirSync(templatesDir)
  .filter((name) => /^\d\d-/.test(name))
  .sort();

if (!query) {
  console.error(
    'usage: node scripts/new-video.mjs <template id or number> [folder]'
  );
  console.error(`templates:\n  ${ids.join('\n  ')}`);
  process.exit(1);
}

const id = ids.find(
  (name) => name === query || name.slice(0, 2) === query.padStart(2, '0')
);
if (!id) {
  console.error(`no template "${query}". Templates:\n  ${ids.join('\n  ')}`);
  process.exit(1);
}

const target = path.resolve(folder || id);
if (existsSync(target)) {
  console.error(`${target} already exists; pick another folder name`);
  process.exit(1);
}

cpSync(path.join(templatesDir, id), target, { recursive: true });

const pkgFile = path.join(target, 'package.json');
if (existsSync(pkgFile)) {
  const pkg = JSON.parse(readFileSync(pkgFile, 'utf8'));
  pkg.name = path.basename(target).toLowerCase().replace(/[^a-z0-9-]+/g, '-');
  writeFileSync(pkgFile, `${JSON.stringify(pkg, null, 2)}\n`);
}

console.log(`created ${target} from ${id}`);
console.log(
  `next: node ${path.join(skillDir, 'scripts', 'vars.mjs')} ${path.relative(process.cwd(), target) || '.'}`
);
