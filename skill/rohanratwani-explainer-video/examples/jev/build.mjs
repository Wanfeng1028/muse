// ep02: Jev, the decision model, and how to use it in RAG. 16:9 long-form.
//   node build.mjs                  -> silent cut + vo/lines.json + script.md (scene table)
//   node build.mjs --voice af_heart -> every beat timed to its Kokoro clip in vo/af_heart/
// Facts + sources: brief.md. Ticket text, paragraphs and every probability on screen are
// illustrative output shapes (labelled as such in the brief).

import fs from "node:fs";
import path from "node:path";
import { timeBeats, subtitleChunks, page, esc, write, PX, PY, ensureEdit } from "../../engine/core.mjs";

const HERE = path.dirname(new URL(import.meta.url).pathname).replace(/^\/([A-Za-z]:)/, "$1");
const showSubs = !process.argv.includes("--no-subs");
const VOICE = process.argv.includes("--voice") ? process.argv[process.argv.indexOf("--voice") + 1] : null;
const r2 = (n) => Math.round(n * 100) / 100;

// ============================================================ BEATS
const beats = [
  { id: "b01", ch: 0, text: "Your app asks an AI a simple question. Is this support ticket urgent?", v: "Ticket card + question bubble" },
  { id: "b02", ch: 0, text: "And a big language model writes you a whole paragraph, just to say yes.", v: "LLM card types a long paragraph, token counter climbs" },
  { id: "b03", ch: 0, text: "Your code throws the paragraph away. It only needed one word.", hold: 0.4, v: "Paragraph fades, YES lights up, claim: one word" },
  { id: "b04", ch: 0, text: "A new kind of model skips the writing. It's called Jev.", v: "Jev wordmark + typed answer card: urgent yes 0.94, 0 words written" },
  { id: "b05", ch: 0, text: "In its first day, 13 percent of paying teams on Vercel's AI Gateway were already using it.", hold: 0.4, v: "Stat 13% counts up" },
  { id: "b06", ch: 0, text: "Here's what it is, how it works, and how to use it in RAG.", hold: 0.8, v: "Title card" },

  { id: "b07", ch: 1, text: "Jev comes from a startup called TypeSafe AI, founded by a former OpenAI researcher. It launched on September 15th.", v: "Company card: TypeSafe AI, founder ex-OpenAI, 15 Sep 2026" },
  { id: "b08", ch: 1, text: "A normal language model generates. It writes text, one word at a time.", v: "Left panel: LANGUAGE MODEL generates, words appear one by one" },
  { id: "b09", ch: 1, text: "Jev is a decision model. It never writes a sentence. It only picks.", hold: 0.3, v: "Right panel: DECISION MODEL picks, one option gets ticked" },
  { id: "b10", ch: 1, text: "TypeSafe calls it a System One model. Think fast, gut feel decisions, the kind you make without stopping to think.", v: "System One chip under the right panel" },
  { id: "b11", ch: 1, text: "You give it some text, plus a question and the answers you allow. It hands back a typed answer your code can use right away.", hold: 0.6, v: "Flow: text + question/answers, Jev, typed answer" },

  { id: "b12", ch: 2, text: "It understands three kinds of questions.", v: "Three cards land: choice, score, noul" },
  { id: "b13", ch: 2, text: "One. Choice. Pick one option from a list. Which team should get this ticket? Billing, tech, or sales?", hold: 0.3, v: "Card 1: probability bars, Billing wins" },
  { id: "b14", ch: 2, text: "Two. Score. Rate something on a scale you define. How upset is this customer, from calm to furious?", hold: 0.3, v: "Card 2: 4-step ladder, marker lands" },
  { id: "b15", ch: 2, text: "Three. A yes or no statement, answered with a probability. This customer wants a refund. 71 percent true.", hold: 0.3, v: "Card 3: statement + 71% ring" },
  { id: "b16", ch: 2, text: "And every answer comes with a confidence score. So your code knows when to trust it, and when to ask a human.", hold: 0.6, v: "Confidence meter with ask-a-human threshold" },

  { id: "b17", ch: 3, text: "Because it never writes, it's fast. About ten complete decision loops, every second.", v: "10 decisions/sec, decision chips flash on" },
  { id: "b18", ch: 3, text: "And it's cheap. Reading costs about four cents per million tokens. The answers are free.", v: "Bar: Jev $0.042 per million input tokens, output free" },
  { id: "b19", ch: 3, text: "For comparison, OpenAI's new GPT-6.1 Sol charges two dollars per million tokens, just to read.", hold: 0.4, v: "Long bar: GPT-6.1 Sol $2.00" },
  { id: "b20", ch: 3, text: "TypeSafe's own example: sorting a million support tickets would cost about 19 dollars.", hold: 0.6, v: "Receipt: 1,000,000 tickets = $19" },

  { id: "b21", ch: 4, text: "Now, RAG. If you saw our last video, RAG finds the chunks closest to your question, and hands them to a model to write the answer.", v: "Pipeline: question, search, chunks, model, answer" },
  { id: "b22", ch: 4, text: "That pipeline is full of small decisions. Jev fits into three of them.", hold: 0.3, v: "Three Jev slots drop into the pipeline" },
  { id: "b23", ch: 4, text: "One. Routing. Before you search, decide what kind of question it is. Small talk, a simple fact, or a big picture question.", v: "Three questions route into three lanes" },
  { id: "b24", ch: 4, text: "You could use that to pick plain RAG or GraphRAG for each question, without paying a big model to decide.", hold: 0.4, v: "Lanes resolve to plain RAG / GraphRAG" },
  { id: "b25", ch: 4, text: "Two. Filtering. Search hands back a pile of chunks, and some of them are junk. Jev gives each one a score, and only the useful ones reach the model.", v: "8 chunks get scores, low ones drop out" },
  { id: "b26", ch: 4, text: "One builder scores sixty chunks per question this way. That's about thirty thousand tokens, or a tenth of a cent.", hold: 0.4, v: "Stat: 60 chunks, 30,000 tokens, $0.001" },
  { id: "b27", ch: 4, text: "Three. Checking. After the answer is written, ask Jev whether each source really backs it up. Full support, partial, not relevant, or contradicts.", v: "Answer + 4 sources, each gets a support label" },
  { id: "b28", ch: 4, text: "The writing still belongs to a language model. Jev makes every decision around it cheaper and faster.", hold: 0.6, v: "Pipeline labels: model writes, Jev decides" },

  { id: "b29", ch: 5, text: "But it's not magic. It can't write, explain its reasoning, do exact math, or read images.", v: "Four can't chips" },
  { id: "b30", ch: 5, text: "And it can be fooled. Security firm Check Point hid fake facts inside documents, and 59 percent of their attacks worked.", hold: 0.5, v: "Stat 59%, Check Point, 24 Sep" },
  { id: "b31", ch: 5, text: "TypeSafe hasn't published its weights or a paper, so you can't run Jev yourself.", v: "Strip: no weights, no paper, API only" },
  { id: "b32", ch: 5, text: "But copies are already here. Amazon just open sourced Strands Decider, small enough to run on your own machine. And OpenAI announced its own Decisions API.", hold: 0.6, v: "Two cards: Amazon Strands Decider, OpenAI Decisions API" },

  { id: "b33", ch: 6, text: "Quick recap. Language models write. Decision models pick.", v: "Recap cards: write / pick" },
  { id: "b34", ch: 6, text: "Use Jev for the hundreds of small choices inside your app, and keep the big model for the writing.", hold: 0.4, v: "Line under the cards" },
  { id: "b35", ch: 6, text: "Stop paying for an essay when all you need is a yes.", hold: 1.2, v: "Last line, YES in a peach pill" },
  { id: "b36", ch: 6, text: "Subscribe for more AI, explained simply.", hold: 2.5, v: "End card + handle" },
];
const CHAPTERS = ["", "What Jev is", "Three questions", "Why it's cheap", "Jev in RAG", "The catch", "Recap"];

