// Dump every component's contract (id, role, desc, params, sfx_hints, invert support) as JSON.
// Components are ES modules with no DOM access at import time, so Node can read them.
//   node timeline/dump_specs.mjs            -> all components/*.js
import { readdirSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
const dir = join(dirname(fileURLToPath(import.meta.url)), '..', 'components');
const out = {};
for (const f of readdirSync(dir).filter(f => f.endsWith('.js')).sort()) {
  const m = await import(pathToFileURL(join(dir, f)).href);
  const c = m.default || m;
  out[c.id] = { id: c.id, file: f, role: c.role, desc: c.desc, params: c.params, sfx_hints: c.sfx_hints || [], invert: !!c.invert,
    hooks: { draw: typeof c.draw === 'function', bbox: typeof c.bbox === 'function', mbSamples: typeof c.mbSamples === 'function', post: typeof c.post === 'function' } };
}
process.stdout.write(JSON.stringify(out, null, 1));
