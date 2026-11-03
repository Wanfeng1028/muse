#!/usr/bin/env node
// Maintainer only. Copies the render engine of the Editing IA Pro kit (its short-editing skill) into the free
// short-editing skill: the engine code, its references, the icon sources and the music index.
//   node scripts/sync-engine.mjs [--from <kit skills dir>] [--dry-run]
// Files owned by this repo (KEEP) are never overwritten. Generated files (node_modules, music mp3s, icon PNGs) never ship.
// Files gone from the source are moved to the Trash.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const argv = process.argv.slice(2);
const opt = k => { const i = argv.indexOf(`--${k}`); return i < 0 ? null : argv[i + 1]; };
const DRY = argv.includes('--dry-run');
const FROM = path.resolve((opt('from') || '~/Developer/courses/editing-ia-pro/skills').replace(/^~/, os.homedir()));
const DST = path.join(REPO, 'skills/short-editing');

// [source folder or file in the kit, destination in skills/short-editing]
const MAP = [
  ['short-editing/engine', 'engine'],
  ['short-editing/references/design-system.md', 'references/design-system.md'],
  ['short-editing/references/scene-library.md', 'references/scene-library.md'],
  ['short-editing/references/shorts-codes.md', 'references/shorts-codes.md'],
  ['short-editing/references/music.md', 'references/music.md'],
  ['short-editing/references/performance.md', 'references/performance.md'],
  ['short-editing/references/sub-agents.md', 'references/sub-agents.md'],
  ['studio-setup/references/style-schema.md', 'references/style-schema.md'],
  ['short-editing/assets/icons/build-icons.mjs', 'assets/icons/build-icons.mjs'],
  ['short-editing/assets/icons/svg', 'assets/icons/svg'],
  ['short-editing/assets/music/tracks.json', 'assets/music/tracks.json'],
  ['studio-setup/assets/looks.json', 'assets/looks.json'],
];
// never copied: dependencies, and the variants tool (it needs the review studio of the paid kit)
const EXCLUDE = [/(^|\/)node_modules(\/|$)/, /(^|\/)\.DS_Store$/, /^engine\/variant\.mjs$/];
// written in this repo, never overwritten
const KEEP = ['engine/setup.mjs', 'engine/whisper.mjs'];

// [file pattern, from, to]: every rule must match at least once, so a source change that breaks one is reported
const TRANSFORMS = [
  // no ElevenLabs key: words come from whisper.cpp on this computer (engine/whisper.mjs), same assets/words-scribe.json
  [/^engine\/short\.mjs$/, 'const key = elevenKey(), t0 = Date.now();',
    "let key; try { key = elevenKey(); } catch { return (await import('./whisper.mjs')).whisperWords(PROJ, lang, wav, log); }\n  const t0 = Date.now();"],
  [/^engine\/short\.mjs$/, '//   node short.mjs words   <project> [lang]     ElevenLabs Scribe word timestamps',
    '//   node short.mjs words   <project> [lang]     word timestamps: whisper.cpp on this computer (ElevenLabs Scribe when ELEVEN_KEY is set)'],
  // the creator profile of the free pack is the project's video-agent/ folder (styles in video-agent/styles/<name>/style.json)
  [/^engine\/short\.mjs$/, "if (d !== os.homedir() && fs.existsSync(path.join(d, '.short-editing'))) return path.join(d, '.short-editing');",
    "if (d !== os.homedir() && (fs.existsSync(path.join(d, '.short-editing')) || fs.existsSync(path.join(d, 'video-agent')))) return path.join(d, fs.existsSync(path.join(d, '.short-editing')) ? '.short-editing' : 'video-agent');"],
  // the free pack has no profile.mjs / preview.mjs: say where its profile lives
  [/^references\/style-schema\.md$/, '# Creator profile: style.json\n',
    '# Creator profile: style.json\n\nIn this free pack the profile folder is `<project>/video-agent/` (it plays the role of `.short-editing/` below): `video-agent/styles/<name>/style.json`, edited by hand. `profile.mjs` and `preview.mjs` belong to the paid kit; check a change with `short.mjs stills`.\n'],
  // free default look: the system font, the camera full width (no framed card), white captions with no block on the video
  [/^engine\/lib\/kit\.js$/, "export const famCss = f => /^[A-Za-z ]+$/.test(f)", "export const famCss = f => /^[A-Za-z ,-]+$/.test(f)"],
  [/^assets\/looks\.json$/, "  \"default\": {\n    \"label\": \"Papier classique\",",
    "  \"default\": {\n    \"label\": \"Minimal\",\n    \"says\": \"Le style par défaut : papier texturé, police système (celle du Mac), caméra pleine largeur, sous-titres en capitales mono, blancs sur un bandeau noir posé sur la jointure.\",\n    \"style\": {\"font\": {\"family\": \"system-ui, -apple-system, Segoe UI, Helvetica Neue, Arial, sans-serif\"}, \"display\": {\"font\": \"system-ui, -apple-system, Segoe UI, Helvetica Neue, Arial, sans-serif\", \"weight\": 800, \"text\": \"system-ui, -apple-system, Segoe UI, Helvetica Neue, Arial, sans-serif\", \"title\": \"ink2\", \"flat\": true}, \"captions\": {\"style\": \"band\", \"font\": \"JetBrains Mono\", \"weight\": 800, \"size\": 60, \"maxWords\": 3, \"upper\": true, \"bg\": \"#111111\", \"color\": \"#FFFFFF\", \"radius\": 0.2, \"shadow\": true, \"tracking\": -0.02, \"straddle\": true}, \"layout\": {\"frame\": {\"bleed\": true, \"r\": 0}, \"seam\": 1160}}\n  },\n  \"classique\": {\n    \"label\": \"Papier classique\","],
  [/^engine\/short\.mjs$/, "const KEYFILES = () => [path.join(HOME(), '.env'), ", "const KEYFILES = () => [path.join(HOME(), '.env'), path.join(process.cwd(), '.env'), "],
  [/^engine\/audio\.mjs$/, "  if (bed && !fs.existsSync(bed)) throw new Error(", "  // free pack: the beds are not in git, each one is generated in code the first time it is used (about 30 s)\n  if (bed && !fs.existsSync(bed) && JSON.parse(fs.readFileSync(path.join(lib, 'tracks.json'), 'utf8')).some(x => x.id === raw.music.bed)) {\n    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'bed-'));\n    console.log(`[audio] music: generating the \"${raw.music.bed}\" bed once (about 30 s)`);\n    execFileSync(process.execPath, [path.join(path.dirname(fileURLToPath(import.meta.url)), 'music.mjs'), raw.music.bed, '--out', tmp], { stdio: 'inherit' });\n    if (fs.existsSync(path.join(tmp, `${raw.music.bed}.mp3`))) fs.copyFileSync(path.join(tmp, `${raw.music.bed}.mp3`), bed);\n  }\n  if (bed && !fs.existsSync(bed)) throw new Error("],
];
// anything still matching after the transforms is reported (fix it in the kit or add a transform)
const LEAKS = /melvyn|portly|lepodcast|Brain\/video-editing|~\/cc\b|steveclaw|hermes|tella-to-short/i;
const NO_LEAK_SCAN = /(^|\/)package-lock\.json$|\.svg$/;