const say = (t) => t
  .replace(/GraphRAG/g, "Graph rag").replace(/\bRAG\b/g, "rag").replace(/GPT-6\.1/g, "GPT 6.1")
  .replace(/September 15th/g, "September fifteenth");
write(path.join(HERE, "vo", "lines.json"), JSON.stringify(beats.map((b) => ({ id: b.id, say: say(b.text), text: b.text })), null, 1));
let voice = null;
if (VOICE) {
  const dir = path.join(HERE, "vo", VOICE);
  voice = { durations: JSON.parse(fs.readFileSync(path.join(dir, "durations.json"), "utf8")),
            words: JSON.parse(fs.readFileSync(path.join(dir, "words.json"), "utf8")) };
}
const { total, T, E, F, Wd } = timeBeats(beats, { voice, gap: 0.4 });
const chapters = CHAPTERS.map((label, n) => {
  const bs = beats.filter((b) => b.ch === n);
  return { n, label, s: bs[0].start, e: bs[bs.length - 1].end };
});

// ============================================================ BUILD HELPERS
let CSS = "", BODY = "", JS = "", track = 10;
const css = (s) => { CSS += s + "\n"; };
const js = (s) => { JS += s + "\n"; };
function scene(id, from, to, html, { exitAt = null } = {}) {
  const s = T(from), e = exitAt ?? E(to), d = r2(e - s);
  BODY += `<div class="set clip" id="${id}" data-start="${s}" data-duration="${d}" data-track-index="${track++}"><div class="stage" id="${id}-st">${html}</div></div>\n`;
  js(`tl.fromTo("#${id}-st", {scale:1}, {scale:1.025, duration:${d}, ease:"none"}, ${s});`);
  js(`tl.to("#${id}", {opacity:0, duration:0.3, ease:"power1.in"}, ${r2(e - 0.3)});`);
}
function sline(x1, y1, x2, y2, id, cls = "") {
  const len = r2(Math.hypot(x2 - x1, y2 - y1));
  return `<line id="${id}" class="${cls}" x1="${r2(x1)}" y1="${r2(y1)}" x2="${r2(x2)}" y2="${r2(y2)}" stroke-dasharray="${len}" stroke-dashoffset="${len}" data-len="${len}"/>`;
}
const svg = (id, inner) => `<svg id="${id}" style="position:absolute;inset:0" viewBox="0 0 1920 1080" width="1920" height="1080">${inner}</svg>`;
const P = (x, y) => [x * PX, y * PY];
const x = () => `<span class="xm"></span>`;

css(`
.stage { position:absolute; inset:0; transform-origin:50% 50%; }
svg line { stroke:var(--fg); stroke-width:3; }
svg line.hot { stroke:var(--accent-strong); stroke-width:5; }
.k { font-size:1.1cqw; color:var(--muted); }
.hd { position:absolute; left:0; right:0; top:11cqh; text-align:center; font-size:3.4cqw; letter-spacing:-0.03em; }
.hd .pill { padding:0 0.35em 0.05em; }
.chip { display:inline-block; font-family:"JetBrains Mono"; font-weight:500; text-transform:uppercase; letter-spacing:0.1em; font-size:1.05cqw;
  padding:0.4cqw 0.9cqw; border-radius:999px; border:0.12cqw solid var(--fg); background:var(--surface); white-space:nowrap; }
.stamp { position:absolute; font-family:"JetBrains Mono"; font-weight:500; text-transform:uppercase; letter-spacing:0.14em;
  border:0.16cqw solid currentColor; border-radius:0.5cqw; padding:0.35cqw 0.8cqw; }
.xm { display:inline-block; position:relative; width:1.3cqw; height:1.3cqw; flex-shrink:0; }
.xm::before, .xm::after { content:""; position:absolute; left:45%; top:-10%; width:0.22cqw; height:120%; background:var(--accent-strong); border-radius:1px; }
.xm::before { transform:rotate(45deg); } .xm::after { transform:rotate(-45deg); }
.ok { display:inline-block; width:1.5cqw; height:1.5cqw; border-radius:50%; background:var(--sage); border:0.14cqw solid var(--fg); position:relative; flex-shrink:0; }
.ok::after { content:""; position:absolute; left:0.36cqw; top:0.34cqw; width:0.6cqw; height:0.3cqw; border-left:0.16cqw solid var(--fg); border-bottom:0.16cqw solid var(--fg); transform:rotate(-45deg); }
.big { font-family:"Instrument Serif", serif; font-style:italic; font-weight:400; line-height:0.9; letter-spacing:-0.02em; }
`);

// ============================================================ 0 · HOOK
css(`
#tk { left:31cqw; top:18cqh; width:38cqw; padding:1.9cqw 2.1cqw; display:flex; flex-direction:column; gap:0.8cqw; }
#tk .mono { font-size:1.05cqw; color:var(--muted); }
#tk .b { font-size:2.1cqw; line-height:1.38; }
#tk-q { position:absolute; left:39cqw; top:52cqh; background:var(--fg); color:#f7f2e6; font-size:2.6cqw; padding:1.1cqw 1.6cqw; border-radius:1.2cqw; border-bottom-left-radius:0.3cqw; }
#llm { left:44cqw; top:15cqh; width:50cqw; padding:1.8cqw 2.1cqw; display:flex; flex-direction:column; gap:1.2cqw; }
#llm > * { flex-shrink:0; }
.llm-h { display:flex; align-items:center; gap:0.8cqw; font-size:1.6cqw; padding-bottom:1cqw; border-bottom:0.12cqw solid rgba(22,21,19,0.15); }
.llm-h .chip { margin-left:auto; background:var(--butter); }
#llm-p { font-size:2.05cqw; line-height:1.5; min-height:41cqh; }
#llm-yes { display:inline-block; opacity:0; padding:0 0.3em; border-radius:0.4em; }
#hk-claim { position:absolute; left:6cqw; top:70cqh; font-size:3.6cqw; letter-spacing:-0.03em; }
#hk-claim .pill { padding:0 0.35em 0.05em; }
`);
{
  const para = "Based on the details in this ticket, the customer reports a duplicate charge, and they also can't log in to their account. Both problems affect their money and their access, and they've asked for help today. Taking all of this into account, I would classify this ticket as urgent. So the short answer is ";
  scene("s-hook", "b01", "b03", `
<div class="card" id="tk"><span class="mono">Support ticket #4471</span><span class="b">Hi, my card was charged twice and now the app won't let me log in. Please help today.</span></div>
<div id="tk-q">Is this ticket urgent?</div>
<div class="card" id="llm"><div class="llm-h"><span>Large language model</span><span class="chip" id="llm-n">0 words</span></div>
<div id="llm-p"><span id="llm-t"></span><span id="llm-yes">yes.</span></div></div>
<div id="hk-claim">It only needed <span class="serif pill" id="hk-pill">one word</span>.</div>`);
  const t0 = F("b02", 0.25), dur = r2(E("b02") - t0 - 0.2), nW = para.split(/\s+/).length + 1;
  js(`
land("#tk", ${T("b01")}, {from:0.95, y:24});
land("#tk-q", ${F("b01", 0.55)}, {from:0.9, y:14});
to("#tk, #tk-q", {x:${-25 * PX}, scale:0.86, duration:0.55, ease:"power3.inOut"}, ${T("b02")});
land("#llm", ${r2(T("b02") + 0.5)}, {from:0.96, y:24});
type("#llm-t", ${JSON.stringify(para)}, ${t0}, ${dur});
count("#llm-n", ${nW}, ${t0}, ${dur}, function(n){ return Math.round(n) + " words"; });
fade("#llm-yes", ${r2(t0 + dur)}, {d:0.2});
tl.to("#llm-t", {opacity:0.18, duration:0.4}, ${T("b03")});
tl.to("#llm-yes", {backgroundColor:"#f0a87a", scale:1.25, duration:0.35, ease:"back.out(2)"}, ${F("b03", 0.15)});
tl.to("#tk, #tk-q", {opacity:0.3, duration:0.4}, ${F("b03", 0.45)});
rise("#hk-claim", ${F("b03", 0.5)}, {y:20});
land("#hk-pill", ${F("b03", 0.8)}, {from:0.6, ease:"back.out(2.2)"});
`);
}

