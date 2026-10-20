// TEMPLATE EPISODE: a 40-second video about how this engine works. Copy it, then replace the
// beats and scenes with your topic (`node engine/new.mjs <slug>` does the copy).
//   node build.mjs                  -> silent cut (beats timed at reading pace) + vo/lines.json + script.md
//   node build.mjs --voice af_heart -> every beat timed to its voice clip in vo/af_heart/
// Facts + sources go in brief.md. This demo makes no factual claims.

import fs from "node:fs";
import path from "node:path";
import { timeBeats, subtitleChunks, page, write, ensureEdit } from "../../engine/core.mjs";

const HERE = path.dirname(new URL(import.meta.url).pathname).replace(/^\/([A-Za-z]:)/, "$1");
const showSubs = !process.argv.includes("--no-subs");
const VOICE = process.argv.includes("--voice") ? process.argv[process.argv.indexOf("--voice") + 1] : null;
const r2 = (n) => Math.round(n * 100) / 100;
const NAME = "explainer-video-opus-5.5"; // filled in by the export

// ============================================================ BEATS
// One beat = one line of narration + what is on screen while it plays (v). ch = chapter index.
// hold = extra seconds after the line. nosub = no subtitle (for lines that are already on screen).
const beats = [
  { id: "b01", ch: 0, text: "Every animation in this video waits for a word.", hold: 0.3, v: "Headline; the last word lights up in a peach pill as it is spoken" },
  { id: "b02", ch: 0, text: "Nothing here is timed in seconds. It's timed in beats.", hold: 0.4, v: "SECONDS gets struck out, a strip of beat blocks slides in" },
  { id: "b03", ch: 1, text: "A beat is one line of narration, plus what's on screen while you hear it.", v: "One beat card: id, narration, on-screen note" },
  { id: "b04", ch: 1, text: "You write all the beats first. The script is the timeline.", hold: 0.3, v: "Beat blocks lay out left to right, a playhead runs across" },
  { id: "b05", ch: 2, text: "Then a voice reads each line, and every clip gets measured.", v: "Waveforms fill the blocks, each block gets its duration" },
  { id: "b06", ch: 2, text: "The scenes stretch to fit. Swap the voice, and nothing breaks.", hold: 0.4, v: "Blocks resize to a second voice, the labels follow" },
  { id: "b07", ch: 3, text: "Write the beats. Build the scenes. Let the voice set the pace.", hold: 0.5, v: "Three cards land, one per sentence" },
  { id: "b08", ch: 3, text: "Your turn. Pick a topic.", hold: 2, nosub: true, v: "End card" },
];
const CHAPTERS = ["", "Beats", "Voice", "Recap"]; // "" = intro: no chapter chip

// say(): what the TTS voice reads, when spelling differs from the screen ("GraphRAG" -> "Graph rag")
const say = (t) => t;
write(path.join(HERE, "vo", "lines.json"), JSON.stringify(beats.map((b) => ({ id: b.id, say: say(b.text), text: b.text })), null, 1));
let voice = null;
if (VOICE) {
  const dir = path.join(HERE, "vo", VOICE);
  voice = { durations: JSON.parse(fs.readFileSync(path.join(dir, "durations.json"), "utf8")),
            words: JSON.parse(fs.readFileSync(path.join(dir, "words.json"), "utf8")) };
}
const { total, T, E, F, Wd, get } = timeBeats(beats, { voice, gap: 0.4 });
const chapters = CHAPTERS.map((label, n) => {
  const bs = beats.filter((b) => b.ch === n);
  return { n, label, s: bs[0].start, e: bs[bs.length - 1].end };
});

// ============================================================ BUILD HELPERS
let CSS = "", BODY = "", JS = "", track = 10;
const css = (s) => { CSS += s + "\n"; };
const js = (s) => { JS += s + "\n"; };
// a scene = one full-frame layer from the start of beat `from` to the end of beat `to`,
// with a slow push-in so nothing ever sits dead still, and a short fade out
function scene(id, from, to, html) {
  const s = T(from), e = E(to), d = r2(e - s);
  BODY += `<div class="set clip" id="${id}" data-start="${s}" data-duration="${d}" data-track-index="${track++}"><div class="stage" id="${id}-st">${html}</div></div>\n`;
  js(`tl.fromTo("#${id}-st", {scale:1}, {scale:1.025, duration:${d}, ease:"none"}, ${s});`);
  js(`tl.to("#${id}", {opacity:0, duration:0.3, ease:"power1.in"}, ${r2(e - 0.3)});`);
}

