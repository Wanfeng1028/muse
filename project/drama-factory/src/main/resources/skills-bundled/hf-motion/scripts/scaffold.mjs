#!/usr/bin/env node
// Scaffold a HyperFrames project from a hf-motion recipe template.
//
//   node scaffold.mjs <recipe> <out-dir> [key=value ...] [--update] [--no-music]
//   node scaffold.mjs --list
//
// key = a top-level key of the recipe's CONFIG block. Values are coerced to
// the default's type: numbers parse as numbers, lists split on "|" (commas
// are legal inside an item). Text stays literal UTF-8 end to end.
// --update   re-apply to an existing project (reads ITS CONFIG, so hand edits
//            survive) and resync timing attributes + music.
// --no-music skip the music bed (no numpy/ffmpeg needed; used by selfchecks).
//            Recipes without a musicArgs export never generate one.
// A recipe's userAssets ({ configKey: "assets/<file>" }) names CONFIG keys that
// hold a path to the user's own file (relative to the cwd). The scaffold copies
// it into the project and refuses, writing nothing, when it cannot be read.
import { execFileSync } from "node:child_process";
import { accessSync, constants, cpSync, existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const templates = join(here, "..", "templates");
const recipes = () => readdirSync(templates).filter((d) => existsSync(join(templates, d, "recipe.mjs"))).sort();
const die = (msg, code = 2) => { console.error(`[hf-motion] ${msg}`); process.exit(code); };

const argv = process.argv.slice(2);
const flags = new Set(argv.filter((a) => a.startsWith("--")));
const pos = argv.filter((a) => !a.startsWith("--") && !a.includes("="));
const kv = argv.filter((a) => !a.startsWith("--") && a.includes("="));
if (flags.has("--list")) { console.log(recipes().join("\n")); process.exit(0); }
if (pos.length !== 2) die(`usage: scaffold.mjs <recipe> <out-dir> [key=value ...] [--update] [--no-music]\nrecipes: ${recipes().join(", ")}`);
const [name, outArg] = pos;
if (!recipes().includes(name)) die(`unknown recipe '${name}'. Implemented: ${recipes().join(", ")}`);
const tpl = join(templates, name);
const out = resolve(outArg);
const update = flags.has("--update");
const recipe = await import(pathToFileURL(join(tpl, "recipe.mjs")).href);

// ---- CONFIG block: strict JSON between the markers
const BEGIN = "/* CONFIG:BEGIN */", END = "/* CONFIG:END */";
const readConfig = (html) => {
  const i = html.indexOf(BEGIN), j = html.indexOf(END);
  if (i < 0 || j < i) die("index.html has no CONFIG:BEGIN/END block");
  return JSON.parse(html.slice(i + BEGIN.length, j));
};
const writeConfig = (html, cfg) => {
  const i = html.indexOf(BEGIN), j = html.indexOf(END);
  const body = JSON.stringify(cfg, null, 2).split("\n").join("\n      ");
  return html.slice(0, i + BEGIN.length) + body + html.slice(j);
};

const srcHtml = update ? join(out, "index.html") : join(tpl, "index.html");
if (update && !existsSync(srcHtml)) die(`--update: ${srcHtml} does not exist`);
if (!update && existsSync(out) && readdirSync(out).length) die(`${out} is not empty (use --update to re-apply)`);
let html = readFileSync(srcHtml, "utf8");
const cfg = readConfig(html);

for (const pair of kv) {
  const eq = pair.indexOf("=");
  const key = pair.slice(0, eq), raw = pair.slice(eq + 1);
  if (!(key in cfg)) die(`unknown key '${key}'. Keys: ${Object.keys(cfg).join(", ")}`);
  const cur = cfg[key];
  if (Array.isArray(cur)) cfg[key] = raw.split("|").map((s) => s.trim()).filter(Boolean);
  else if (typeof cur === "number") {
    if (!/^-?\d+(\.\d+)?$/.test(raw.trim())) die(`${key} must be a number, got '${raw}'`);
    cfg[key] = Number(raw);
  } else cfg[key] = raw;
}
// userFiles: a CONFIG key naming local file(s), e.g. photos=a.jpg|b.jpg (list) or
// image=./x.png; each is copied to <out-dir>/assets/<basename> and CONFIG holds that path.
const fileCopies = [];
for (const key of recipe.userFiles ?? []) {
  const pair = kv.findLast((p) => p.slice(0, p.indexOf("=")) === key);
  if (!pair) continue;
  const list = Array.isArray(cfg[key]);
  const raws = list ? cfg[key] : [pair.slice(key.length + 1)];
  const dests = raws.map((raw) => {
    const src = resolve(raw);
    if (!existsSync(src) || !statSync(src).isFile()) die(`${key}: no such file ${src}`);
    const dest = `assets/${basename(src)}`;
    if (fileCopies.some(([, d]) => d === join(out, dest))) die(`${key}: two files named ${basename(src)}`);
    fileCopies.push([src, join(out, dest)]);
    return dest;
  });
  cfg[key] = list ? dests : dests[0];
}
const passed = new Set(kv.map((p) => p.slice(0, p.indexOf("="))));
recipe.derive?.(cfg, passed);
const errors = recipe.validate(cfg);
if (errors.length) die(`invalid parameters:\n  - ${errors.join("\n  - ")}`);

// ---- static timing attributes (the engine reads these before any script runs)
const { at, total } = recipe.timing(cfg);
html = writeConfig(html, cfg);
for (const [id, [start, dur]] of Object.entries(at)) {
  const rx = new RegExp(`<[a-zA-Z]+\\b[^>]*\\bid="${id}"[^>]*>`, "g");
  const hits = html.match(rx) || [];
  if (hits.length !== 1) die(`expected one element id="${id}", found ${hits.length}`);
  const tag = hits[0]
    .replace(/data-start="[^"]*"/, `data-start="${start}"`)
    .replace(/data-duration="[^"]*"/, `data-duration="${dur}"`);
  html = html.replace(hits[0], tag);
}

// ---- user assets (never bundled): every source must be readable before anything is written.
// --update re-copies only a key passed on this command line; the project already holds the rest.
const userCopies = Object.entries(recipe.userAssets || {})
  .filter(([key]) => !update || passed.has(key))
  .map(([key, dest]) => {
    const src = resolve(cfg[key]);
    try {
      if (!statSync(src).isFile()) throw new Error("not a file");
      accessSync(src, constants.R_OK);
    } catch {
      die(`${key}: cannot read '${src}'. Pass ${key}=<path to your image>; it is copied to ${dest} (nothing is bundled). Nothing was written.`);
    }
    return [src, dest];
  });

// ---- resolve the official plugin before writing anything
const missing = Object.keys(recipe.pluginAssets).filter((p) => !existsSync(join(out, p)));
let plugin;
if (missing.length) {
  try {
    plugin = execFileSync("bash", [join(here, "find-hf-plugin.sh")], { encoding: "utf8", stdio: ["ignore", "pipe", "inherit"] }).trim();
  } catch { die("official hyperframes plugin is required (see message above)", 3); }
}

// ---- write the project
if (!update) {
  mkdirSync(out, { recursive: true });
  cpSync(tpl, out, { recursive: true, filter: (p) => basename(p) !== "recipe.mjs" });
}
writeFileSync(join(out, "index.html"), html);
// recipes that generate project files from CONFIG (letter-flythrough's glyphs.js)
for (const [p, body] of Object.entries(recipe.files?.(cfg) ?? {})) writeFileSync(join(out, p), body);

if (missing.length) {
  for (const dest of missing) {
    const spec = recipe.pluginAssets[dest];
    let src = spec.path && join(plugin, spec.path);
    if (spec.glob) {
      const [pre, post] = spec.glob.split("/*/");
      const base = join(plugin, pre);
      const hit = existsSync(base) && readdirSync(base).sort().map((d) => join(base, d, post)).find(existsSync);
      src = hit || join(plugin, spec.glob);
    }
    if (!existsSync(src)) die(`hyperframes plugin at ${plugin} has no ${spec.path || spec.glob}`, 3);
    mkdirSync(dirname(join(out, dest)), { recursive: true });
    cpSync(src, join(out, dest));
  }
  const version = JSON.parse(readFileSync(join(plugin, "plugin.json"), "utf8")).version;
  const pkgName = basename(out).toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "") || "hf-motion-project";
  const pin = (cmd) => `npx --yes hyperframes@${version} ${cmd}`;
  if (!existsSync(join(out, "package.json"))) {
    writeFileSync(join(out, "package.json"), JSON.stringify({
      name: pkgName, private: true, type: "module",
      scripts: { dev: pin("preview"), check: pin("check"), render: pin("render"), publish: pin("publish") },
    }, null, 2) + "\n");
  }
  if (!existsSync(join(out, "meta.json"))) {
    writeFileSync(join(out, "meta.json"), JSON.stringify({ id: pkgName, name: pkgName }, null, 2) + "\n");
  }
}