// ============================================================ 0 · JEV + 13%
css(`
#jv-w { position:absolute; left:8cqw; top:17cqh; }
#jv-w .w { font-size:13cqw; letter-spacing:-0.05em; line-height:0.9; }
#jv-w .mono { font-size:1.2cqw; margin-top:1.2cqw; }
#jv-c { left:46cqw; top:17cqh; width:46cqw; padding:1.8cqw 2cqw; display:flex; flex-direction:column; gap:1.3cqw; }
#jv-c .q { font-size:2cqw; }
#jv-c .row { display:flex; align-items:center; gap:1.2cqw; }
#jv-c .ans { font-family:"JetBrains Mono"; font-size:2.6cqw; background:var(--fg); color:var(--bg); padding:0.5cqw 1.4cqw; border-radius:0.6cqw; }
#jv-c .p { font-family:"JetBrains Mono"; font-size:1.6cqw; }
#jv-c .bar { flex:1; height:1.1cqw; border-radius:1cqw; background:rgba(22,21,19,0.12); overflow:hidden; }
#jv-c .bar b { display:block; width:94%; height:100%; background:var(--accent-strong); transform-origin:0 50%; }
#jv-c .zero { align-self:flex-start; font-size:1.25cqw; padding:0.4cqw 1cqw; border-radius:999px; background:var(--sage); border:0.12cqw solid var(--fg); }
#jv-st { position:absolute; left:8cqw; top:55cqh; display:flex; align-items:center; gap:2.4cqw; }
#jv-st .n { font-size:11cqw; }
#jv-st .l { font-size:2.2cqw; line-height:1.3; max-width:42cqw; }
#jv-st .mono { font-size:1.05cqw; color:var(--muted); margin-top:0.8cqw; display:block; }
`);
scene("s-jev", "b04", "b05", `
<div id="jv-w"><div class="w">Jev</div><div class="mono">a decision model</div></div>
<div class="card" id="jv-c"><span class="mono k">same ticket, same question</span><span class="q">Is this ticket urgent?</span>
<div class="row"><span class="ans" id="jv-a">yes</span><span class="p">0.94</span><span class="bar"><b id="jv-b"></b></span></div>
<span class="mono zero" id="jv-z">0 words written</span></div>
<div id="jv-st"><span class="big n" id="jv-n">0%</span><div class="l">of paying teams on Vercel's AI Gateway used it in its first day<span class="mono">TechTarget · 15 Sep 2026 launch</span></div></div>`);
js(`
land("#jv-c", ${r2(T("b04") + 0.1)}, {from:0.95, y:20});
land("#jv-a", ${F("b04", 0.35)}, {from:0.5, ease:"back.out(2.2)"});
tl.fromTo("#jv-b", {scaleX:0}, {scaleX:1, duration:0.5, ease:"power2.out"}, ${r2(F("b04", 0.35) + 0.1)});
fade("#jv-z", ${F("b04", 0.55)});
rise("#jv-w", ${F("b04", 0.8)}, {y:30});
rise("#jv-st", ${T("b05")}, {y:20});
fade("#jv-n", ${r2(T("b05") + 0.1)}, {d:0.15});
count("#jv-n", 13, ${r2(T("b05") + 0.1)}, 0.8, function(n){ return Math.round(n) + "%"; });
`);

// ============================================================ 0 · TITLE
css(`
#ttl { position:absolute; left:0; right:0; top:24cqh; display:flex; flex-direction:column; align-items:center; gap:2cqw; }
#ttl .k { font-size:1.1cqw; color:var(--fg); }
#ttl .w { font-size:9.4cqw; letter-spacing:-0.045em; line-height:1; }
#ttl-s { font-size:3.2cqw; color:var(--muted); }
#ttl-s .pill { color:var(--fg); padding:0 0.35em 0.05em; }
#ttl-opts { position:absolute; left:0; right:0; top:72cqh; display:flex; justify-content:center; gap:1.4cqw; }
#ttl-opts span { font-size:1.6cqw; padding:0.5cqw 1.4cqw; border-radius:999px; border:0.14cqw solid var(--fg); background:var(--surface); display:flex; align-items:center; gap:0.6cqw; }
#ttl-opts span.on { background:var(--butter); }
`);
scene("s-title", "b06", "b06", `
<div id="ttl"><div class="mono k" id="ttl-k">AI, explained · Episode 02</div><div class="w" id="ttl-a">Jev, explained</div>
<div class="serif" id="ttl-s">and how to use it in <span class="pill">RAG</span></div></div>
<div id="ttl-opts"><span>billing</span><span class="on" id="ttl-on"><i class="ok"></i>tech</span><span>sales</span></div>`);
js(`
fade("#ttl-k", ${T("b06")});
rise("#ttl-a", ${T("b06") + 0.15}, {y:40, d:0.6});
rise("#ttl-s", ${F("b06", 0.5)}, {y:16});
rise("#ttl-opts span", ${F("b06", 0.7)}, {st:0.1, y:12});
land("#ttl-on", ${F("b06", 0.95)}, {from:1.25, ease:"back.out(2)"});
`);

// ============================================================ 1 · company
css(`
#co { left:23cqw; top:22cqh; width:54cqw; padding:3cqw 3.4cqw; display:flex; flex-direction:column; gap:1.4cqw; align-items:flex-start; }
#co .h { font-size:7cqw; letter-spacing:-0.04em; line-height:1; }
#co .rows { display:flex; flex-direction:column; gap:0.9cqw; }
#co .rows span { font-size:2.4cqw; display:flex; align-items:center; gap:1cqw; }
#co .rows .mono { font-size:1.2cqw; color:var(--muted); width:12cqw; }
`);
scene("s-co", "b07", "b07", `
<div class="card" id="co"><span class="mono k">the company</span><span class="h">TypeSafe AI</span>
<div class="rows"><span id="co1"><span class="mono">founded by</span>a former OpenAI researcher</span><span id="co2"><span class="mono">launched</span>15 September 2026</span></div></div>`);
js(`
land("#co", ${T("b07")}, {from:0.95, y:20});
rise("#co1", ${F("b07", 0.45)}, {y:12});
rise("#co2", ${F("b07", 0.85)}, {y:12});
`);