css(`
.stage { position:absolute; inset:0; transform-origin:50% 50%; }
.k { font-size:1.1cqw; color:var(--muted); }
.chip { display:inline-block; font-family:"JetBrains Mono"; font-weight:500; text-transform:uppercase; letter-spacing:0.1em; font-size:1.05cqw;
  padding:0.4cqw 0.9cqw; border-radius:999px; border:0.12cqw solid var(--fg); background:var(--surface); white-space:nowrap; }
`);

// ============================================================ 0 · HOOK
css(`
#h1 { position:absolute; left:0; right:0; top:36cqh; text-align:center; font-size:4.6cqw; letter-spacing:-0.035em; }
#h1-w { padding:0 0.32em 0.06em; background:rgba(240,168,122,0); }
#h2 { position:absolute; left:0; right:0; top:22cqh; text-align:center; font-size:3.6cqw; letter-spacing:-0.03em; }
#h2-sec { position:relative; display:inline-block; color:var(--muted); }
#h2-x { position:absolute; left:-4%; top:52%; width:108%; height:0.5cqh; background:var(--accent-strong); transform-origin:0 50%; }
#h2-row { position:absolute; left:14cqw; top:52cqh; width:72cqw; height:12cqh; }
.hb { position:absolute; top:0; height:12cqh; display:flex; align-items:center; justify-content:center; font-family:"JetBrains Mono"; font-weight:500;
  font-size:1.2cqw; letter-spacing:0.1em; background:var(--surface); border:0.14cqw solid var(--fg); border-radius:0.9cqw; box-shadow:0 0.38cqw 0 var(--fg); }
`);
{
  // strip widths = the real beat lengths, so a voiced build draws its own timeline
  const ids = ["b01", "b02", "b03", "b04", "b05", "b06"], sum = ids.reduce((a, id) => a + get(id).dur, 0), gap = 1;
  let x = 0;
  const blocks = ids.map((id) => { const w = r2((72 - gap * 5) * get(id).dur / sum); const h = `<div class="hb" style="left:${r2(x)}cqw;width:${w}cqw">${id}</div>`; x += w + gap; return h; }).join("");
  scene("s-hook", "b01", "b02", `
<div id="h1">Every animation waits for a <span class="serif pill" id="h1-w">word</span>.</div>
<div id="h2">Not <span id="h2-sec">seconds<span id="h2-x"></span></span>. <span class="serif pill">beats</span>.</div>
<div id="h2-row">${blocks}</div>`);
  js(`
rise("#h1", ${r2(T("b01") + 0.1)});
tl.to("#h1-w", {backgroundColor:"#f0a87a", duration:0.25, ease:"power1.out"}, ${Wd("b01", 8)});
exit("#h1", ${T("b02")});
rise("#h2", ${r2(T("b02") + 0.2)});
tl.fromTo("#h2-x", {scaleX:0}, {scaleX:1, duration:0.35, ease:"power2.out"}, ${Wd("b02", 5)});
land("#h2-row .hb", ${Wd("b02", 9)}, {st:0.07, y:20});`);
}

// ============================================================ 1 · BEATS
css(`
#bc { left:24cqw; top:20cqh; width:52cqw; padding:2.2cqw 2.4cqw; display:flex; flex-direction:column; gap:1.6cqw; }
#bc > * { flex-shrink:0; }
.bc-top { display:flex; align-items:center; gap:1cqw; }
.bc-top .chip { background:var(--butter); }
.bc-row { display:flex; flex-direction:column; gap:0.5cqw; padding-top:1.2cqw; border-top:0.12cqw solid rgba(22,21,19,0.14); }
.bc-row p { font-size:2.1cqw; line-height:1.35; }
.bc-row.see p { color:var(--accent-strong); }
`);
scene("s-beat", "b03", "b03", `
<div class="card" id="bc">
  <div class="bc-top"><span class="chip">b03</span><span class="mono k">one beat</span></div>
  <div class="bc-row say" id="bc-say"><span class="mono k">narration</span><p>A beat is one line of narration, plus what's on screen while you hear it.</p></div>
  <div class="bc-row see" id="bc-see"><span class="mono k">on screen</span><p>This card.</p></div>
</div>`);
js(`
land("#bc", ${r2(T("b03") + 0.1)});
rise("#bc-say", ${r2(T("b03") + 0.3)});
rise("#bc-see", ${Wd("b03", 8)});`);

