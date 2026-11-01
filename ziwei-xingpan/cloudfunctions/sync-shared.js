'use strict';

// Sync shared modules into each cloud function directory.
// Why: a cloud function is uploaded as its own directory, so a
// require('../_shared/...') would break at runtime. Each function dir
// therefore carries a materialized copy under ./shared/.
// Rule: edit only cloudfunctions/_shared/*, then run:
//   node cloudfunctions/sync-shared.js
// and deploy the function dirs (each now self-contained).

const fs = require('fs');
const path = require('path');

const root = path.join(__dirname);
const sharedDir = path.join(root, '_shared');
const functions = [
  'login', 'charts', 'membership', 'order', 'points',
  'invite', 'ai', 'aiImage', 'config', 'feedback'
];

const files = fs.readdirSync(sharedDir).filter(function (f) { return f.endsWith('.js'); });
for (const fn of functions) {
  const target = path.join(root, fn, 'shared');
  fs.mkdirSync(target, { recursive: true });
  for (const file of files) {
    fs.copyFileSync(path.join(sharedDir, file), path.join(target, file));
  }
  console.log('synced ' + fn + ' (' + files.length + ' files)');
}
console.log('done');