// ============================================================ 1 · generate vs pick
css(`
.pn { top:16cqh; width:40cqw; height:51cqh; padding:2cqw 2.2cqw; display:flex; flex-direction:column; gap:1.2cqw; }
#pn-l { left:7cqw; } #pn-r { left:53cqw; }
.pn .mono { font-size:1.15cqw; color:var(--muted); }
.pn .v { font-size:5.4cqw; letter-spacing:-0.04em; line-height:1; }
#pn-words { display:flex; flex-wrap:wrap; gap:0.6cqw; margin-top:1cqw; }
#pn-words span { font-size:1.95cqw; padding:0.35cqw 0.8cqw; border-radius:0.5cqw; background:var(--bg-deep); border:0.1cqw solid rgba(22,21,19,0.25); }
#pn-opts { display:flex; flex-direction:column; gap:0.9cqw; margin-top:1cqw; }
#pn-opts span { font-size:2.4cqw; padding:0.7cqw 1.4cqw; border-radius:999px; border:0.14cqw solid var(--fg); background:var(--bg); display:flex; align-items:center; gap:1cqw; align-self:flex-start; }
#pn-s1 { position:absolute; left:53cqw; top:71.5cqh; width:41cqw; display:flex; align-items:center; gap:1.2cqw; font-size:2.1cqw; }
#pn-s1 .chip { background:var(--accent); font-size:1.3cqw; }
`);
{
  const words = "The ticket mentions a duplicate charge and a login problem, so this seems".split(" ");
  scene("s-split", "b08", "b10", `
<div class="card pn" id="pn-l"><span class="mono">Language model</span><span class="v">generates</span>
<div id="pn-words">${words.map((w) => `<span>${esc(w)}</span>`).join("")}</div></div>
<div class="card pn" id="pn-r"><span class="mono">Decision model · Jev</span><span class="v">picks</span>
<div id="pn-opts"><span><i class="ok" style="opacity:0"></i>low</span><span><i class="ok" style="opacity:0"></i>normal</span><span id="pn-on"><i class="ok"></i>urgent</span></div></div>
<div id="pn-s1"><span class="chip">System One model</span><span>fast, gut-feel decisions</span></div>`);
  js(`
land("#pn-l", ${T("b08")}, {from:0.95, y:20});
rise("#pn-words span", ${F("b08", 0.55)}, {st:${r2(Math.max(0.08, (E("b08") - F("b08", 0.55) - 0.3) / words.length))}, y:8, d:0.25});
land("#pn-r", ${T("b09")}, {from:0.95, y:20});
rise("#pn-opts span", ${F("b09", 0.3)}, {st:0.12, y:10});
tl.fromTo("#pn-on", {backgroundColor:"#f3ecd9"}, {backgroundColor:"#f0c860", duration:0.3}, ${F("b09", 0.85)});
land("#pn-on .ok", ${F("b09", 0.85)}, {from:0, ease:"back.out(2.4)"});
tl.to("#pn-l", {opacity:0.4, duration:0.4}, ${T("b10")});
rise("#pn-s1", ${F("b10", 0.2)}, {y:14});
`);
}

// ============================================================ 1 · input -> typed answer
css(`
.fl { top:30cqh; height:28cqh; padding:1.8cqw 2cqw; display:flex; flex-direction:column; gap:1cqw; }
#fl1 { left:5cqw; width:24cqw; } #fl2 { left:32cqw; width:24cqw; } #fl4 { left:72cqw; width:23cqw; }
.fl .mono { font-size:1.05cqw; color:var(--muted); }
.fl .b { font-size:2cqw; line-height:1.38; }
.fl .opt { display:flex; gap:0.6cqw; flex-wrap:wrap; }
.fl .opt span { font-size:1.6cqw; padding:0.3cqw 0.9cqw; border-radius:999px; border:0.12cqw solid var(--fg); }
#fl3 { position:absolute; left:59.3cqw; top:38cqh; width:10cqw; height:10cqw; border-radius:50%; background:var(--fg); color:var(--bg); display:flex; align-items:center; justify-content:center; font-size:2.6cqw; letter-spacing:-0.03em; }
#fl4 pre { font-family:"JetBrains Mono"; font-size:1.75cqw; line-height:1.6; background:var(--fg); color:#f7f2e6; border-radius:0.7cqw; padding:1cqw 1.2cqw; }
#fl4 pre b { color:var(--butter); font-weight:500; }
#fl-plus { position:absolute; left:29.3cqw; top:41cqh; font-size:3cqw; }
`);
{
  const L = [sline(...P(56, 45), ...P(59.3, 45), "fll1"), sline(...P(69.3, 45), ...P(72, 45), "fll2")];
  scene("s-flow", "b11", "b11", `
<div class="card fl" id="fl1"><span class="mono">your text</span><span class="b">"Charged twice, can't log in. Please help today."</span></div>
<div id="fl-plus">+</div>
<div class="card fl" id="fl2"><span class="mono">question + allowed answers</span><span class="b">Which team should handle this?</span><div class="opt"><span>billing</span><span>tech</span><span>sales</span></div></div>
${svg("fl-svg", L.join(""))}
<div id="fl3">Jev</div>
<div class="card fl" id="fl4"><span class="mono">typed answer</span><pre>{
  team: <b>"billing"</b>,
  p: 0.82
}</pre></div>`);
  js(`
land("#fl1", ${T("b11")}, {from:0.95, y:20});
fade("#fl-plus", ${F("b11", 0.2)});
land("#fl2", ${F("b11", 0.22)}, {from:0.95, y:20});
draw("#fll1", ${F("b11", 0.5)}, {d:0.3});
land("#fl3", ${F("b11", 0.52)}, {from:0, ease:"back.out(2)"});
draw("#fll2", ${F("b11", 0.62)}, {d:0.3});
land("#fl4", ${F("b11", 0.66)}, {from:0.95, y:20});
`);
}