// ============================================================ 1-2 · TIMELINE (b04-b06 share one strip)
css(`
#tl-h { position:absolute; left:14cqw; top:20cqh; font-size:3.2cqw; letter-spacing:-0.03em; }
#tl-voice { position:absolute; right:14cqw; top:21.5cqh; }
#tl-voice .chip { background:var(--lilac); }
#tl-v2 { position:absolute; right:0; top:0; background:var(--sage) !important; }
.tb { position:absolute; top:40cqh; height:16cqh; background:var(--surface); border:0.14cqw solid var(--fg); border-radius:0.9cqw;
  box-shadow:0 0.38cqw 0 var(--fg); transform-origin:0 50%; overflow:hidden; }
.tb svg { position:absolute; inset:0; width:100%; height:100%; }
.tb rect { fill:var(--accent); }
.tl { position:absolute; top:58.5cqh; font-family:"JetBrains Mono"; font-weight:500; font-size:1.05cqw; letter-spacing:0.1em; text-align:center; }
.td { position:absolute; top:34cqh; font-family:"JetBrains Mono"; font-weight:500; font-size:1.2cqw; text-align:center; color:var(--accent-strong); }
#ph { position:absolute; left:14cqw; top:37cqh; width:0.3cqw; height:23cqh; background:var(--fg); border-radius:1cqw; }
`);
{
  const ids = ["b01", "b02", "b03", "b04", "b05", "b06"];
  const A = ids.map((id) => get(id).dur);                       // this build's beat lengths
  const B = A.map((d, i) => r2(d * [1.25, 0.8, 1.15, 0.85, 1.3, 0.95][i])); // an illustrative second voice
  const lay = (ds) => { const sum = ds.reduce((a, b) => a + b, 0), gap = 0.8; let x = 14; return ds.map((d) => { const w = r2((72 - gap * 5) * d / sum), o = { x, w }; x += w + gap; return o; }); };
  const LA = lay(A), LB = lay(B);
  const wave = (k) => `<svg viewBox="0 0 100 40" preserveAspectRatio="none">${Array.from({ length: 14 }, (_, j) => {
    const h = 6 + ((j * 37 + k * 11) % 23); return `<rect x="${j * 7 + 2}" y="${20 - h / 2}" width="4" height="${h}" rx="1"/>`; }).join("")}</svg>`;
  scene("s-tl", "b04", "b06", `
<div id="tl-h">The script is the <span class="serif pill">timeline</span></div>
<div id="tl-voice"><span class="chip" id="tl-v1">voice A</span><span class="chip" id="tl-v2">voice B</span></div>
${ids.map((id, i) => `<div class="tb" id="tb${i}" style="left:${LA[i].x}cqw;width:${LA[i].w}cqw"><div class="wv" id="wv${i}">${wave(i)}</div></div>
<div class="tl" id="tl${i}" style="left:${LA[i].x}cqw;width:${LA[i].w}cqw">${id}</div>
<div class="td" id="tdA${i}" style="left:${LA[i].x}cqw;width:${LA[i].w}cqw">${A[i].toFixed(1)}s</div>
<div class="td" id="tdB${i}" style="left:${LB[i].x}cqw;width:${LB[i].w}cqw">${B[i].toFixed(1)}s</div>`).join("\n")}
<div id="ph"></div>`);
  js(`
rise("#tl-h", ${r2(T("b04") + 0.1)});
land(".tb", ${r2(T("b04") + 0.35)}, {st:0.08, y:18});
fade(".tl", ${r2(T("b04") + 0.6)}, {st:0.06});
tl.set(".wv, .td, #ph, #tl-voice", {opacity:0}, ${T("b04")});
tl.set("#ph", {opacity:1}, ${Wd("b04", 6)});
tl.fromTo("#ph", {x:0}, {x:72 * PX, duration:${r2(E("b04") - Wd("b04", 6) - 0.2)}, ease:"none"}, ${Wd("b04", 6)});
tl.to("#ph", {opacity:0, duration:0.2}, ${r2(E("b04") - 0.2)});
fade("#tl-voice", ${T("b05")});
fade(".wv", ${Wd("b05", 2)}, {st:0.12, d:0.3});
fade("[id^=tdA]", ${Wd("b05", 8)}, {st:0.08, d:0.3});
tl.to("[id^=tdA]", {opacity:0, duration:0.2}, ${r2(Wd("b06", 2) - 0.2)});
tl.to("#tl-v1", {opacity:0, duration:0.15}, ${Wd("b06", 5)});`);
  // stretch: each block moves (x) and resizes (scaleX from its left edge) to voice B's layout
  ids.forEach((_, i) => js(`
tl.to("#tb${i}", {x:${r2(LB[i].x - LA[i].x)} * PX, scaleX:${r2(LB[i].w / LA[i].w)}, duration:0.7, ease:"power2.inOut"}, ${Wd("b06", 2)});
tl.to("#tl${i}", {x:${r2(LB[i].x - LA[i].x + (LB[i].w - LA[i].w) / 2)} * PX, duration:0.7, ease:"power2.inOut"}, ${Wd("b06", 2)});`));
  js(`fade("[id^=tdB]", ${r2(Wd("b06", 2) + 0.75)}, {st:0.06, d:0.3});`);
  js(`tl.fromTo("#tl-v2", {opacity:0}, {opacity:1, duration:0.2}, ${r2(Wd("b06", 5) + 0.1)});`);
}

