// Engine core: beat timing, persistent chrome (paper, chapter chip,
// progress rail, subtitles) and the page skeleton. Episodes import this and
// supply beats + visual sets; see videos/ep01-rag-vs-graphrag/build.mjs.
//
// Timing model: an episode is a list of narration BEATS. Every visual is
// keyed to beat ids (T(id) = start, E(id) = end, F(id, frac) = a point inside
// the beat), never to raw seconds. Silent cut: beat length comes from word
// count at reading pace. Voiced cut: pass measured audio durations instead and
// every animation follows without edits.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const W = 1920, H = 1080;
export const PX = W / 100; // px per cqw (for GSAP x/y, which are px)
export const PY = H / 100; // px per cqh

const r2 = (n) => Math.round(n * 100) / 100;

// voice = { durations: {id: seconds}, words: {id: [{s, e}]} } from engine/tts.py + engine/align.py.
// Voiced beat = its clip + `gap` + its hold. F() then lands on real word starts.
export function timeBeats(beats, { wps = 2.5, pad = 0.65, min = 2.2, lead = 0.5, voice = null, gap = 0.45 } = {}) {
  let t = lead;
  for (const b of beats) {
    b.words = b.text.split(/\s+/).filter(Boolean).length;
    let d;
    if (voice) {
      b.spoken = voice.durations[b.id];
      if (b.spoken == null) throw new Error(`no voice clip for ${b.id}`);
      b.wt = voice.words?.[b.id]?.length ? voice.words[b.id] : null;
      d = b.spoken + gap + (b.hold ?? 0);
    } else {
      d = Math.max(b.min ?? min, b.words / wps + pad + (b.hold ?? 0));
      b.spoken = d - pad;
      b.wt = null;
    }
    b.start = r2(t); b.dur = r2(d); b.end = r2(t + d);
    t += d;
  }
  const byId = Object.fromEntries(beats.map((b) => [b.id, b]));
  const get = (id) => { const b = byId[id]; if (!b) throw new Error(`unknown beat ${id}`); return b; };
  const T = (id) => get(id).start;
  const E = (id) => get(id).end;
  // a point inside the beat's spoken part: f=0.5 is halfway through the words.
  // Voiced: snaps to the start of the word at that position (whisper timings).
  const F = (id, f) => {
    const b = get(id);
    if (b.wt) {
      if (f >= 1) return r2(b.start + b.wt[b.wt.length - 1].e);
      const k = Math.min(b.wt.length - 1, Math.max(0, Math.round(f * b.wt.length)));
      return r2(b.start + b.wt[k].s);
    }
    return r2(b.start + f * Math.max(0.1, b.spoken));
  };
  // start of the k-th spoken word (0-based). Use when a visual must land ON a word.
  const Wd = (id, k) => {
    const b = get(id);
    if (b.wt) return r2(b.start + b.wt[Math.min(k, b.wt.length - 1)].s);
    return F(id, k / b.words);
  };
  return { total: r2(t + 0.6), T, E, F, Wd, get };
}