// ============================================================ 2 · three questions
css(`
.q3 { top:15cqh; width:27.5cqw; height:47cqh; padding:1.6cqw 1.8cqw; display:flex; flex-direction:column; gap:1cqw; }
#q1 { left:5.5cqw; } #q2 { left:36.25cqw; } #q3 { left:67cqw; }
.q3 .top { display:flex; align-items:center; gap:0.9cqw; }
.q3 .n { font-family:"JetBrains Mono"; font-size:1.2cqw; background:var(--fg); color:var(--bg); border-radius:0.4cqw; padding:0.2cqw 0.6cqw; }
.q3 .t { font-size:2.8cqw; letter-spacing:-0.03em; }
.q3 .d { font-size:1.4cqw; color:var(--muted); line-height:1.3; }
.q3 .ex { font-size:1.65cqw; line-height:1.3; margin-top:0.4cqw; }
.bars { display:flex; flex-direction:column; gap:0.8cqw; margin-top:0.6cqw; }
.bars div { display:grid; grid-template-columns:6cqw 1fr 4cqw; align-items:center; gap:0.8cqw; font-size:1.45cqw; }
.bars i { display:block; height:1.4cqw; border-radius:0.3cqw; background:rgba(22,21,19,0.15); overflow:hidden; }
.bars b { display:block; height:100%; background:var(--fg); transform-origin:0 50%; }
.bars .w b { background:var(--accent-strong); }
.bars em { font-style:normal; font-family:"JetBrains Mono"; font-size:1.2cqw; text-align:right; }
.lad { position:relative; display:flex; gap:0.4cqw; margin-top:1.4cqw; }
.lad span { flex:1; text-align:center; font-size:1.25cqw; padding:0.7cqw 0; background:var(--bg-deep); border:0.12cqw solid rgba(22,21,19,0.3); }
.lad span:first-child { border-radius:0.6cqw 0 0 0.6cqw; } .lad span:last-child { border-radius:0 0.6cqw 0.6cqw 0; }
.lad span.on { background:var(--accent); border-color:var(--fg); }
#q2-mk { position:absolute; top:-2.2cqw; left:14cqw; width:0; height:0; border-left:0.9cqw solid transparent; border-right:0.9cqw solid transparent; border-top:1.3cqw solid var(--fg); }
.ring { position:relative; width:11cqw; height:11cqw; margin:1cqw auto 0; }
.ring svg { position:absolute; inset:0; }
.ring .v { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-family:"Instrument Serif"; font-style:italic; font-size:4cqw; }
#cf { position:absolute; left:5.5cqw; top:68cqh; width:89cqw; display:flex; align-items:center; gap:1.6cqw; }
#cf .mono { font-size:1.1cqw; }
#cf-track { position:relative; flex:none; width:70cqw; height:1.6cqw; border-radius:1cqw; background:linear-gradient(90deg, rgba(240,168,122,0.55) 0 60%, rgba(169,199,155,0.75) 60% 100%); border:0.12cqw solid var(--fg); }
#cf-th { position:absolute; left:60%; top:-1.2cqw; width:0.2cqw; height:4cqw; background:var(--fg); }
#cf-thl { position:absolute; left:48%; top:2.6cqw; font-size:1.2cqw; white-space:nowrap; }
#cf-thr { position:absolute; left:72%; top:2.6cqw; font-size:1.2cqw; white-space:nowrap; }
#cf-dot { position:absolute; left:0; top:-0.5cqw; width:2.6cqw; height:2.6cqw; margin-left:-1.3cqw; border-radius:50%; background:var(--fg); border:0.3cqw solid var(--surface); }
`);
{
  const R = 0.42 * 11 * PX, C = r2(2 * Math.PI * R), c = r2(5.5 * PX);
  scene("s-three", "b12", "b16", `
<div class="card q3" id="q1"><div class="top"><span class="n">1</span><span class="t">Choice</span></div><span class="d">pick one option from your list</span>
<span class="ex" id="q1-ex">Which team should get this ticket?</span>
<div class="bars" id="q1-b"><div class="w"><span>Billing</span><i><b style="width:82%"></b></i><em>0.82</em></div><div><span>Tech</span><i><b style="width:13%"></b></i><em>0.13</em></div><div><span>Sales</span><i><b style="width:5%"></b></i><em>0.05</em></div></div></div>
<div class="card q3" id="q2"><div class="top"><span class="n">2</span><span class="t">Score</span></div><span class="d">rate it on a scale you define</span>
<span class="ex" id="q2-ex">How upset is this customer?</span>
<div class="lad" id="q2-l"><span>calm</span><span>annoyed</span><span id="q2-on">upset</span><span>furious</span><i id="q2-mk"></i></div></div>
<div class="card q3" id="q3"><div class="top"><span class="n">3</span><span class="t">True or false</span></div><span class="d">TypeSafe calls this a "noul": a yes or no statement, with a probability</span>
<span class="ex" id="q3-ex">"This customer wants a refund."</span>
<div class="ring" id="q3-r"><svg viewBox="0 0 ${r2(11 * PX)} ${r2(11 * PX)}"><circle cx="${c}" cy="${c}" r="${r2(R)}" fill="none" stroke="rgba(22,21,19,0.12)" stroke-width="14"/>
<circle id="q3-arc" cx="${c}" cy="${c}" r="${r2(R)}" fill="none" stroke="#e07a45" stroke-width="14" stroke-dasharray="${C}" stroke-dashoffset="${C}" transform="rotate(-90 ${c} ${c})"/></svg><span class="v" id="q3-v">0%</span></div></div>
<div id="cf"><span class="mono">confidence</span><div id="cf-track"><i id="cf-th"></i><span id="cf-thl">ask a human</span><span id="cf-thr">trust it</span><i id="cf-dot"></i></div><span class="mono" id="cf-n">0.00</span></div>`);
  js(`
land(".q3", ${T("b12")}, {from:0.95, y:24, st:0.12});
tl.to("#q2, #q3", {opacity:0.35, duration:0.3}, ${T("b13")});
rise("#q1-ex", ${F("b13", 0.5)}, {y:10});
rise("#q1-b > div", ${F("b13", 0.7)}, {st:0.12, y:8});
tl.fromTo("#q1-b b", {scaleX:0}, {scaleX:1, duration:0.6, ease:"power2.out", stagger:0.12}, ${F("b13", 0.75)});
tl.to("#q1", {opacity:0.35, duration:0.3}, ${T("b14")});
tl.to("#q2", {opacity:1, duration:0.3}, ${T("b14")});
rise("#q2-ex", ${F("b14", 0.55)}, {y:10});
rise("#q2-l > span", ${F("b14", 0.7)}, {st:0.08, y:8});
tl.fromTo("#q2-mk", {x:${-12 * PX}, opacity:0}, {x:0, opacity:1, duration:0.7, ease:"power3.out"}, ${F("b14", 0.85)});
tl.to("#q2-on", {backgroundColor:"#f0a87a", duration:0.3}, ${r2(F("b14", 0.85) + 0.6)});
tl.to("#q2", {opacity:0.35, duration:0.3}, ${T("b15")});
tl.to("#q3", {opacity:1, duration:0.3}, ${T("b15")});
rise("#q3-ex", ${F("b15", 0.6)}, {y:10});
tl.to("#q3-arc", {strokeDashoffset:${r2(C * 0.29)}, duration:0.8, ease:"power2.out"}, ${F("b15", 0.8)});
fade("#q3-v", ${F("b15", 0.8)}, {d:0.15});
count("#q3-v", 71, ${F("b15", 0.8)}, 0.8, function(n){ return Math.round(n) + "%"; });
tl.to("#q1, #q2", {opacity:1, duration:0.3}, ${T("b16")});
fade("#cf", ${T("b16")});
tl.fromTo("#cf-dot", {x:0}, {x:${r2(0.88 * 70 * PX)}, duration:0.9, ease:"power2.out"}, ${F("b16", 0.3)});
count("#cf-n", 91, ${F("b16", 0.3)}, 0.9, function(n){ return "0." + String(Math.round(n)).padStart(2, "0"); });
tl.to("#cf-dot", {x:${r2(0.38 * 70 * PX)}, duration:0.7, ease:"power2.inOut"}, ${F("b16", 0.75)});
tl.to("#cf-n", {opacity:0, duration:0.15}, ${F("b16", 0.75)});
`);
}

// ============================================================ 3 · fast + cheap
css(`
#sp { position:absolute; left:6cqw; top:15cqh; width:36cqw; }
#sp .n { font-size:11cqw; }
#sp .l { font-size:2.2cqw; margin-top:0.6cqw; }
#sp-chips { display:grid; grid-template-columns:repeat(5, 1fr); gap:0.6cqw; margin-top:1.6cqw; }
#sp-chips span { font-family:"JetBrains Mono"; font-size:1.35cqw; text-align:center; padding:0.6cqw 0; border-radius:0.4cqw; background:var(--sage); border:0.12cqw solid var(--fg); }
#bars { left:48cqw; top:15cqh; width:46cqw; padding:2cqw 2.2cqw; display:flex; flex-direction:column; gap:1.5cqw; }
#bars .mono { font-size:1.05cqw; color:var(--muted); }
.cb { display:flex; flex-direction:column; gap:0.5cqw; }
.cb .lb { display:flex; align-items:baseline; gap:1cqw; font-size:1.8cqw; }
.cb .lb .pr { margin-left:auto; font-family:"JetBrains Mono"; font-size:1.7cqw; }
.cb i { display:block; height:2.6cqw; border-radius:0.4cqw; background:rgba(22,21,19,0.08); position:relative; }
.cb b { position:absolute; left:0; top:0; bottom:0; border-radius:0.4cqw; transform-origin:0 50%; }
#cb1 b { width:2.1%; min-width:0.5cqw; background:var(--accent-strong); }
#cb2 b { width:100%; background:var(--fg); }
#cb-free { align-self:flex-start; background:var(--sage); }
#rc { left:6cqw; top:58cqh; width:36cqw; padding:1.6cqw 1.9cqw; display:flex; flex-direction:column; gap:0.6cqw; border-style:dashed; }
#rc .mono { font-size:1.05cqw; color:var(--muted); }
#rc .row { display:flex; align-items:baseline; justify-content:space-between; font-size:1.8cqw; }
#rc .n { font-size:5cqw; }
#ratio { left:48cqw; top:58cqh; width:46cqw; padding:1.6cqw 2cqw; font-size:2.1cqw; line-height:1.35; }
#ratio .pill { padding:0 0.35em 0.05em; }
`);
scene("s-cheap", "b17", "b20", `
<div id="sp"><span class="big n" id="sp-n">0</span><div class="l">decision loops a second</div>
<div id="sp-chips">${["urgent", "billing", "0.82", "yes", "upset", "no", "tech", "0.91", "spam", "keep"].map((s) => `<span>${s}</span>`).join("")}</div></div>
<div class="card" id="bars"><span class="mono">price to read 1 million tokens (input)</span>
<div class="cb" id="cb1"><div class="lb"><span>Jev</span><span class="pr">$0.042</span></div><i><b></b></i></div>
<span class="chip" id="cb-free">answers (output): free</span>
<div class="cb" id="cb2"><div class="lb"><span>GPT-6.1 Sol</span><span class="pr">$2.00</span></div><i><b></b></i></div></div>
<div class="card" id="rc"><span class="mono">TypeSafe's example</span><div class="row"><span>1,000,000 support tickets</span></div><div class="row"><span>sorted for about</span><span class="big n" id="rc-n">$0</span></div></div>`);
js(`
rise("#sp", ${T("b17")}, {y:20});
fade("#sp-n", ${r2(T("b17") + 0.15)}, {d:0.15});
count("#sp-n", 10, ${r2(T("b17") + 0.15)}, 0.9, function(n){ return "~" + Math.round(n); });
land("#sp-chips span", ${F("b17", 0.5)}, {from:0.4, st:0.1, ease:"back.out(2)"});
land("#bars", ${T("b18")}, {from:0.96, y:20});
rise("#cb1", ${F("b18", 0.35)}, {y:10});
tl.fromTo("#cb1 b", {scaleX:0}, {scaleX:1, duration:0.4, ease:"power2.out"}, ${F("b18", 0.5)});
land("#cb-free", ${F("b18", 0.85)}, {from:0.7});
rise("#cb2", ${F("b19", 0.3)}, {y:10});
tl.fromTo("#cb2 b", {scaleX:0}, {scaleX:1, duration:1.1, ease:"power2.inOut"}, ${F("b19", 0.5)});
land("#rc", ${T("b20")}, {from:0.95, y:20});
fade("#rc-n", ${F("b20", 0.75)}, {d:0.15});
count("#rc-n", 19, ${F("b20", 0.75)}, 0.7, function(n){ return "$" + Math.round(n); });
`);