// ============================================================ 3 · RECAP + END
css(`
.rc { top:30cqh; width:24cqw; height:21cqh; padding:2cqw 2.2cqw; display:flex; flex-direction:column; gap:1.2cqw; }
.rc .n { font-family:"JetBrains Mono"; font-weight:500; font-size:1.2cqw; width:2.6cqw; height:2.6cqw; border-radius:50%; background:var(--fg); color:var(--bg);
  display:flex; align-items:center; justify-content:center; }
.rc p { font-size:2.4cqw; line-height:1.2; letter-spacing:-0.02em; }
#end { position:absolute; left:0; right:0; top:30cqh; text-align:center; display:flex; flex-direction:column; align-items:center; gap:2.4cqw; }
#end .big { font-size:8cqw; }
#end .chip { font-size:1.4cqw; background:var(--butter); }
#end .mark { font-size:1.6cqw; color:var(--muted); }
`);
scene("s-recap", "b07", "b07", ["Write the beats", "Build the scenes", "Let the voice set the pace"].map((t, i) =>
  `<div class="card rc" id="rc${i}" style="left:${12 + i * 26}cqw"><span class="n">${i + 1}</span><p>${t}</p></div>`).join(""));
js(`
land("#rc0", ${Wd("b07", 0)});
land("#rc1", ${Wd("b07", 3)});
land("#rc2", ${Wd("b07", 6)});`);
scene("s-end", "b08", "b08", `
<div id="end"><div class="big serif">Your turn.</div><span class="chip">node engine/new.mjs your-topic</span><span class="mark mono">made with ${NAME}</span></div>`);
js(`rise("#end > *", ${r2(T("b08") + 0.1)}, {st:0.15});`);

// ============================================================ WRITE
const subs = subtitleChunks(beats.filter((b) => !b.nosub));
const edit = path.join(HERE, "edit");
ensureEdit(edit);
write(path.join(edit, "index.html"), page({ total, css: CSS, body: BODY, js: JS, chapters, subs, showSubs }));
const fmt = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
write(path.join(HERE, "script.md"), `# ${path.basename(HERE)} · scene table

Generated by \`build.mjs\` from the beat list. Edit the beats there, not here.
Runtime **${fmt(total)}** (${total}s), ${beats.length} beats, ${beats.reduce((a, b) => a + b.words, 0)} words of narration.

| Time | Chapter | Narration | On screen |
|---|---|---|---|
${beats.map((b) => `| ${fmt(b.start)} | ${CHAPTERS[b.ch] || "Intro"} | ${b.text} | ${b.v} |`).join("\n")}
`);
write(path.join(HERE, "beats.json"), JSON.stringify(beats.map(({ id, ch, start, end, dur, words }) => ({ id, ch, start, end, dur, words })), null, 1));
write(path.join(HERE, "total.txt"), String(total));
const srtT = (t) => { const ms = Math.round(t * 1000), h = Math.floor(ms / 3600000), m = Math.floor(ms / 60000) % 60, s2 = Math.floor(ms / 1000) % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s2).padStart(2, "0")},${String(ms % 1000).padStart(3, "0")}`; };
write(path.join(HERE, "captions.srt"), subs.map((c, i) => `${i + 1}\n${srtT(c.s)} --> ${srtT(c.s + c.d)}\n${c.text}\n`).join("\n"));
write(path.join(HERE, "chapters.txt"), chapters.map((c, i) => `${i === 0 ? "0:00" : fmt(c.s)} ${c.label || "Intro"}`).join("\n"));
console.log(`built: ${beats.length} beats, ${subs.length} subtitle chunks, ${fmt(total)} (${total}s)`);