// ---------------------------------------------------------------- subtitles
// Split each beat at sentence ends (and long sentences at a comma). Silent: time
// the pieces by word share. Voiced: each piece starts on its first spoken word.
// maxWords (Shorts): break every sentence into chunks of at most that many words,
// preferring a break right after a comma.
export function subtitleChunks(beats, { maxWords = 0 } = {}) {
  const out = [];
  for (const b of beats) {
    // split after . ? ! only when the next word starts a sentence (keeps "0.1" whole)
    let parts = b.text.split(/(?<=[.?!]["”’]?)\s+(?=[A-Z“"])/);
    parts = parts.flatMap((s) => {
      const w = s.trim().split(/\s+/);
      if (w.length <= 15) return [s.trim()];
      const mid = s.indexOf(", ", Math.floor(s.length * 0.35));
      return mid > 0 ? [s.slice(0, mid + 1).trim(), s.slice(mid + 2).trim()] : [s.trim()];
    }).filter(Boolean);
    if (maxWords) parts = parts.flatMap((s) => {
      const w = s.split(/\s+/), out = [];
      let cur = [];
      w.forEach((x, i) => {
        cur.push(x);
        const left = w.length - i - 1;
        const atComma = /[,;:]$/.test(x) && cur.length >= 2;
        if (left > 1 && (cur.length >= maxWords || atComma)) { out.push(cur.join(" ")); cur = []; } // never orphan the last word
      });
      if (cur.length) out.push(cur.join(" "));
      return out;
    });
    const counts = parts.map((s) => s.split(/\s+/).length);
    const total = counts.reduce((a, n) => a + n, 0);
    const endAll = b.start + b.dur - 0.1;
    let starts;
    if (b.wt) {
      // word index in our text -> nearest whisper word (counts can differ: "72" vs "seventy two")
      let k = 0;
      starts = counts.map((n) => {
        const j = Math.min(b.wt.length - 1, Math.round((k / total) * b.wt.length));
        k += n;
        return k - n === 0 ? b.start : b.start + b.wt[j].s - 0.05;
      });
    } else {
      let t = b.start;
      starts = counts.map((n) => { const s0 = t; t += (b.dur - 0.12) * (n / total); return s0; });
    }
    parts.forEach((s, i) => {
      const e = i === parts.length - 1 ? endAll : starts[i + 1];
      out.push({ s: r2(starts[i]), d: r2(e - starts[i]), text: s });
    });
  }
  return out;
}