// ============================================================ 4 · RAG pipeline
const NODES = [["q", "Question", 9], ["s", "Search", 28], ["c", "Chunks", 47], ["m", "Model", 66], ["a", "Answer", 85]];
const NY = 21; // node centre, cqh
css(`
.nd { position:absolute; top:${NY - 4}cqh; width:13cqw; height:8cqh; margin-left:-6.5cqw; display:flex; align-items:center; justify-content:center;
  font-size:1.8cqw; background:var(--surface); border:0.14cqw solid var(--fg); border-radius:0.9cqw; box-shadow:0 0.3cqw 0 var(--fg); }
.slot { position:absolute; width:3.6cqw; height:3.6cqw; margin:-1.8cqw 0 0 -1.8cqw; border-radius:50%; background:var(--accent-strong); border:0.18cqw solid var(--fg);
  color:var(--fg); font-family:"JetBrains Mono"; font-size:1.3cqw; display:flex; align-items:center; justify-content:center; }
.slotl { position:absolute; font-family:"JetBrains Mono"; text-transform:uppercase; letter-spacing:0.1em; font-size:1.05cqw; width:12cqw; margin-left:-6cqw; text-align:center; }
#pipe { position:absolute; inset:0; transform-origin:50% ${NY}cqh; }
.dt { position:absolute; left:5cqw; right:5cqw; top:36cqh; height:48cqh; }
.dt .ttl { font-size:2.6cqw; letter-spacing:-0.03em; }
.dt .ttl .n { font-family:"JetBrains Mono"; font-size:1.3cqw; background:var(--fg); color:var(--bg); border-radius:0.4cqw; padding:0.2cqw 0.6cqw; margin-right:0.8cqw; vertical-align:0.3cqw; }
/* routing */
.rt { position:absolute; left:0; display:flex; align-items:center; gap:1.4cqw; width:90cqw; }
.rt .qq { width:31cqw; font-size:1.7cqw; padding:0.8cqw 1.3cqw; border-radius:1cqw; background:var(--fg); color:#f7f2e6; }
.rt .lane { flex:1; height:0.2cqw; background:var(--fg); opacity:0.5; transform-origin:0 50%; }
.rt .ty { width:15cqw; text-align:center; font-family:"JetBrains Mono"; text-transform:uppercase; letter-spacing:0.08em; font-size:1.1cqw; padding:0.5cqw 0; border-radius:999px; border:0.12cqw solid var(--fg); background:var(--surface); }
.rt .to { width:17cqw; font-size:1.9cqw; padding:0.6cqw 1.2cqw; border-radius:0.8cqw; border:0.14cqw solid var(--fg); background:var(--surface); text-align:center; }
#rt1 { top:7cqh; } #rt2 { top:19cqh; } #rt3 { top:31cqh; }
#rt-could { position:absolute; right:0; top:0; background:var(--butter); }
/* filtering */
#ch-row { position:absolute; left:0; top:8cqh; width:90cqw; display:grid; grid-template-columns:repeat(8, 1fr); gap:1cqw; }
.chk2 { position:relative; height:17cqh; background:var(--surface); border:0.14cqw solid var(--fg); border-radius:0.7cqw; padding:1cqw; display:flex; flex-direction:column; gap:0.5cqw; }
.chk2 i { display:block; height:0.35cqw; background:var(--fg); opacity:0.3; border-radius:1px; }
.chk2 i:nth-child(2) { width:80%; } .chk2 i:nth-child(3) { width:60%; }
.chk2 .sc { position:absolute; left:50%; bottom:-1.5cqw; width:5cqw; margin-left:-2.5cqw; text-align:center; font-family:"JetBrains Mono"; font-size:1.2cqw; padding:0.3cqw 0; border-radius:999px; border:0.12cqw solid var(--fg); }
.chk2 .sc.hi { background:var(--sage); } .chk2 .sc.lo { background:var(--accent); }
#ch-stat { position:absolute; left:0; top:33cqh; display:flex; gap:1.4cqw; align-items:center; font-size:1.9cqw; }
#ch-stat .chip { font-size:1.2cqw; }
#ch-stat .mono { font-size:1.05cqw; color:var(--muted); }
/* checking */
#ck-a { position:absolute; left:0; top:7cqh; width:34cqw; padding:1.4cqw 1.6cqw; font-size:1.8cqw; line-height:1.38; }
#ck-a .mono { display:block; font-size:1.05cqw; color:var(--muted); margin-bottom:0.6cqw; }
.ck { position:absolute; left:39cqw; width:51cqw; display:flex; align-items:center; gap:1.2cqw; font-size:1.6cqw; }
.ck .src { flex:1; padding:0.7cqw 1.1cqw; border-radius:0.6cqw; background:var(--surface); border:0.12cqw solid rgba(22,21,19,0.4); }
.ck .lab { width:14cqw; text-align:center; font-family:"JetBrains Mono"; text-transform:uppercase; letter-spacing:0.06em; font-size:1.05cqw; padding:0.55cqw 0; border-radius:999px; border:0.12cqw solid var(--fg); }
#ck1 { top:7cqh; } #ck2 { top:16cqh; } #ck3 { top:25cqh; } #ck4 { top:34cqh; }
/* summary */
#sum { position:absolute; left:0; right:0; top:10cqh; text-align:center; font-size:4.6cqw; letter-spacing:-0.035em; line-height:1.15; }
#sum .pill { padding:0 0.35em 0.05em; }
#sum .m { color:var(--muted); }
`);
{
  const lines = [];
  for (let i = 0; i < NODES.length - 1; i++) lines.push(sline(...P(NODES[i][2] + 6.5, NY), ...P(NODES[i + 1][2] - 6.5, NY), `pl${i}`));
  const SLOTS = [[18.5, NY, "1", "route"], [56.5, NY, "2", "filter"], [85, NY + 7.2, "3", "check"]];
  lines.push(sline(...P(85, NY + 4), ...P(85, NY + 5.4), "pl-ck"));
  const chunks = [[0.92, 1], [0.14, 0], [0.81, 1], [0.07, 0], [0.66, 1], [0.12, 0], [0.88, 1], [0.21, 0]];
  scene("s-rag", "b21", "b28", `
<div id="pipe">${svg("pl-svg", lines.join(""))}
${NODES.map(([id, l, xx]) => `<div class="nd" id="nd-${id}" style="left:${xx}cqw">${l}</div>`).join("")}
${SLOTS.map(([xx, yy, n, l], i) => `<div class="slot" id="sl${i}" style="left:${xx}cqw; top:${yy}cqh">${n}</div><div class="slotl" id="sll${i}" style="left:${xx}cqw; top:${yy + (i === 2 ? 2.6 : 3.4)}cqh">${l}</div>`).join("")}</div>
<div class="dt" id="dt-r"><div class="ttl"><span class="n">1</span>Routing</div><span class="chip" id="rt-could">you could</span>
  <div class="rt" id="rt1"><span class="qq">"Thanks, that helped!"</span><i class="lane"></i><span class="ty">small talk</span><i class="lane"></i><span class="to" id="rt1t">no search</span></div>
  <div class="rt" id="rt2"><span class="qq">"When did GraphRAG come out?"</span><i class="lane"></i><span class="ty">simple fact</span><i class="lane"></i><span class="to" id="rt2t">plain RAG</span></div>
  <div class="rt" id="rt3"><span class="qq">"What are the main themes?"</span><i class="lane"></i><span class="ty">big picture</span><i class="lane"></i><span class="to" id="rt3t">GraphRAG</span></div></div>
<div class="dt" id="dt-f"><div class="ttl"><span class="n">2</span>Filtering</div>
  <div id="ch-row">${chunks.map(([s, hi], i) => `<div class="chk2" id="ck-${i}"><i></i><i></i><i></i><span class="sc ${hi ? "hi" : "lo"}">${s.toFixed(2)}</span></div>`).join("")}</div>
  <div id="ch-stat"><span class="chip">60 chunks</span><span>≈ 30,000 tokens</span><span>≈ a tenth of a cent</span><span class="mono">per question · The AI Automators</span></div></div>
<div class="dt" id="dt-c"><div class="ttl"><span class="n">3</span>Checking</div>
  <div class="card" id="ck-a"><span class="mono">the answer</span>GraphRAG came out in 2024, and it builds a knowledge graph before you ask anything.</div>
  <div class="ck" id="ck1"><span class="src">Source A: the paper, April 2024</span><span class="lab" style="background:var(--sage)">full support</span></div>
  <div class="ck" id="ck2"><span class="src">Source B: a blog post</span><span class="lab" style="background:var(--butter)">partial</span></div>
  <div class="ck" id="ck3"><span class="src">Source C: a recipe page</span><span class="lab" style="background:var(--bg-deep)">not relevant</span></div>
  <div class="ck" id="ck4"><span class="src">Source D: "released in 2022"</span><span class="lab" style="background:var(--accent)">contradicts</span></div></div>
<div class="dt" id="dt-s"><div id="sum"><span class="m">The model</span> writes.<br>Jev <span class="serif pill">decides</span>.</div></div>`);
  js(`
tl.set("#pipe", {y:${r2(24 * PY)}}, ${T("b21")});
to("#pipe", {y:0, duration:0.8, ease:"power3.inOut"}, ${r2(T("b23") - 0.1)});
land(".nd", ${T("b21")}, {from:0.9, y:14, st:0.12});
draw("#pl-svg line:not(#pl-ck)", ${F("b21", 0.4)}, {st:0.15, d:0.35});
tl.to("#nd-m", {backgroundColor:"#f0c860", duration:0.3}, ${F("b21", 0.85)});
tl.to("#nd-m", {backgroundColor:"#faf6ec", duration:0.3}, ${T("b22")});
draw("#pl-ck", ${F("b22", 0.6)}, {d:0.2});
land(".slot", ${F("b22", 0.6)}, {from:0, st:0.25, ease:"back.out(2.4)"});
fade(".slotl", ${r2(F("b22", 0.6) + 0.3)}, {st:0.25});
// routing
tl.to("#sl1, #sl2, #sll1, #sll2", {opacity:0.3, duration:0.3}, ${T("b23")});
rise("#dt-r .ttl", ${T("b23")}, {y:12});
${[12, 15, 19].map((w, k) => `rise("#rt${k + 1} .qq", ${Wd("b23", w)}, {y:10});
tl.fromTo("#rt${k + 1} .lane", {scaleX:0}, {scaleX:1, duration:0.3, ease:"power2.out", stagger:0.3}, ${r2(Wd("b23", w) + 0.2)});
land("#rt${k + 1} .ty", ${r2(Wd("b23", w) + 0.35)}, {from:0.7});`).join("\n")}
land(".rt .to", ${T("b24")}, {from:0.8, st:0.15});
tl.to("#rt2t", {backgroundColor:"#f0c860", duration:0.3}, ${F("b24", 0.3)});
tl.to("#rt3t", {backgroundColor:"#f0a87a", duration:0.3}, ${F("b24", 0.4)});
land("#rt-could", ${F("b24", 0.1)}, {from:0.7});
exit("#dt-r", ${T("b25")}, {y:-14});
// filtering
tl.to("#sl0, #sll0", {opacity:0.3, duration:0.3}, ${T("b25")});
tl.to("#sl1, #sll1", {opacity:1, duration:0.3}, ${T("b25")});
rise("#dt-f .ttl", ${T("b25")}, {y:12});
land(".chk2", ${F("b25", 0.35)}, {from:0.85, st:0.07});
land(".chk2 .sc", ${F("b25", 0.65)}, {from:0.4, st:0.08, ease:"back.out(2)"});
${chunks.map(([, hi], i) => hi ? "" : `tl.to("#ck-${i}", {opacity:0.18, y:${2 * PY}, duration:0.4, ease:"power2.in"}, ${r2(F("b25", 0.88) + i * 0.04)});`).join("\n")}
rise("#ch-stat > *", ${T("b26")}, {st:0.35, y:10});
exit("#dt-f", ${T("b27")}, {y:-14});
// checking
tl.to("#sl1, #sll1", {opacity:0.3, duration:0.3}, ${T("b27")});
tl.to("#sl2, #sll2", {opacity:1, duration:0.3}, ${T("b27")});
rise("#dt-c .ttl", ${T("b27")}, {y:12});
land("#ck-a", ${F("b27", 0.25)}, {from:0.95, y:14});
rise(".ck .src", ${F("b27", 0.45)}, {st:0.12, y:10});
land(".ck .lab", ${F("b27", 0.7)}, {from:0.6, st:${r2(Math.max(0.2, (E("b27") - F("b27", 0.7) - 0.6) / 4))}, ease:"back.out(2)"});
exit("#dt-c", ${T("b28")}, {y:-14});
// summary
tl.to(".slot, .slotl", {opacity:1, duration:0.3}, ${T("b28")});
tl.to("#nd-m", {backgroundColor:"#bdb2ea", duration:0.3}, ${F("b28", 0.15)});
rise("#sum", ${F("b28", 0.1)}, {y:20});
tl.to(".slot", {scale:1.25, duration:0.25, ease:"power2.out", stagger:0.12}, ${F("b28", 0.55)});
tl.to(".slot", {scale:1, duration:0.3, ease:"back.out(2)", stagger:0.12}, ${r2(F("b28", 0.55) + 0.25)});
`);
}