for (const [src, dest] of fileCopies) {
  mkdirSync(dirname(dest), { recursive: true });
  cpSync(src, dest);
}
// sharedAssets: files several recipes use (the Geist font), kept once in templates/_shared
for (const dest of recipe.sharedAssets ?? []) {
  if (existsSync(join(out, dest))) continue;
  mkdirSync(dirname(join(out, dest)), { recursive: true });
  cpSync(join(templates, "_shared", dest), join(out, dest));
}

for (const [src, dest] of userCopies) {
  mkdirSync(dirname(join(out, dest)), { recursive: true });
  cpSync(src, join(out, dest));
}

// a recipe without musicArgs (pixel-dissolve) has no music bed and no bpm
if (recipe.musicArgs && !flags.has("--no-music")) {
  execFileSync("python3", recipe.musicArgs(cfg), { cwd: out, stdio: "inherit" });
}

const bpm = recipe.musicArgs ? cfg.bpm : null;
const size = recipe.canvas ? ` --width ${recipe.canvas.width} --height ${recipe.canvas.height}` : "";
console.log(`[OK] ${name} scaffolded at ${out} (${total}s${bpm == null ? ", no music" : ` @ ${bpm} BPM`})`);
console.log(`verify-render args: --duration ${total}${bpm == null ? "" : ` --bpm ${bpm}`}${size}`);
console.log(`Next (PLUGIN=$(bash ${join(here, "find-hf-plugin.sh")})):`);
for (const c of ["lint .", "check .", "snapshot . --at <times> --no-end --describe false", "render . -q high -o ./renders/video.mp4"]) {
  console.log(`  (cd ${out} && node "$PLUGIN/skills/hyperframes/scripts/plugin-cli.mjs" ${c})`);
}