// ---------------------------------------------------------------- page
// w/h default to 16:9. vertical: Shorts chrome (no chapter chip or rail, big captions
// parked above the Shorts UI). Pass chapters = [] to drop the chip and rail.
export function page({ total, css, body, js, chapters = [], subs, showSubs = true, w = W, h = H, vertical = false }) {
  const px = w / 100, py = h / 100;
  const subHtml = showSubs
    ? subs.map((c, i) =>
        `<div class="sub clip" id="sub${i}" data-start="${c.s}" data-duration="${c.d}" data-track-index="900"><span>${esc(c.text)}</span></div>`
      ).join("\n")
    : "";
  const chapHtml = chapters.filter((c) => c.label).map((c, i) =>
    `<div class="chap clip" id="chap${i}" data-start="${c.s}" data-duration="${r2(c.e - c.s)}" data-track-index="800"><span class="num">${String(c.n).padStart(2, "0")}</span>${esc(c.label)}</div>`
  ).join("\n");
  const numbered = chapters.filter((c) => c.label);
  const railHtml = numbered.length ? `<div id="rail" class="clip" data-start="${numbered[0].s}" data-duration="${r2(numbered[numbered.length - 1].e - numbered[0].s)}" data-track-index="801">${
    numbered.map((c, i) => `<i><b id="rf${i}"></b></i>`).join("")}</div>` : "";
  const railJs = numbered.map((c, i) =>
    `tl.fromTo("#rf${i}", {scaleX:0}, {scaleX:1, duration:${r2(c.e - c.s)}, ease:"none"}, ${c.s});`
  ).join("\n");
  const chapJs = chapters.filter((c) => c.label).map((c, i) =>
    `tl.fromTo("#chap${i}", {opacity:0, y:-12}, {opacity:1, y:0, duration:0.45, ease:"power3.out"}, ${c.s});`
  ).join("\n");
  const subJs = showSubs
    ? subs.map((c, i) => `tl.fromTo("#sub${i}", {opacity:0}, {opacity:1, duration:0.16, ease:"none"}, ${c.s});`).join("\n")
    : "";

  return `<!doctype html>
<html lang="en" data-resolution="${vertical ? "portrait" : "landscape"}">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=${w}, height=${h}" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
@font-face { font-family:"Space Grotesk"; src:url("fonts/spacegrotesk-400.woff2") format("woff2"); font-weight:400; font-display:block; }
@font-face { font-family:"Space Grotesk"; src:url("fonts/spacegrotesk-500.woff2") format("woff2"); font-weight:500; font-display:block; }
@font-face { font-family:"Instrument Serif"; src:url("fonts/instrumentserif-italic.woff2") format("woff2"); font-style:italic; font-weight:400; font-display:block; }
@font-face { font-family:"JetBrains Mono"; src:url("fonts/jetbrainsmono-500.woff2") format("woff2"); font-weight:500; font-display:block; }
* { margin:0; padding:0; box-sizing:border-box; }
html, body { width:${w}px; height:${h}px; overflow:hidden; background:#f3ecd9; }
#root {
  position:relative; width:${w}px; height:${h}px; overflow:hidden; container-type:size;
  --bg:#f3ecd9; --bg-deep:#ece2c9; --surface:#faf6ec; --fg:#161513; --muted:#6a6258;
  --accent:#f0a87a; --accent-strong:#e07a45; --butter:#f0c860; --sage:#a9c79b; --lilac:#bdb2ea;
  --line-faint:rgba(22,21,19,0.07);
  background:var(--bg); color:var(--fg); font-family:"Space Grotesk", system-ui; font-weight:500;
}
.set { position:absolute; inset:0; }
.mono { font-family:"JetBrains Mono", monospace; font-weight:500; text-transform:uppercase; letter-spacing:0.14em; }
.serif { font-family:"Instrument Serif", serif; font-style:italic; font-weight:400; }
.pill { display:inline-block; background:var(--accent); border-radius:999px; padding:0 0.9em; }
.card { position:absolute; background:var(--surface); border:0.14cqw solid var(--fg); border-radius:1.1cqw; box-shadow:0 0.38cqw 0 var(--fg); }
.dark { background:var(--fg); color:var(--bg); }

#paper { position:absolute; left:-6cqw; top:-6cqh; width:112cqw; height:112cqh;
  background:
    linear-gradient(var(--line-faint) 1px, transparent 1px),
    linear-gradient(90deg, var(--line-faint) 1px, transparent 1px);
  background-size:4cqw 4cqw; }

/* chrome */
.chap { position:absolute; left:4cqw; top:4.2cqh; font-family:"JetBrains Mono"; font-weight:500; font-size:1.05cqw;
  text-transform:uppercase; letter-spacing:0.16em; color:var(--fg); display:flex; align-items:center; gap:0.8cqw; z-index:50; }
.chap .num { background:var(--fg); color:var(--bg); border-radius:0.4cqw; padding:0.25cqw 0.55cqw; }
#rail { position:absolute; right:4cqw; top:5.1cqh; display:flex; gap:0.5cqw; z-index:50; }
#rail i { display:block; width:2.4cqw; height:0.6cqh; background:rgba(22,21,19,0.2); border-radius:1cqw; overflow:hidden; }
#rail b { display:block; width:100%; height:100%; background:var(--accent-strong); transform-origin:0 50%; }
.sub { position:absolute; left:0; right:0; bottom:4.6cqh; text-align:center; z-index:60; pointer-events:none; }
.sub span { display:inline-block; max-width:62cqw; background:rgba(22,21,19,0.9); color:#f7f2e6; font-family:"Space Grotesk";
  font-weight:500; font-size:1.6cqw; line-height:1.32; padding:0.55cqw 1.3cqw; border-radius:0.7cqw; }
${vertical ? `#paper { background-size:7cqw 7cqw; }
.sub { bottom:auto; top:66cqh; }
.sub span { max-width:90cqw; font-size:5.2cqw; line-height:1.18; padding:1.2cqw 2.6cqw 1.5cqw; border-radius:1.6cqw; }` : ""}
${css}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="${total}" data-width="${w}" data-height="${h}">
<div id="paper" class="clip" data-start="0" data-duration="${total}" data-track-index="0"></div>
${body}
${chapHtml}
${railHtml}
${subHtml}
</div>
<script>
window.__timelines = window.__timelines || {};
var tl = gsap.timeline({ paused:true });
var PX = ${px}, PY = ${py};
// motion vocabulary (CLAUDE.md format C standard): panel lands, contents stagger, exits rise
function land(s, t, o) { o = o || {}; tl.fromTo(s, {opacity:0, scale:o.from == null ? 0.9 : o.from, y:o.y || 0}, {opacity:1, scale:1, y:0, duration:o.d || 0.42, ease:o.ease || "back.out(1.7)", stagger:o.st || 0}, t); }
function rise(s, t, o) { o = o || {}; tl.fromTo(s, {opacity:0, y:o.y == null ? 22 : o.y}, {opacity:1, y:0, duration:o.d || 0.5, ease:"power3.out", stagger:o.st == null ? 0.075 : o.st}, t); }
function fade(s, t, o) { o = o || {}; tl.fromTo(s, {opacity:0}, {opacity:1, duration:o.d || 0.4, ease:"power1.out", stagger:o.st || 0}, t); }
function exit(s, t, o) { o = o || {}; tl.to(s, {opacity:0, y:o.y == null ? -18 : o.y, duration:o.d || 0.32, ease:"power2.inOut"}, t); }
function to(s, v, t) { tl.to(s, v, t); }
function draw(s, t, o) { o = o || {}; tl.fromTo(s, {strokeDashoffset:function(i, el){ return el.getAttribute("data-len"); }}, {strokeDashoffset:0, duration:o.d || 0.5, ease:o.ease || "power2.inOut", stagger:o.st || 0}, t); }
function type(sel, text, t, d) { var el = document.querySelector(sel); var o = {n:0}; tl.to(o, {n:text.length, duration:d, ease:"none", onUpdate:function(){ el.textContent = text.slice(0, Math.round(o.n)); }}, t); }
function count(sel, to_, t, d, fmt) { var el = document.querySelector(sel); var o = {n:0}; tl.to(o, {n:to_, duration:d, ease:"power2.out", onUpdate:function(){ el.textContent = fmt ? fmt(o.n) : Math.round(o.n).toLocaleString("en-US"); }}, t); }
tl.fromTo("#paper", {x:0, y:0}, {x:-3 * PX, y:-2 * PY, duration:${total}, ease:"none"}, 0);
${railJs}
${chapJs}
${subJs}
${js}
window.__timelines["main"] = tl;
</script>
</body>
</html>
`;
}

export function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Deterministic PRNG for build-time layout (the page itself stays deterministic
// because positions are baked into the HTML).
export function rng(seed) {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}

export function write(file, text) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, text, "utf8");
}

// A fresh edit/ folder needs HyperFrames' project files and the fonts page() loads.
export function ensureEdit(editDir) {
  fs.mkdirSync(editDir, { recursive: true });
  const put = (f, o) => { const p = path.join(editDir, f); if (!fs.existsSync(p)) fs.writeFileSync(p, JSON.stringify(o, null, 2)); };
  put("hyperframes.json", { $schema: "https://hyperframes.heygen.com/schema/hyperframes.json",
    registry: "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
    paths: { blocks: "compositions", components: "compositions/components", assets: "assets" }, media: { autoProxy: true } });
  put("meta.json", { id: "edit", name: path.basename(path.dirname(path.resolve(editDir))), createdAt: "2026-01-01T00:00:00.000Z" });
  const src = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "fonts"), dst = path.join(editDir, "fonts");
  fs.mkdirSync(dst, { recursive: true });
  for (const f of fs.readdirSync(src)) if (f.endsWith(".woff2") && !fs.existsSync(path.join(dst, f))) fs.copyFileSync(path.join(src, f), path.join(dst, f));
}