// ============================================================ 5 · the catch
css(`
#cn { position:absolute; left:6cqw; top:19cqh; width:40cqw; }
#cn .h { font-size:4cqw; letter-spacing:-0.03em; margin-bottom:1.4cqw; }
#cn-g { display:grid; grid-template-columns:1fr 1fr; gap:1cqw; }
#cn-g span { display:flex; align-items:center; gap:1cqw; font-size:2.1cqw; padding:1.6cqw 1.4cqw; border-radius:0.8cqw; border:0.14cqw solid var(--fg); background:var(--surface); }
#inj { left:52cqw; top:19cqh; width:42cqw; padding:2.2cqw 2.4cqw; display:flex; flex-direction:column; gap:0.6cqw; }
#inj .mono { font-size:1.05cqw; color:var(--muted); }
#inj .n { font-size:9cqw; color:var(--accent-strong); }
#inj .l { font-size:2.2cqw; line-height:1.3; }
#nw { position:absolute; left:6cqw; top:68cqh; display:flex; gap:1cqw; align-items:center; }
#nw .chip { font-size:1.3cqw; background:var(--bg-deep); }
#nw .t { font-size:2.2cqw; margin-left:0.6cqw; }
.alt { top:19cqh; width:42cqw; height:46cqh; padding:2.4cqw 2.6cqw; display:flex; flex-direction:column; gap:1.2cqw; }
#alt1 { left:6cqw; } #alt2 { left:52cqw; }
.alt .mono { font-size:1.05cqw; color:var(--muted); }
.alt .h { font-size:4.2cqw; letter-spacing:-0.03em; line-height:1.05; }
.alt .tags { display:flex; gap:0.8cqw; flex-wrap:wrap; margin-top:auto; }
.alt .tags .chip { font-size:1.3cqw; }
`);
scene("s-catch", "b29", "b32", `
<div id="cn"><div class="h">It can't…</div><div id="cn-g"><span>${x()}write</span><span>${x()}explain itself</span><span>${x()}do exact math</span><span>${x()}read images</span></div></div>
<div class="card" id="inj"><span class="mono">it can be fooled</span><span class="big n" id="inj-n">0%</span><span class="l">of Check Point's attacks worked, using fake facts hidden inside documents</span><span class="mono">Check Point Research · 24 Sep 2026</span></div>
<div id="nw"><span class="chip">no public weights</span><span class="chip">no paper</span><span class="chip">API only</span><span class="t" id="nw-t">so you can't run it yourself</span></div>
<div class="card alt" id="alt1"><span class="mono">Amazon · 1 Oct 2026</span><span class="h">Strands Decider 2B</span><span style="font-size:2.2cqw; line-height:1.35">An open source, Jev-style decision model.</span><div class="tags"><span class="chip" style="background:var(--sage)">open source</span><span class="chip" style="background:var(--butter)">runs on your machine</span></div></div>
<div class="card alt" id="alt2"><span class="mono">OpenAI · DevDay, 29 Sep 2026</span><span class="h">Decisions API</span><span style="font-size:2.2cqw; line-height:1.35">Picks from options you define, using a model called Luna.</span><div class="tags"><span class="chip" style="background:var(--lilac)">limited preview</span></div></div>`);
js(`
rise("#cn .h", ${T("b29")}, {y:14});
${[6, 7, 10, 14].map((w, i) => `land("#cn-g span:nth-child(${i + 1})", ${Wd("b29", w)}, {from:0.85});`).join("\n")}
land("#inj", ${T("b30")}, {from:0.95, y:20});
fade("#inj-n", ${F("b30", 0.75)}, {d:0.15});
count("#inj-n", 59, ${F("b30", 0.75)}, 0.8, function(n){ return Math.round(n) + "%"; });
rise("#nw > *", ${T("b31")}, {st:0.12, y:10});
exit("#cn, #inj, #nw", ${T("b32")}, {y:-20});
land("#alt1", ${r2(T("b32") + 0.15)}, {from:0.95, y:24});
land("#alt2", ${Wd("b32", 19)}, {from:0.95, y:24});
`);