const rel = (root, f) => path.relative(root, f).split(path.sep).join('/');
const walk = d => !fs.existsSync(d) ? [] : fs.statSync(d).isFile() ? [d] : fs.readdirSync(d, { withFileTypes: true }).flatMap(e => {
  const f = path.join(d, e.name);
  return e.isDirectory() ? walk(f) : e.isFile() ? [f] : [];
});
const TEXT = /\.(md|js|mjs|cjs|json|html|swift|txt)$/;

let copied = 0, same = 0, removed = 0;
const used = new Set(), leaks = [], want = new Set();
for (const [from, to] of MAP) {
  const src = path.join(FROM, from);
  if (!fs.existsSync(src)) { console.error(`missing ${src}`); process.exit(1); }
  const single = fs.statSync(src).isFile();
  for (const f of walk(src)) {
    const r = single ? to : `${to}/${rel(src, f)}`;
    if (EXCLUDE.some(x => x.test(r))) continue;
    want.add(r);
    if (KEEP.includes(r)) continue;
    const dst = path.join(DST, r);
    let buf = fs.readFileSync(f);
    if (TEXT.test(r)) {
      let s = buf.toString('utf8');
      TRANSFORMS.forEach(([re, a, b], i) => {
        if (!re.test(r)) return;
        const next = typeof a === 'string' ? s.split(a).join(b) : s.replace(a, b);
        if (next !== s) used.add(i);
        s = next;
      });
      if (!NO_LEAK_SCAN.test(r)) s.split('\n').forEach((l, n) => { if (LEAKS.test(l)) leaks.push(`${r}:${n + 1}: ${l.trim().slice(0, 140)}`); });
      buf = Buffer.from(s, 'utf8');
    }
    if (fs.existsSync(dst) && fs.readFileSync(dst).equals(buf)) { same++; continue; }
    copied++;
    if (DRY) { console.log(`copy  ${r}`); continue; }
    fs.mkdirSync(path.dirname(dst), { recursive: true });
    fs.writeFileSync(dst, buf);
    if (fs.statSync(f).mode & 0o111) fs.chmodSync(dst, 0o755);
  }
}

// files that disappeared from the kit go to the Trash (only inside the synced folders)
for (const [, to] of MAP) for (const f of walk(path.join(DST, to))) {
  const r = rel(DST, f);
  if (want.has(r) || KEEP.includes(r) || EXCLUDE.some(x => x.test(r))) continue;
  if (/^assets\/(music\/.*\.mp3|icons\/.*\.png)$/.test(r)) continue;   // generated on the creator's computer
  removed++;
  if (DRY) { console.log(`trash ${r}`); continue; }
  execFileSync('trash', [f]);
}

const unused = TRANSFORMS.filter((t, i) => !used.has(i));
console.log(`${DRY ? '[dry run] ' : ''}${copied} copied, ${same} unchanged, ${removed} trashed (from ${FROM.replace(os.homedir(), '~')})`);
for (const t of unused) console.log(`warning: transform matched nothing: ${String(t[1]).slice(0, 80)}`);
for (const l of leaks) console.log(`leak: ${l}`);
process.exit(leaks.length || unused.length ? 2 : 0);