// ============================================================ 6 · recap + last line
css(`
.rcp { top:17cqh; width:39cqw; height:42cqh; padding:1.8cqw; display:flex; flex-direction:column; gap:1cqw; }
#rcp1 { left:9cqw; } #rcp2 { left:52cqw; }
.rcp .mono { font-size:1.15cqw; color:var(--muted); }
.rcp .h { font-size:5.4cqw; line-height:1; letter-spacing:-0.04em; }
.rcp .ln2 { display:flex; flex-direction:column; gap:0.7cqw; margin-top:auto; }
.rcp .ln2 i { display:block; height:0.5cqw; border-radius:1cqw; background:var(--fg); opacity:0.25; }
.rcp .ops { display:flex; gap:0.8cqw; margin-top:auto; }
.rcp .ops span { font-size:1.6cqw; padding:0.4cqw 1.1cqw; border-radius:999px; border:0.14cqw solid var(--fg); display:flex; gap:0.5cqw; align-items:center; }
#rc-use { position:absolute; left:0; right:0; top:67cqh; text-align:center; font-size:3cqw; letter-spacing:-0.02em; }
#last { position:absolute; left:8cqw; right:8cqw; top:30cqh; text-align:center; font-size:6.2cqw; letter-spacing:-0.04em; line-height:1.1; }
#last .pill { padding:0 0.35em 0.05em; background:transparent; box-shadow:inset 0 0 0 0.16cqw rgba(22,21,19,0.25); }
`);
scene("s-recap", "b33", "b35", `
<div class="card rcp" id="rcp1"><span class="mono">Language models</span><span class="h">write.</span><div class="ln2"><i></i><i style="width:92%"></i><i style="width:96%"></i><i style="width:70%"></i></div></div>
<div class="card rcp" id="rcp2"><span class="mono">Decision models · Jev</span><span class="h">pick.</span><div class="ops"><span>no</span><span style="background:var(--butter)"><i class="ok"></i>yes</span><span>maybe</span></div></div>
<div id="rc-use">Jev for the hundreds of small choices. The big model for the writing.</div>
<div id="last">Stop paying for an essay when all you need is a <span class="serif pill" id="last-p">yes</span>.</div>`);
js(`
land("#rcp1", ${r2(T("b33") + 0.1)}, {from:0.94, y:20});
land("#rcp2", ${F("b33", 0.75)}, {from:0.94, y:20});
rise("#rc-use", ${T("b34")}, {y:16});
exit("#rcp1, #rcp2, #rc-use", ${T("b35")}, {y:-20});
rise("#last", ${r2(T("b35") + 0.2)}, {y:24});
tl.to("#last-p", {backgroundColor:"#f0a87a", boxShadow:"inset 0 0 0 0px rgba(22,21,19,0)", scale:1.15, duration:0.25, ease:"power2.out"}, ${F("b35", 0.92)});
tl.to("#last-p", {scale:1, duration:0.3, ease:"back.out(2)"}, ${r2(F("b35", 0.92) + 0.25)});
`);
css(`
#end { position:absolute; left:0; right:0; top:28cqh; display:flex; flex-direction:column; align-items:center; gap:1.8cqw; }
#end .h { font-size:7cqw; letter-spacing:-0.045em; line-height:1; }
#end .s { font-size:3.2cqw; }
#end .hd2 { font-size:1.3cqw; padding:0.6cqw 1.3cqw; border-radius:999px; background:var(--fg); color:var(--bg); letter-spacing:0.08em; text-transform:none; }
`);
scene("s-end", "b36", "b36", `
<div id="end"><div class="h" id="end-h">Subscribe</div><div class="serif s" id="end-s">for more AI, explained <span class="pill">simply</span></div><div class="mono hd2" id="end-hd">@yourchannel</div></div>`, { exitAt: total });
js(`
rise("#end-h", ${T("b36")}, {y:30, d:0.6});
rise("#end-s", ${T("b36") + 0.3}, {y:16});
land("#end-hd", ${T("b36") + 0.7}, {from:0.7});
`);

// ============================================================ WRITE
const subs = subtitleChunks(beats);
ensureEdit(path.join(HERE, "edit"));
write(path.join(HERE, "edit", "index.html"), page({ total, css: CSS, body: BODY, js: JS, chapters, subs, showSubs }));
const fmt = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
write(path.join(HERE, "script.md"), `# ep02 · Jev, explained (and how to use it in RAG) · scene table

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
console.log(`built: ${beats.length} beats, ${subs.length} subtitle chunks, ${fmt(total)} (${total}s), ${track - 10} layers`);
