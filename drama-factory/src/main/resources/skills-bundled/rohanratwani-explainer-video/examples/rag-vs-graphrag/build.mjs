// ep01: RAG vs GraphRAG. Silent pilot (narration as on-screen subtitles).
//   node build.mjs            -> edit/index.html + script.md (scene table)
//   node build.mjs --no-subs  -> same, without the subtitle track
// Facts + sources: brief.md. Running example: A Christmas Carol (public
// domain; it is the sample book in microsoft/graphrag's Get Started guide).

import fs from "node:fs";
import path from "node:path";
import { timeBeats, subtitleChunks, page, esc, rng, write, PX, PY, ensureEdit } from "../../engine/core.mjs";

const HERE = path.dirname(new URL(import.meta.url).pathname).replace(/^\/([A-Za-z]:)/, "$1");
const showSubs = !process.argv.includes("--no-subs");
// --voice <name>: time every beat to its Kokoro clip in vo/<name>/ (durations.json + words.json)
const VOICE = process.argv.includes("--voice") ? process.argv[process.argv.indexOf("--voice") + 1] : null;
const r2 = (n) => Math.round(n * 100) / 100;

// ============================================================ BEATS
// text = narration (spoken later, subtitled now). v = what is on screen.
const beats = [
  { id: "b01", ch: 0, text: "You give an AI all of your company's documents. Then you ask it one simple question.", v: "Chat window lands, files connect, counter to 1,204" },
  { id: "b02", ch: 0, text: "What do our customers complain about the most?", hold: 0.6, v: "Question types into a chat bubble" },
  { id: "b03", ch: 0, text: "And it answers with three random quotes, from three random emails.", hold: 0.5, v: "AI answer: 3 unrelated quotes, '3 of 1,204 files used'" },
  { id: "b04", ch: 0, text: "The model isn't the problem. The way it looks things up is.", hold: 0.5, v: "Chat slides left and dims, claim: the LOOKUP is" },
  { id: "b05", ch: 0, text: "This video is about the two main ways AI looks things up, RAG and GraphRAG, and when each one wins.", hold: 0.8, v: "Title card RAG vs GraphRAG" },

  { id: "b06", ch: 1, text: "Here's the problem. A model like ChatGPT learned from the public internet.", v: "Circle: what the model learned from, source tags" },
  { id: "b07", ch: 1, text: "It has never seen your notes, your support tickets, or your PDFs.", v: "Three private doc cards outside the circle, 'never seen' stamps" },
  { id: "b08", ch: 1, text: "And you can't just paste ten thousand documents into the chat. They won't fit.", hold: 0.5, v: "10,000 docs counter, tiles pour into context window and overflow" },
  { id: "b09", ch: 1, text: "So you need a way to find the right few pages, and hand only those to the model.", v: "Tiles go back, 3 peach tiles slot neatly into the window" },
  { id: "b10", ch: 1, text: "That idea is called RAG. Retrieval augmented generation.", hold: 0.6, v: "R A G letters land, words expand under each" },
  { id: "b11", ch: 1, text: "Retrieve the right pages. Augment your prompt with them. Generate the answer.", hold: 0.6, v: "Each word lights in turn with its verb" },
  { id: "b12", ch: 1, text: "The name comes from a 2020 paper by researchers at Facebook AI.", v: "Paper citation card: Lewis et al. 2020" },

  { id: "b13", ch: 2, text: "To make this real, we'll use one book the whole way through. A Christmas Carol, by Charles Dickens.", v: "Book cover lands" },
  { id: "b14", ch: 2, text: "It's the same book Microsoft uses in its own GraphRAG demo.", v: "Chip: microsoft/graphrag Get Started uses this book" },
  { id: "b15", ch: 2, text: "Step one. Cut the book into small chunks, a few paragraphs each.", hold: 0.6, v: "Step rail 1/4. Book bursts into 24 chunk cards" },
  { id: "b16", ch: 2, text: "Step two. Turn every chunk into a long list of numbers, called an embedding.", hold: 0.4, v: "Real opening chunk (Marley was dead) becomes a vector" },
  { id: "b17", ch: 2, text: "Chunks that mean similar things get similar numbers. So you can place them on a map, and similar chunks land close together.", hold: 0.8, v: "Map: chunks become dots, settle into labelled clusters" },
  { id: "b18", ch: 2, text: "Step three. Your question gets turned into numbers too, and dropped on the same map.", v: "Peach pin drops: What does Scrooge say about Christmas?" },
  { id: "b19", ch: 2, text: "The system grabs the chunks closest to it. Usually the top five or so.", hold: 0.6, v: "Ring expands, 5 nearest dots light, lines draw, 'top 5'" },
  { id: "b20", ch: 2, text: "Step four. Those chunks get pasted into the prompt, right above your question.", hold: 0.4, v: "Map shrinks left, prompt card fills with 5 slips + question" },
  { id: "b21", ch: 2, text: "The model reads them, and writes the answer.", hold: 0.8, v: "Answer card: Bah! said Scrooge, Humbug!" },
  { id: "b22", ch: 2, text: "For a question like this, RAG is great. The answer sits in one chunk, and that chunk is close to the question.", v: "Butter badge: one chunk had the answer" },

  { id: "b23", ch: 3, text: "But RAG only ever sees a handful of chunks. Never the whole book.", hold: 0.5, v: "Wall of 112 chunks, 5 lit, the rest dim" },
  { id: "b24", ch: 3, text: "That breaks two kinds of questions.", v: "Two numbered cards: connect the dots / the big picture" },
  { id: "b25", ch: 3, text: "One. Questions where you have to connect the dots. How is Tiny Tim connected to Scrooge?", hold: 0.4, v: "Map returns, pin drops near the Cratchits" },
  { id: "b26", ch: 3, text: "The book never says it in one place. Tiny Tim is Bob Cratchit's son. And Bob Cratchit works for Scrooge.", hold: 0.4, v: "Two fact cards pinned to far-apart dots" },
  { id: "b27", ch: 3, text: "Those two facts live in different chunks, far apart on the map. Search finds one, and misses the other.", hold: 0.8, v: "Ring catches fact A, fact B stamped MISSED" },
  { id: "b28", ch: 3, text: "Two. Big picture questions. What are the main themes of this book?", hold: 0.4, v: "Wall returns with the themes question" },
  { id: "b29", ch: 3, text: "No single chunk says what the themes are. The answer is spread across the whole book, and five chunks can't see it.", hold: 0.8, v: "Answer sparks appear all over the wall, only 5 tiles lit" },

  { id: "b30", ch: 4, text: "GraphRAG fixes this by doing the reading up front.", hold: 0.5, v: "GraphRAG title: reads everything FIRST" },
  { id: "b31", ch: 4, text: "Microsoft Research published it in April 2024, and open sourced it that July.", v: "Timeline: Apr 2024 paper, Jul 2024 open source" },
  { id: "b32", ch: 4, text: "Instead of only storing chunks, it builds a map of who is connected to what.", hold: 0.4, v: "Split: stored chunks vs a map of connections" },
  { id: "b33", ch: 4, text: "Step one. An AI reads every chunk and pulls out the things in it. People, places, and ideas.", v: "Step rail 1/3. Chunk text, entities highlight and pop out as nodes" },
  { id: "b34", ch: 4, text: "It also writes down how they relate. Bob Cratchit, works for, Scrooge.", hold: 0.6, v: "Labelled edges draw: works for, son of, lives in" },
  { id: "b35", ch: 4, text: "Do that for every chunk, and you get a knowledge graph. Every dot is a thing. Every line is a relationship.", hold: 1.0, v: "Full 18-node graph builds outward from Scrooge" },
  { id: "b36", ch: 4, text: "Now Tiny Tim and Scrooge are just two hops apart, and the path is right there.", hold: 0.8, v: "Everything dims but the path Tiny Tim, Bob, Scrooge. Hops 1, 2" },
  { id: "b37", ch: 4, text: "Step two. It finds clusters, groups of things that are tightly linked.", hold: 0.5, v: "Step 2/3. Nodes recolour by cluster, blobs swell behind" },
  { id: "b38", ch: 4, text: "The Cratchit family. Scrooge's past. The ghosts. It uses an algorithm called Leiden to find them.", hold: 0.5, v: "Cluster labels pop in sync, Leiden chip" },
  { id: "b39", ch: 4, text: "Step three. The AI writes a short summary of every cluster.", hold: 0.8, v: "Step 3/3. Graph slides left, 4 summary cards stack right" },
  { id: "b40", ch: 4, text: "So before you ask a single question, the whole book is already summed up, group by group.", hold: 0.4, v: "Stamp: summed up before any question" },
  { id: "b41", ch: 4, text: "Now ask the big question again. What are the main themes of this book?", v: "Global question bar, 4 summary cards in a row" },
  { id: "b42", ch: 4, text: "GraphRAG asks every cluster summary for its part of the answer. Then it combines those parts into one.", hold: 0.8, v: "Map: partial answers drop out. Reduce: lines converge" },
  { id: "b43", ch: 4, text: "Greed. Redemption. Family. Kindness to the poor. The kind of answer five random chunks could never give you.", hold: 0.8, v: "Final answer card, 4 theme pills land on each word" },
  { id: "b44", ch: 4, text: "That's called global search. For a detail question, GraphRAG uses local search instead. It starts at one dot, and walks the lines around it.", hold: 1.0, v: "Global vs local legend; Tiny Tim pulses, neighbours light" },

  { id: "b45", ch: 5, text: "So does it actually work better? Microsoft tested it on podcast transcripts and news articles, one to two million tokens each.", v: "Dark card: the two test datasets with token and chunk counts" },
  { id: "b46", ch: 5, text: "On big picture questions, an AI judge rated GraphRAG's answers more complete than plain RAG's, 72 to 83 percent of the time.", hold: 1.0, v: "Big serif stat 72-83%" },
  { id: "b47", ch: 5, text: "But all that reading up front isn't free.", v: "Header: reading up front isn't free" },
  { id: "b48", ch: 5, text: "Every chunk goes through an AI, and then every cluster gets summarized. On a big pile of documents, that costs real money and real time.", hold: 0.6, v: "Long GraphRAG receipt prints line by line" },
  { id: "b49", ch: 5, text: "Plain RAG only needs the embeddings, which are cheap and fast.", hold: 0.4, v: "Short RAG receipt: one line" },
  { id: "b50", ch: 5, text: "Here's the whole thing, side by side.", v: "Comparison table lands" },
  { id: "b51", ch: 5, text: "RAG is cheap, and great at finding facts. GraphRAG costs more, and is great at connections and the big picture.", hold: 2.0, v: "Rows fill one by one, winners tinted" },

  { id: "b52", ch: 6, text: "So which one should you use? Look at the questions people actually ask.", v: "Decision root: What do people ask?" },
  { id: "b53", ch: 6, text: "If it's mostly find me the fact, start with plain RAG. Most apps are this.", hold: 0.5, v: "Left branch to Plain RAG" },
  { id: "b54", ch: 6, text: "If it's how are these connected, or what's the big picture, that's where GraphRAG earns its cost.", hold: 0.5, v: "Right branch to GraphRAG" },
  { id: "b55", ch: 6, text: "And there's a middle ground now. Microsoft's LazyGraphRAG skips most of the up front work.", v: "Middle branch to LazyGraphRAG" },
  { id: "b56", ch: 6, text: "Its indexing costs about the same as plain RAG. That's about 0.1 percent of full GraphRAG.", hold: 1.0, v: "0.1% stat inside the LazyGraphRAG card" },

  { id: "b57", ch: 7, text: "Quick recap. RAG finds the closest chunks. Fast, cheap, and great for facts.", v: "Recap card: RAG" },
  { id: "b58", ch: 7, text: "GraphRAG builds a map first. Slower and pricier, but great for connections and the big picture.", hold: 0.4, v: "Recap card: GraphRAG" },
  { id: "b59", ch: 7, text: "Pick by the question, not the hype.", hold: 1.2, v: "Closing line, QUESTION in a peach pill" },
  { id: "b60", ch: 7, text: "Subscribe for more AI, explained simply.", hold: 2.5, v: "End card + handle" },
];
const CHAPTERS = ["", "The problem", "How RAG works", "Where RAG breaks", "How GraphRAG works", "Head to head", "Which one to use", "Recap"];

// what the TTS says: same words, spelled so Kokoro pronounces them right (checked by phonemes)
const say = (t) => t
  .replace(/LazyGraphRAG/g, "Lazy Graph rag").replace(/GraphRAG/g, "Graph rag").replace(/\bRAG\b/g, "rag")
  .replace(/PDFs/g, "PDF files").replace(/Leiden/g, "Liden")
  .replace(/\b2020\b/g, "twenty twenty").replace(/\b2024\b/g, "twenty twenty-four");
write(path.join(HERE, "vo", "lines.json"), JSON.stringify(beats.map((b) => ({ id: b.id, say: say(b.text), text: b.text })), null, 1));
let voice = null;
if (VOICE) {
  const dir = path.join(HERE, "vo", VOICE);
  voice = { durations: JSON.parse(fs.readFileSync(path.join(dir, "durations.json"), "utf8")),
            words: JSON.parse(fs.readFileSync(path.join(dir, "words.json"), "utf8")) };
}
const { total, T, E, F, Wd } = timeBeats(beats, { voice });
const chapters = CHAPTERS.map((label, n) => {
  const bs = beats.filter((b) => b.ch === n);
  return { n, label, s: bs[0].start, e: bs[bs.length - 1].end };
});

// ============================================================ BUILD HELPERS
let CSS = "", BODY = "", JS = "", track = 10;
const css = (s) => { CSS += s + "\n"; };
const js = (s) => { JS += s + "\n"; };

// A set = one scene layer living from beat `from` to beat `to`.
function scene(id, from, to, html, { push = true, exitAt = null } = {}) {
  const s = T(from), e = exitAt ?? E(to), d = r2(e - s);
  BODY += `<div class="set clip" id="${id}" data-start="${s}" data-duration="${d}" data-track-index="${track++}"><div class="stage" id="${id}-st">${html}</div></div>\n`;
  if (push) js(`tl.fromTo("#${id}-st", {scale:1}, {scale:1.025, duration:${d}, ease:"none"}, ${s});`);
  js(`tl.to("#${id}", {opacity:0, duration:0.3, ease:"power1.in"}, ${r2(e - 0.3)});`);
  return { s, e };
}

// HTML line from (x1,y1) to (x2,y2) in px: static rotated wrapper, GSAP scales the <i>.
function hline(x1, y1, x2, y2, id, cls = "") {
  const len = Math.hypot(x2 - x1, y2 - y1), a = (Math.atan2(y2 - y1, x2 - x1) * 180) / Math.PI;
  return `<div class="ln ${cls}" style="left:${r2(x1)}px; top:${r2(y1)}px; width:${r2(len)}px; transform:rotate(${r2(a)}deg);"><i id="${id}"></i></div>`;
}
// SVG line with data-len for draw-on
function sline(x1, y1, x2, y2, id, cls = "") {
  const len = r2(Math.hypot(x2 - x1, y2 - y1));
  return `<line id="${id}" class="${cls}" x1="${r2(x1)}" y1="${r2(y1)}" x2="${r2(x2)}" y2="${r2(y2)}" stroke-dasharray="${len}" stroke-dashoffset="${len}" data-len="${len}"/>`;
}
const docIcon = (c = "") => `<span class="docic ${c}"><i></i><i></i><i></i></span>`;
const check = () => `<span class="chk"></span>`;

// shared component CSS
css(`
.stage { position:absolute; inset:0; transform-origin:50% 50%; }
.ln { position:absolute; height:3px; transform-origin:0 50%; }
.ln i { display:block; width:100%; height:100%; background:var(--accent-strong); border-radius:3px; transform-origin:0 50%; }
.ln.ink i { background:var(--fg); }
.docic { display:inline-flex; flex-direction:column; justify-content:center; gap:0.28cqw; width:2.6cqw; height:3.2cqw; padding:0 0.45cqw;
  background:var(--surface); border:0.12cqw solid var(--fg); border-radius:0.35cqw; }
.docic i { display:block; height:0.18cqw; background:var(--fg); opacity:0.55; border-radius:1px; }
.docic i:nth-child(3) { width:60%; }
.chk { display:inline-block; width:0.7em; height:0.38em; border-left:0.14em solid currentColor; border-bottom:0.14em solid currentColor;
  transform:rotate(-45deg) translate(0.06em,-0.12em); }
.stamp { position:absolute; font-family:"JetBrains Mono"; font-weight:500; text-transform:uppercase; letter-spacing:0.14em;
  border:0.16cqw solid currentColor; border-radius:0.5cqw; padding:0.35cqw 0.8cqw; }
.k { font-size:1.1cqw; color:var(--muted); }
.steps { position:absolute; left:0; right:0; top:3.3cqh; display:flex; justify-content:center; align-items:center; gap:0.7cqw; z-index:40; }
.steps .st { font-family:"JetBrains Mono"; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; font-size:1cqw;
  padding:0.4cqw 0.9cqw; border-radius:999px; border:0.12cqw solid var(--fg); background:var(--surface); color:var(--fg); opacity:0.4; }
.steps .st b { font-weight:500; margin-right:0.5cqw; }
.steps .ar { width:1.6cqw; height:0.12cqw; background:var(--fg); opacity:0.35; }
`);

// step rail: active = peach, done = ink. Persistent across the scenes of a chapter.
function stepRail(id, names, from, to, at) {
  const html = names.map((n, i) => `<div class="st" id="${id}${i}"><b>${i + 1}</b>${n}</div>`).join(`<span class="ar"></span>`);
  BODY += `<div class="steps clip" id="${id}" data-start="${T(from)}" data-duration="${r2(E(to) - T(from))}" data-track-index="${track++}">${html}</div>\n`;
  js(`fade("#${id}", ${T(from)}, {d:0.4});`);
  at.forEach((t, i) => {
    js(`tl.to("#${id}${i}", {opacity:1, backgroundColor:"#f0a87a", duration:0.35, ease:"power2.out"}, ${t});`);
    const next = at[i + 1] ?? E(to) - 0.9;
    js(`tl.to("#${id}${i}", {backgroundColor:"#161513", color:"#f3ecd9", duration:0.3, ease:"power2.out"}, ${r2(next)});`);
  });
}

// ============================================================ 0 · HOOK: chat
css(`
#chat { left:25cqw; top:12.5cqh; width:50cqw; height:71cqh; padding:1.4cqw 1.6cqw; display:flex; flex-direction:column; gap:1.2cqw; transform-origin:0% 50%; }
#chat > * { flex-shrink:0; }
.chat-h { display:flex; align-items:center; gap:0.8cqw; font-size:1.6cqw; padding-bottom:1cqw; border-bottom:0.12cqw solid rgba(22,21,19,0.15); }
.chat-h .dotg { width:0.8cqw; height:0.8cqw; border-radius:50%; background:#6fb36a; }
.chat-h .files { margin-left:auto; font-size:1cqw; background:var(--butter); padding:0.3cqw 0.7cqw; border-radius:999px; }
#chat-src { display:flex; gap:0.6cqw; flex-wrap:wrap; }
.fchip { font-family:"JetBrains Mono"; font-weight:500; font-size:1.05cqw; letter-spacing:0.04em; padding:0.35cqw 0.7cqw; border-radius:0.5cqw;
  border:0.1cqw solid rgba(22,21,19,0.35); background:var(--bg); }
.bub { border-radius:1.2cqw; padding:1.1cqw 1.5cqw; font-size:1.9cqw; line-height:1.35; }
.bub.me { align-self:flex-end; background:var(--fg); color:#f7f2e6; border-bottom-right-radius:0.3cqw; min-height:3.6cqw; max-width:80%; }
.bub.ai { align-self:flex-start; background:var(--bg-deep); border-bottom-left-radius:0.3cqw; width:86%; display:flex; flex-direction:column; gap:0.7cqw; }
.ai-l { font-size:1.45cqw; color:var(--muted); }
.qt { font-size:1.7cqw; background:var(--surface); border-radius:0.6cqw; padding:0.6cqw 0.9cqw; border-left:0.35cqw solid rgba(22,21,19,0.25); }
.srcs { font-size:1.05cqw; color:var(--muted); }
.srcs .hl { background:var(--accent); color:var(--fg); padding:0.15cqw 0.5cqw; border-radius:0.3cqw; }
#claim { position:absolute; left:57cqw; top:31cqh; width:38cqw; }
#claim .c1 { font-size:4.4cqw; line-height:1.02; letter-spacing:-0.03em; }
#claim .c2 { font-size:4.4cqw; line-height:1.02; letter-spacing:-0.03em; margin-top:1.4cqw; }
#claim .pill { padding:0 0.35em; }
`);
scene("s-chat", "b01", "b04", `
<div class="card" id="chat">
  <div class="chat-h"><span class="dotg"></span><span>Company assistant</span><span class="mono files" id="chat-files">0 files connected</span></div>
  <div id="chat-src"><span class="fchip">support-inbox</span><span class="fchip">tickets.csv</span><span class="fchip">reviews.pdf</span><span class="fchip">+1,200 more</span></div>
  <div class="bub me" id="chat-q"><span id="chat-qt"></span></div>
  <div class="bub ai" id="chat-a">
    <div class="ai-l">Here's what customers say:</div>
    <div class="qt">“The invoice came late.”</div>
    <div class="qt">“Love the new logo!”</div>
    <div class="qt">“How do I reset my password?”</div>
    <div class="mono srcs"><span class="hl">3 of 1,204 files</span> used</div>
  </div>
</div>
<div id="claim"><div class="c1" id="claim1">The model isn't<br>the problem.</div><div class="c2" id="claim2">The <span class="serif pill">lookup</span> is.</div></div>`);
js(`
land("#chat", ${T("b01")}, {y:30, from:0.97});
count("#chat-files", 1204, ${T("b01") + 0.5}, 1.8, function(n){ return Math.round(n).toLocaleString("en-US") + " files connected"; });
rise("#chat-src .fchip", ${T("b01") + 0.6}, {st:0.09, y:10});
land("#chat-q", ${T("b02") - 0.15}, {from:0.92, y:12});
type("#chat-qt", "What do our customers complain about the most?", ${T("b02")}, 1.5);
land("#chat-a", ${T("b03")}, {from:0.95, y:16});
rise("#chat-a .ai-l, #chat-a .qt", ${T("b03") + 0.25}, {st:0.32, y:12});
fade("#chat-a .srcs", ${F("b03", 0.8)});
to("#chat", {x:${-21 * PX}, scale:0.78, opacity:0.4, duration:0.75, ease:"power3.inOut"}, ${T("b04")});
rise("#claim1", ${T("b04") + 0.4}, {y:26});
land("#claim2", ${F("b04", 0.55)}, {from:0.85});
`);

// ============================================================ 0 · TITLE
css(`
#ttl { position:absolute; left:0; right:0; top:22cqh; display:flex; flex-direction:column; align-items:center; gap:2.2cqw; }
#ttl .k { font-size:1.1cqw; color:var(--fg); }
#ttl .row { display:flex; align-items:center; gap:2.4cqw; }
#ttl .w { font-size:9.4cqw; letter-spacing:-0.045em; line-height:1; }
#ttl .vs { font-size:4.6cqw; padding:0 0.5em 0.06em; }
#ttl-s { font-size:3.2cqw; color:var(--muted); }
#ttl-mot { position:absolute; left:0; top:0; width:100%; height:100%; }
.mdot { position:absolute; width:1.1cqw; height:1.1cqw; margin:-0.55cqw 0 0 -0.55cqw; border-radius:50%; background:var(--fg); }
.mdot.p { background:var(--accent-strong); }
#ttl-svg line { stroke:var(--fg); stroke-width:3; }
`);
{
  // motif: scattered dots under RAG, connected dots under GraphRAG
  const dotsA = [[25, 74], [28.5, 70.5], [31, 76], [34.5, 72], [27.5, 79], [36, 78.5]];
  const dotsB = [[60, 72], [66, 77], [71, 70], [76.5, 76.5], [64, 81], [72.5, 82]];
  const edgesB = [[0, 1], [1, 2], [2, 3], [1, 4], [4, 5], [3, 5], [1, 5]];
  const P = (p) => [p[0] * PX, p[1] * PY];
  const svg = `<svg id="ttl-svg" style="position:absolute;inset:0" viewBox="0 0 1920 1080" width="1920" height="1080">${
    edgesB.map(([a, b], i) => { const [x1, y1] = P(dotsB[a]), [x2, y2] = P(dotsB[b]); return sline(x1, y1, x2, y2, `te${i}`); }).join("")}</svg>`;
  scene("s-title", "b05", "b05", `
<div id="ttl-mot">${svg}${dotsA.map((p, i) => `<span class="mdot ${i === 2 ? "p" : ""} tda" style="left:${p[0]}cqw; top:${p[1]}cqh"></span>`).join("")}${
    dotsB.map((p, i) => `<span class="mdot ${i === 1 ? "p" : ""} tdb" style="left:${p[0]}cqw; top:${p[1]}cqh"></span>`).join("")}</div>
<div id="ttl"><div class="mono k" id="ttl-k">AI, explained · Episode 01</div>
<div class="row"><span class="w" id="ttl-a">RAG</span><span class="serif pill vs" id="ttl-vs">vs</span><span class="w" id="ttl-b">GraphRAG</span></div>
<div class="serif" id="ttl-s">and when each one wins</div></div>`);
  js(`
fade("#ttl-k", ${T("b05")});
rise("#ttl-a", ${T("b05") + 0.15}, {y:40, d:0.6});
land("#ttl-vs", ${T("b05") + 0.45}, {from:0.4, ease:"back.out(2.2)"});
rise("#ttl-b", ${T("b05") + 0.6}, {y:40, d:0.6});
land(".tda", ${T("b05") + 1.0}, {from:0, st:0.06});
land(".tdb", ${T("b05") + 1.3}, {from:0, st:0.06});
draw("#ttl-svg line", ${T("b05") + 1.6}, {st:0.08, d:0.4});
rise("#ttl-s", ${F("b05", 0.75)}, {y:16});
`);
}

// ============================================================ 1 · what the model knows
css(`
#kn-globe { position:absolute; left:32cqw; top:16cqh; width:36cqw; height:36cqw; border-radius:50%; border:0.16cqw dashed var(--fg);
  background:radial-gradient(circle at 40% 35%, var(--surface), var(--bg-deep)); }
#kn-globe .k { position:absolute; left:0; right:0; top:33%; text-align:center; }
#kn-globe .gt { position:absolute; left:0; right:0; top:40%; text-align:center; font-size:3.4cqw; line-height:1.0; letter-spacing:-0.03em; }
.gtag { position:absolute; font-family:"JetBrains Mono"; font-weight:500; font-size:1.05cqw; letter-spacing:0.06em; padding:0.3cqw 0.6cqw;
  border-radius:999px; background:var(--surface); border:0.1cqw solid rgba(22,21,19,0.4); }
.kc { left:56cqw; width:34cqw; height:14cqh; display:flex; align-items:center; gap:1.4cqw; padding:0 1.6cqw; }
.kc .docic { width:3.4cqw; height:4.2cqw; }
.kc .kt { font-size:2.1cqw; letter-spacing:-0.02em; }
.kc .stamp { right:1.4cqw; top:50%; margin-top:-1.3cqw; color:var(--accent-strong); font-size:1.05cqw; transform:rotate(-4deg); }
.kc .stamp b { display:block; font-weight:500; }
#kc1 { top:20cqh; } #kc2 { top:39cqh; } #kc3 { top:58cqh; }
`);
{
  const tags = [["Wikipedia", 14, 20], ["news sites", 56, 9], ["books", 80, 28], ["forums", 4, 64], ["public code", 62, 76], ["blogs", 28, 86]];
  scene("s-known", "b06", "b07", `
<div id="kn-globe"><div class="mono k">What the model learned from</div><div class="gt">the public<br>internet</div>
${tags.map(([t, x, y]) => `<span class="gtag" style="left:${x}%; top:${y}%">${t}</span>`).join("")}</div>
${[["kc1", "Your notes"], ["kc2", "Support tickets"], ["kc3", "Internal PDFs"]].map(([id, t]) =>
    `<div class="card kc" id="${id}">${docIcon()}<div class="kt">${t}</div><div class="stamp"><b id="${id}s">never seen</b></div></div>`).join("")}`);
  js(`
land("#kn-globe", ${T("b06")}, {from:0.85, d:0.55});
land("#kn-globe .gtag", ${T("b06") + 0.6}, {from:0.6, st:0.12});
to("#kn-globe", {x:${-24 * PX}, duration:0.7, ease:"power3.inOut"}, ${T("b07")});
rise("#kc1, #kc2, #kc3", ${T("b07") + 0.35}, {st:0.42, y:26});
land("#kc1s, #kc2s, #kc3s", ${T("b07") + 0.8}, {from:1.6, st:0.42, ease:"back.out(2)"});
`);
}

// ============================================================ 1 · context window
css(`
#cw-count { position:absolute; left:8cqw; top:14.5cqh; font-size:2.6cqw; letter-spacing:-0.02em; }
#cw-count .mono { font-size:1.05cqw; color:var(--muted); display:block; margin-top:0.3cqw; letter-spacing:0.14em; }
.dt { position:absolute; width:2.4cqw; height:3cqw; background:var(--surface); border:0.1cqw solid var(--fg); border-radius:0.3cqw; }
.dt::before, .dt::after { content:""; position:absolute; left:0.4cqw; right:0.4cqw; height:0.14cqw; background:rgba(22,21,19,0.45); }
.dt::before { top:0.8cqw; } .dt::after { top:1.4cqw; right:0.9cqw; }
#cw-win { position:absolute; left:60cqw; top:28cqh; width:30cqw; height:40cqh; border:0.22cqw solid var(--fg); border-radius:1cqw; background:rgba(250,246,236,0.6); }
#cw-wl { position:absolute; left:60cqw; top:22.5cqh; font-size:1.05cqw; width:31cqw; }
.cw-st { position:absolute; left:64cqw; top:43cqh; font-size:1.7cqw; transform:rotate(-5deg); z-index:20; }
#cw-st1 { background:var(--surface); box-shadow:0 0.3cqw 0 var(--accent-strong); }
#cw-st1 { color:var(--accent-strong); } #cw-st2 { color:var(--fg); background:var(--butter); border-color:var(--fg); }
`);
{
  const cols = 12, rows = 7, tw = 2.4, th = 3.0, gx = 0.7, gy = 0.7; // cqw
  const ox = 8, oy = 24; // cqw / cqh
  const tiles = [];
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
    tiles.push({ x: (ox + c * (tw + gx)) * PX, y: oy * PY + r * (th + gy) * PX });
  }
  // pour targets: 10 per row inside the window, rows continue past its bottom = overflow
  const wx = 60 * PX + 0.6 * PX, wy = 28 * PY + 0.6 * PX, R = rng(7);
  const pour = tiles.map((t, i) => {
    const c = i % 10, r = Math.floor(i / 10);
    return { dx: wx + c * 2.85 * PX - t.x + (R() - 0.5) * 10, dy: wy + r * 3.3 * PX - t.y + (R() - 0.5) * 10, rot: (R() - 0.5) * 24 };
  });
  const pick = [17, 44, 70];
  const neat = pick.map((i, k) => ({ dx: 63.4 * PX + k * 8.3 * PX - tiles[i].x, dy: 44 * PY - tiles[i].y }));
  scene("s-window", "b08", "b09", `
<div id="cw-count"><span id="cw-n">0</span> documents<span class="mono">your company's files</span></div>
<div class="mono" id="cw-wl">Context window: what the model can read at once</div>
<div id="cw-win"></div>
${tiles.map((t, i) => `<div class="dt" id="dt${i}" style="left:${r2(t.x)}px; top:${r2(t.y)}px"></div>`).join("")}
<div class="cw-st" id="cw-st1-w"><span class="stamp" id="cw-st1" style="position:static; display:inline-block">won't fit</span></div>
<div class="cw-st" id="cw-st2-w" style="top:57cqh; left:67cqw"><span class="stamp" id="cw-st2" style="position:static; display:inline-block">just the right 3</span></div>`);
  js(`
rise("#cw-count", ${T("b08")}, {y:14});
count("#cw-n", 10000, ${T("b08") + 0.2}, 1.6);
fade("#cw-wl", ${T("b08") + 0.3});
land("#cw-win", ${T("b08") + 0.3}, {from:0.92});
tl.fromTo(".dt", {opacity:0, scale:0.4}, {opacity:1, scale:1, duration:0.3, ease:"back.out(1.6)", stagger:{each:0.006, from:"start"}}, ${T("b08") + 0.1});
${tiles.map((t, i) => `tl.to("#dt${i}", {x:${r2(pour[i].dx)}, y:${r2(pour[i].dy)}, rotation:${r2(pour[i].rot)}, duration:0.55, ease:"power2.in"}, ${r2(F("b08", 0.5) + i * 0.012)});`).join("\n")}
tl.to("#cw-win", {borderColor:"#e07a45", duration:0.2}, ${r2(F("b08", 0.5) + 0.9)});
tl.to("#cw-win", {x:-8, duration:0.06, yoyo:true, repeat:5, ease:"none"}, ${r2(F("b08", 0.5) + 1.0)});
land("#cw-st1", ${r2(F("b08", 0.5) + 1.1)}, {from:1.8, ease:"back.out(2)"});
${tiles.map((t, i) => pick.includes(i) ? "" : `tl.to("#dt${i}", {x:0, y:0, rotation:0, opacity:0.22, duration:0.5, ease:"power3.inOut"}, ${r2(T("b09") + 0.2 + (i % 12) * 0.01)});`).join("\n")}
${pick.map((i, k) => `tl.to("#dt${i}", {x:${r2(neat[k].dx)}, y:${r2(neat[k].dy)}, rotation:0, scale:2, backgroundColor:"#f0a87a", duration:0.7, ease:"power3.inOut"}, ${r2(F("b09", 0.35) + k * 0.12)});`).join("\n")}
tl.to("#cw-win", {borderColor:"#161513", duration:0.3}, ${T("b09") + 0.2});
exit("#cw-st1", ${T("b09") + 0.2});
land("#cw-st2", ${F("b09", 0.75)}, {from:1.5, ease:"back.out(2)"});
`);
}

// ============================================================ 1 · RAG term
css(`
.tcol { position:absolute; top:19cqh; width:26cqw; display:flex; flex-direction:column; align-items:center; }
#tc0 { left:9cqw; } #tc1 { left:37cqw; } #tc2 { left:65cqw; }
.tcol .L { font-size:15cqw; line-height:1; letter-spacing:-0.04em; }
.tcol .Wd { font-size:3cqw; letter-spacing:-0.02em; margin-top:0.6cqw; }
.tcol .bar { width:60%; height:0.5cqw; background:var(--accent-strong); border-radius:1cqw; margin-top:1.2cqw; transform-origin:0 50%; }
.tcol .vb { font-size:1.9cqw; color:var(--muted); margin-top:1.1cqw; text-align:center; }
#cite { left:22cqw; top:64cqh; width:56cqw; padding:1.3cqw 1.8cqw; display:flex; flex-direction:column; gap:0.5cqw; }
#cite .ct { font-size:1.9cqw; line-height:1.25; }
#cite .cs { font-size:1.05cqw; color:var(--muted); }
`);
{
  const cols = [["R", "Retrieval", "find the right pages"], ["A", "Augmented", "add them to your prompt"], ["G", "Generation", "write the answer"]];
  scene("s-term", "b10", "b12", `
${cols.map(([L, w, v], i) => `<div class="tcol" id="tc${i}"><div class="L" id="tL${i}">${L}</div><div class="Wd" id="tW${i}">${w}</div><div class="bar" id="tB${i}"></div><div class="vb" id="tV${i}">${v}</div></div>`).join("")}
<div class="card" id="cite"><div class="mono k">The paper · 2020</div><div class="ct">Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks</div><div class="mono cs">Lewis et al. · Facebook AI Research</div></div>`);
  js(`
land("#tL0, #tL1, #tL2", ${T("b10")}, {from:0.6, st:0.14, ease:"back.out(1.8)"});
rise("#tW0, #tW1, #tW2", ${F("b10", 0.45)}, {st:0.22, y:18});
${[0, 1, 2].map((i) => `tl.fromTo("#tB${i}", {scaleX:0}, {scaleX:1, duration:0.45, ease:"power3.out"}, ${F("b11", i * 0.33)});
rise("#tV${i}", ${r2(F("b11", i * 0.33) + 0.15)}, {y:12});`).join("\n")}
to("#tc0, #tc1, #tc2", {y:${-8 * PY}, duration:0.6, ease:"power3.inOut"}, ${T("b12")});
land("#cite", ${T("b12") + 0.3}, {y:30, from:0.95});
`);
}

// ============================================================ 2 · step rail (RAG)
stepRail("stR", ["Chunk", "Embed", "Retrieve", "Generate"], "b15", "b22", [T("b15"), T("b16"), T("b18"), T("b20")]);

// ============================================================ 2 · the book
css(`
#book { left:39cqw; top:14cqh; width:22cqw; height:62cqh; padding:1.4cqw; background:#1d2a24; color:#f3ecd9; border-color:var(--fg); }
#book .in { position:absolute; inset:1cqw; border:0.12cqw solid rgba(243,236,217,0.5); border-radius:0.6cqw; display:flex; flex-direction:column;
  align-items:center; justify-content:center; gap:1.4cqw; text-align:center; }
#book .au { font-size:0.9cqw; color:#f0c860; }
#book .bt { font-size:4cqw; line-height:0.98; }
#book .orn { width:4cqw; height:4cqw; border-radius:50%; border:0.14cqw solid #f0c860; position:relative; }
#book .orn::after { content:""; position:absolute; inset:1cqw; border-radius:50%; background:#c4553f; }
#book .yr { font-size:0.85cqw; color:rgba(243,236,217,0.7); }
#bchip { left:64cqw; top:38cqh; padding:1.1cqw 1.5cqw; display:flex; flex-direction:column; gap:0.35cqw; }
#bchip .m { font-size:1.35cqw; letter-spacing:0.06em; text-transform:none; }
#bchip .s { font-size:1.55cqw; color:var(--muted); }
.ck { position:absolute; width:9cqw; height:15cqh; padding:0.7cqw 0.8cqw; display:flex; flex-direction:column; gap:0.55cqw;
  background:var(--surface); border:0.12cqw solid var(--fg); border-radius:0.6cqw; box-shadow:0 0.25cqw 0 var(--fg); }
.ck .mono { font-size:0.85cqw; color:var(--muted); letter-spacing:0.1em; }
.ck i { display:block; height:0.22cqw; background:rgba(22,21,19,0.32); border-radius:1px; }
.ck i:nth-child(odd) { width:82%; }
`);
{
  const cks = [];
  for (let r = 0; r < 3; r++) for (let c = 0; c < 8; c++) cks.push({ x: 9.8 + c * 10.2, y: 20 + r * 18 });
  const bx = 50, by = 45;
  scene("s-book", "b13", "b15", `
<div class="card" id="book"><div class="in"><div class="mono au">Charles Dickens</div><div class="serif bt">A Christmas<br>Carol</div><div class="orn"></div><div class="mono yr">1843 · public domain</div></div></div>
<div class="card" id="bchip"><div class="mono m">microsoft/graphrag</div><div class="s">its Get Started guide uses this book</div></div>
${cks.map((k, i) => `<div class="ck" id="ck${i}" style="left:${r2(k.x)}cqw; top:${k.y}cqh"><span class="mono">chunk ${String(i + 1).padStart(2, "0")}</span><i></i><i></i><i></i><i></i><i></i></div>`).join("")}`);
  js(`
land("#book", ${T("b13")}, {y:40, from:0.9, d:0.55});
rise("#book .in > *", ${T("b13") + 0.35}, {st:0.12, y:12});
land("#bchip", ${T("b14")}, {from:0.9, y:16});
to("#book", {scale:0.5, opacity:0, duration:0.45, ease:"power3.in"}, ${T("b15") + 0.1});
exit("#bchip", ${T("b15") + 0.1});
${cks.map((k, i) => `tl.fromTo("#ck${i}", {opacity:0, scale:0.3, x:${r2((bx - 4.5 - k.x) * PX)}, y:${r2((by - 7.5 - k.y) * PY)}}, {opacity:1, scale:1, x:0, y:0, duration:0.6, ease:"power3.out"}, ${r2(T("b15") + 0.45 + i * 0.03)});`).join("\n")}
`);
}

// ============================================================ 2 · embedding
css(`
#emb-c { left:7cqw; top:22cqh; width:34cqw; height:46cqh; padding:1.6cqw; display:flex; flex-direction:column; gap:1cqw; }
#emb-c .tx { font-size:1.75cqw; line-height:1.4; }
#emb-arrow { position:absolute; left:43cqw; top:44cqh; width:8cqw; }
#emb-arrow .ln { position:relative; width:100%; }
#emb-arrow .hd { position:absolute; right:-0.2cqw; top:-0.62cqw; width:1.3cqw; height:1.3cqw; border-top:3px solid var(--accent-strong); border-right:3px solid var(--accent-strong); transform:rotate(45deg); }
#emb-al { position:absolute; left:41cqw; top:48cqh; width:12cqw; text-align:center; font-size:0.95cqw; color:var(--muted); }
#emb-v { left:53cqw; top:22cqh; width:40cqw; height:46cqh; padding:1.6cqw; display:flex; flex-direction:column; gap:1.2cqw; }
#emb-v .nums { display:grid; grid-template-columns:repeat(4, 1fr); gap:0.9cqw 1cqw; font-family:"JetBrains Mono"; font-weight:500; font-size:1.55cqw; }
#emb-v .nums span { background:var(--bg); border-radius:0.4cqw; padding:0.5cqw 0; text-align:center; }
#emb-v .more { font-size:1.5cqw; color:var(--muted); }
`);
{
  const R = rng(3);
  const nums = Array.from({ length: 16 }, () => { const v = (R() * 2 - 1); return (v < 0 ? "-" : "") + Math.abs(v).toFixed(2); });
  scene("s-embed", "b16", "b16", `
<div class="card" id="emb-c"><div class="mono k">chunk 01</div><div class="tx">Marley was dead: to begin with. There is no doubt whatever about that. The register of his burial was signed by the clergyman, the clerk, the undertaker, and the chief mourner. Scrooge signed it.</div></div>
<div id="emb-arrow"><div class="ln" style="position:relative"><i id="emb-ai"></i></div><span class="hd" id="emb-hd"></span></div>
<div class="mono" id="emb-al">embedding model</div>
<div class="card" id="emb-v"><div class="mono k">its embedding</div><div class="nums">${nums.map((n) => `<span>${n}</span>`).join("")}</div><div class="more">…and hundreds more numbers</div></div>`);
  js(`
land("#emb-c", ${T("b16")}, {from:0.94, y:20});
tl.fromTo("#emb-ai", {scaleX:0}, {scaleX:1, duration:0.45, ease:"power2.out"}, ${F("b16", 0.35)});
fade("#emb-hd, #emb-al", ${r2(F("b16", 0.35) + 0.35)});
land("#emb-v", ${F("b16", 0.45)}, {from:0.94, y:20});
fade("#emb-v .nums span", ${r2(F("b16", 0.45) + 0.3)}, {st:0.05, d:0.2});
fade("#emb-v .more", ${F("b16", 0.9)});
`);
}

// ============================================================ embedding MAP (used twice)
const MAPF = { l: 14, t: 13, w: 72, h: 68 }; // cqw, cqh, cqw, cqh
const MW = MAPF.w * PX, MH = MAPF.h * PY;
const CLUST = [
  { id: "office", label: "Scrooge's office", cx: 22, cy: 30, n: 9 },
  { id: "ghosts", label: "the ghosts", cx: 77, cy: 23, n: 8 },
  { id: "cratchit", label: "the Cratchits", cx: 78, cy: 72, n: 8 },
  { id: "party", label: "Fezziwig's party", cx: 22, cy: 75, n: 7 },
  { id: "morning", label: "Christmas morning", cx: 50, cy: 49, n: 7 },
];
const MAPDOTS = (() => {
  const R = rng(42), pts = [];
  for (const c of CLUST) {
    let k = 0, guard = 0;
    while (k < c.n && guard++ < 2000) {
      const a = R() * Math.PI * 2, d = Math.sqrt(R());
      const x = c.cx + Math.cos(a) * d * 9, y = c.cy + Math.sin(a) * d * 12;
      const px = (x / 100) * MW, py = (y / 100) * MH;
      if (pts.some((p) => Math.hypot(p.px - px, p.py - py) < 44)) continue;
      pts.push({ x, y, px, py, cl: c.id }); k++;
    }
  }
  return pts;
})();
css(`
.mapf { left:${MAPF.l}cqw; top:${MAPF.t}cqh; width:${MAPF.w}cqw; height:${MAPF.h}cqh; overflow:visible; transform-origin:0% 50%;
  background:
    linear-gradient(rgba(22,21,19,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(22,21,19,0.06) 1px, transparent 1px), var(--surface);
  background-size:3cqw 3cqw; }
.md { position:absolute; width:1.15cqw; height:1.15cqw; margin:-0.575cqw 0 0 -0.575cqw; border-radius:50%; background:var(--fg); border:0.12cqw solid var(--fg); }
.mlab { position:absolute; font-size:1.05cqw; color:var(--fg); opacity:0.6; white-space:nowrap; }
.pin { position:absolute; width:1.9cqw; height:1.9cqw; margin:-0.95cqw 0 0 -0.95cqw; border-radius:50%; background:var(--accent-strong);
  border:0.22cqw solid var(--fg); box-shadow:0 0 0 0.5cqw rgba(224,122,69,0.25); z-index:3; }
.ring { position:absolute; border-radius:50%; border:0.16cqw dashed var(--accent-strong); background:rgba(240,168,122,0.14); }
.mq { position:absolute; padding:0.8cqw 1.1cqw; font-size:1.55cqw; max-width:22cqw; line-height:1.25; z-index:4; }
.mq .mono { display:block; font-size:0.9cqw; color:var(--muted); margin-bottom:0.25cqw; }
.mbadge { position:absolute; font-size:1.15cqw; padding:0.35cqw 0.8cqw; border-radius:999px; background:var(--fg); color:var(--bg); z-index:4; }
`);
function mapHtml(p) {
  return `<div class="card mapf" id="${p}">
${CLUST.map((c) => `<span class="mono mlab ${p}-lab" style="left:${c.cx - 6}%; top:${c.cy - 15.5}%">${c.label}</span>`).join("")}
${MAPDOTS.map((d, i) => `<span class="md ${p}-d" id="${p}-d${i}" style="left:${r2(d.x)}%; top:${r2(d.y)}%"></span>`).join("")}
<!--extra-->
</div>`;
}
const nearest = (x, y, k) => MAPDOTS.map((d, i) => ({ i, dist: Math.hypot(d.px - (x / 100) * MW, d.py - (y / 100) * MH) }))
  .sort((a, b) => a.dist - b.dist).slice(0, k);

// ============================================================ 2 · map: retrieve + generate
css(`
#pr { left:47cqw; top:13cqh; width:48cqw; height:51cqh; padding:1.3cqw 1.5cqw; display:flex; flex-direction:column; gap:0.7cqw; }
#pr .pl { font-size:1.45cqw; color:var(--muted); }
.slip { font-size:1.5cqw; padding:0.55cqw 0.9cqw; border-left:0.35cqw solid var(--accent-strong); background:var(--bg); border-radius:0.35cqw; min-height:2.3cqw; }
.slip i { display:inline-block; height:0.25cqw; width:70%; background:rgba(22,21,19,0.25); vertical-align:middle; }
#pr .q { font-size:1.7cqw; margin-top:0.5cqw; }
#ans { left:47cqw; top:67cqh; width:48cqw; height:14cqh; padding:1cqw 1.5cqw; display:flex; flex-direction:column; justify-content:center; gap:0.4cqw;
  background:var(--fg); color:var(--bg); }
#ans .mono { font-size:0.95cqw; color:var(--butter); }
#ans .t { font-size:1.85cqw; }
#ok { position:absolute; left:6cqw; top:71cqh; display:flex; align-items:center; gap:0.8cqw; background:var(--butter); border:0.14cqw solid var(--fg);
  border-radius:999px; padding:0.6cqw 1.3cqw; font-size:1.35cqw; box-shadow:0 0.3cqw 0 var(--fg); }
`);
{
  const pin = { x: 31, y: 40 };
  const nn = nearest(pin.x, pin.y, 5);
  const rad = nn[4].dist + 26;
  const ppx = (pin.x / 100) * MW, ppy = (pin.y / 100) * MH;
  const extra = `
<div class="ring" id="m1-ring" style="left:${r2(ppx - rad)}px; top:${r2(ppy - rad)}px; width:${r2(rad * 2)}px; height:${r2(rad * 2)}px"></div>
${nn.map((n, k) => hline(ppx, ppy, MAPDOTS[n.i].px, MAPDOTS[n.i].py, `m1-l${k}`)).join("")}
<span class="pin" id="m1-pin" style="left:${pin.x}%; top:${pin.y}%"></span>
<div class="card mq" id="m1-q" style="left:${pin.x + 2.5}%; top:${pin.y + 3}%"><span class="mono">your question</span>What does Scrooge say about Christmas?</div>
<span class="mono mbadge" id="m1-top" style="left:${r2(((ppx + rad * 0.62) / MW) * 100)}%; top:${r2(((ppy - rad - 34) / MH) * 100)}%">top 5</span>`;
  scene("s-map1", "b17", "b22", mapHtml("m1").replace("<!--extra-->", extra) + `
<div class="card" id="pr"><div class="mono k">the prompt</div><div class="pl">Use these notes to answer:</div>
<div class="slip">“Bah!” said Scrooge, “Humbug!”</div><div class="slip">“Out upon merry Christmas!”</div><div class="slip"><i></i></div><div class="slip"><i></i></div><div class="slip"><i></i></div>
<div class="q">Question: What does Scrooge say about Christmas?</div></div>
<div class="card" id="ans"><div class="mono">answer</div><div class="t">He calls it humbug. “Bah!” said Scrooge, “Humbug!”</div></div>
<div id="ok">${check()}<span>One chunk had the answer</span></div>`);
  js(`
land("#m1", ${T("b17")}, {from:0.95, d:0.5});
tl.fromTo(".m1-d", {opacity:0, scale:0}, {opacity:1, scale:1, duration:0.35, ease:"back.out(2)", stagger:{each:0.025, from:"random"}}, ${T("b17") + 0.4});
fade(".m1-lab", ${F("b17", 0.62)}, {st:0.15});
tl.fromTo("#m1-pin", {opacity:0, y:-80}, {opacity:1, y:0, duration:0.55, ease:"bounce.out"}, ${T("b18") + 0.1});
land("#m1-q", ${F("b18", 0.35)}, {from:0.9, y:10});
tl.fromTo("#m1-ring", {opacity:0, scale:0}, {opacity:1, scale:1, duration:0.6, ease:"power3.out"}, ${T("b19") + 0.1});
${nn.map((n, k) => `tl.fromTo("#m1-l${k}", {scaleX:0}, {scaleX:1, duration:0.35, ease:"power2.out"}, ${r2(F("b19", 0.35) + k * 0.1)});
tl.to("#m1-d${n.i}", {backgroundColor:"#f0a87a", scale:1.5, duration:0.3, ease:"back.out(2)"}, ${r2(F("b19", 0.35) + k * 0.1 + 0.25)});`).join("\n")}
land("#m1-top", ${F("b19", 0.85)}, {from:0.6});
exit("#m1-q", ${T("b20")});
to("#m1", {x:${(3 - MAPF.l) * PX}, scale:0.6, duration:0.8, ease:"power3.inOut"}, ${T("b20")});
land("#pr", ${T("b20") + 0.5}, {from:0.95, y:20});
rise("#pr .pl, #pr .slip, #pr .q", ${T("b20") + 0.85}, {st:0.14, y:10});
land("#ans", ${T("b21") + 0.2}, {from:0.92, y:16});
land("#ok", ${T("b22") + 0.2}, {from:0.7, ease:"back.out(2)"});
`);
}

// ============================================================ chunk WALL (used twice)
const WALL = { cols: 16, rows: 7, l: 11.9, t: 21, tw: 4.2, th: 4.6, gx: 0.6, gy: 1.0 };
css(`
.wt { position:absolute; width:${WALL.tw}cqw; height:${WALL.th}cqh; background:var(--surface); border:0.1cqw solid var(--fg); border-radius:0.35cqw; }
.wt::before, .wt::after { content:""; position:absolute; left:0.5cqw; height:0.16cqw; background:rgba(22,21,19,0.35); }
.wt::before { top:1.3cqh; right:0.5cqw; } .wt::after { top:2.5cqh; right:1.4cqw; }
.wspark { position:absolute; right:0.35cqw; bottom:0.45cqh; width:1cqw; height:1cqw; border-radius:50%; }
.whead { position:absolute; left:${WALL.l}cqw; top:11.5cqh; font-size:2.8cqw; letter-spacing:-0.02em; }
.whead .mono { font-size:1.05cqw; color:var(--muted); margin-left:1cqw; letter-spacing:0.14em; }
`);
function wallHtml(p, sparks = []) {
  let h = "";
  for (let r = 0; r < WALL.rows; r++) for (let c = 0; c < WALL.cols; c++) {
    const i = r * WALL.cols + c;
    const sp = sparks.find((s) => s.i === i);
    h += `<div class="wt ${p}-t" id="${p}-t${i}" style="left:${r2(WALL.l + c * (WALL.tw + WALL.gx))}cqw; top:${r2(WALL.t + r * (WALL.th + WALL.gy))}cqh">${sp ? `<span class="wspark ${p}-sp" style="background:${sp.c}"></span>` : ""}</div>`;
  }
  return h;
}
const TOP5 = [21, 22, 58, 75, 99];

// ============================================================ 3 · wall: only 5
css(`
.qcard { position:absolute; top:66cqh; width:28cqw; height:14cqh; display:flex; align-items:center; gap:1.4cqw; padding:0 1.6cqw; }
.qcard .n { width:3.6cqw; height:3.6cqw; border-radius:50%; background:var(--fg); color:var(--bg); display:flex; align-items:center; justify-content:center; font-size:1.8cqw; }
.qcard .t { font-size:2.2cqw; letter-spacing:-0.02em; }
#qc1 { left:20cqw; } #qc2 { left:52cqw; }
`);
scene("s-wall1", "b23", "b24", `
<div class="whead" id="w1-h">The model reads 5 chunks.<span class="mono" id="w1-hs">the rest of the book stays unread</span></div>
${wallHtml("w1")}
<div class="card qcard" id="qc1"><span class="n">1</span><span class="t">Connect the dots</span></div>
<div class="card qcard" id="qc2"><span class="n">2</span><span class="t">The big picture</span></div>`);
js(`
tl.fromTo(".w1-t", {opacity:0, scale:0.5}, {opacity:1, scale:1, duration:0.3, ease:"back.out(1.6)", stagger:{each:0.004, grid:[${WALL.rows}, ${WALL.cols}], from:"center"}}, ${T("b23")});
rise("#w1-h", ${F("b23", 0.3)}, {y:14, st:0});
tl.to("${Array.from({ length: WALL.rows * WALL.cols }, (_, i) => i).filter((i) => !TOP5.includes(i)).map((i) => `#w1-t${i}`).join(", ")}", {opacity:0.22, duration:0.5, ease:"power1.inOut"}, ${F("b23", 0.45)});
tl.to("${TOP5.map((i) => `#w1-t${i}`).join(", ")}", {backgroundColor:"#f0a87a", scale:1.12, duration:0.35, ease:"back.out(2)", stagger:0.08}, ${F("b23", 0.45)});
fade("#w1-hs", ${F("b23", 0.8)});
rise("#qc1, #qc2", ${T("b24") + 0.1}, {st:0.3, y:26});
`);

// ============================================================ 3 · map: connect the dots
{
  const pin = { x: 64, y: 60 };
  const fA = { x: 71, y: 67 }, fB = { x: 20, y: 30 };
  const ppx = (pin.x / 100) * MW, ppy = (pin.y / 100) * MH;
  const ax = (fA.x / 100) * MW, ay = (fA.y / 100) * MH, bx = (fB.x / 100) * MW, by = (fB.y / 100) * MH;
  const rad = Math.hypot(ax - ppx, ay - ppy) + 46;
  css(`
.fdot { position:absolute; width:1.5cqw; height:1.5cqw; margin:-0.75cqw 0 0 -0.75cqw; border-radius:50%; background:var(--butter); border:0.18cqw solid var(--fg); z-index:3; }
.fact { position:absolute; padding:0.8cqw 1.1cqw; font-size:1.55cqw; line-height:1.25; z-index:4; max-width:20cqw; }
.fact .mono { display:block; font-size:0.9cqw; color:var(--muted); margin-bottom:0.2cqw; }
.m2mw { position:absolute; right:-1.6cqw; top:-1.6cqw; z-index:5; transform:rotate(-6deg); }
#m2-miss { position:static; display:inline-block; color:var(--accent-strong); font-size:1.2cqw; background:var(--surface); }
#m2-q2 { position:absolute; left:3cqw; top:3cqh; z-index:4; padding:0.8cqw 1.2cqw; font-size:1.8cqw; }
#m2-q2 .mono { display:block; font-size:0.9cqw; color:var(--muted); margin-bottom:0.2cqw; }
#m2-half { position:absolute; z-index:5; font-size:1.2cqw; padding:0.4cqw 0.9cqw; border-radius:999px; background:var(--fg); color:var(--bg); }
`);
  const extra = `
<div class="ring" id="m2-ring" style="left:${r2(ppx - rad)}px; top:${r2(ppy - rad)}px; width:${r2(rad * 2)}px; height:${r2(rad * 2)}px"></div>
${hline(ppx, ppy, ax, ay, "m2-la")}
<span class="fdot" id="m2-fa" style="left:${fA.x}%; top:${fA.y}%"></span>
<span class="fdot" id="m2-fb" style="left:${fB.x}%; top:${fB.y}%"></span>
<span class="pin" id="m2-pin" style="left:${pin.x}%; top:${pin.y}%"></span>
<div class="card" id="m2-q2"><span class="mono">your question</span>How is Tiny Tim connected to Scrooge?</div>
<div class="card fact" id="m2-ca" style="left:${fA.x + 2}%; top:${fA.y + 4}%"><span class="mono">chunk 52</span>Tiny Tim is Bob Cratchit's son.</div>
<div class="card fact" id="m2-cb" style="left:3%; top:45%; max-width:none; white-space:nowrap"><span class="mono">chunk 08</span>Bob Cratchit works for Scrooge.<span class="m2mw"><span class="stamp" id="m2-miss">missed</span></span></div>
<span class="mono" id="m2-half" style="left:33%; top:80%">only half the story</span>`;
  scene("s-map2", "b25", "b27", mapHtml("m2").replace("<!--extra-->", extra));
  js(`
land("#m2", ${T("b25")}, {from:0.95, d:0.5});
fade(".m2-d", ${T("b25") + 0.3}, {d:0.5});
fade(".m2-lab", ${T("b25") + 0.5});
land("#m2-q2", ${F("b25", 0.45)}, {from:0.9, y:10});
tl.fromTo("#m2-pin", {opacity:0, y:-80}, {opacity:1, y:0, duration:0.55, ease:"bounce.out"}, ${F("b25", 0.55)});
land("#m2-fa", ${F("b26", 0.35)}, {from:0, ease:"back.out(2.4)"});
land("#m2-ca", ${r2(F("b26", 0.35) + 0.15)}, {from:0.9, y:10});
land("#m2-fb", ${F("b26", 0.7)}, {from:0, ease:"back.out(2.4)"});
land("#m2-cb", ${r2(F("b26", 0.7) + 0.15)}, {from:0.9, y:10});
tl.fromTo("#m2-ring", {opacity:0, scale:0}, {opacity:1, scale:1, duration:0.6, ease:"power3.out"}, ${F("b27", 0.3)});
tl.fromTo("#m2-la", {scaleX:0}, {scaleX:1, duration:0.4, ease:"power2.out"}, ${F("b27", 0.45)});
tl.to("#m2-fa", {backgroundColor:"#f0a87a", duration:0.3}, ${F("b27", 0.5)});
tl.to("#m2-fb", {opacity:0.35, duration:0.4}, ${F("b27", 0.7)});
land("#m2-miss", ${F("b27", 0.72)}, {from:1.8, ease:"back.out(2)"});
land("#m2-half", ${F("b27", 0.85)}, {from:0.7});
`);
}

// ============================================================ 3 · wall: big picture
{
  const R = rng(11), cols = ["#e07a45", "#d9a92c", "#6f9e62", "#8a7bd6"], sparks = [];
  const n = WALL.rows * WALL.cols;
  for (let i = 0; i < n; i++) if (R() < 0.42) sparks.push({ i, c: cols[Math.floor(R() * 4)] });
  css(`#w2-q { position:absolute; left:${WALL.l}cqw; top:9.5cqh; padding:0.7cqw 1.2cqw; font-size:2cqw; z-index:3; }
#w2-q .mono { font-size:0.9cqw; color:var(--muted); display:block; margin-bottom:0.2cqw; }
#w2-note { position:absolute; left:${WALL.l}cqw; top:65cqh; font-size:2.3cqw; letter-spacing:-0.02em; }
#w2-note .mono { display:block; font-size:1.05cqw; color:var(--muted); margin-top:0.4cqw; letter-spacing:0.14em; }`);
  scene("s-wall2", "b28", "b29", `
<div class="card" id="w2-q"><span class="mono">your question</span>What are the main themes of this book?</div>
${wallHtml("w2", sparks)}
<div id="w2-note"><span id="w2-n1">Pieces of the answer are everywhere.</span><span class="mono" id="w2-n2">the top 5 chunks see almost none of them</span></div>`);
  js(`
land("#w2-q", ${T("b28") + 0.1}, {from:0.92, y:12});
tl.fromTo(".w2-t", {opacity:0, scale:0.5}, {opacity:1, scale:1, duration:0.3, ease:"back.out(1.6)", stagger:{each:0.004, grid:[${WALL.rows}, ${WALL.cols}], from:"center"}}, ${F("b28", 0.4)});
tl.fromTo(".w2-sp", {opacity:0, scale:0}, {opacity:1, scale:1, duration:0.3, ease:"back.out(2)", stagger:{each:0.025, from:"random"}}, ${F("b29", 0.12)});
rise("#w2-n1", ${F("b29", 0.35)}, {y:14});
tl.to("${Array.from({ length: n }, (_, i) => i).filter((i) => !TOP5.includes(i)).map((i) => `#w2-t${i}`).join(", ")}", {opacity:0.25, duration:0.5, ease:"power1.inOut"}, ${F("b29", 0.7)});
tl.to("${TOP5.map((i) => `#w2-t${i}`).join(", ")}", {backgroundColor:"#f0a87a", scale:1.12, duration:0.35, ease:"back.out(2)", stagger:0.08}, ${F("b29", 0.7)});
fade("#w2-n2", ${F("b29", 0.85)});
`);
}

// ============================================================ 4 · GraphRAG intro
css(`
#gi-t { position:absolute; left:0; right:0; top:20cqh; text-align:center; font-size:9cqw; letter-spacing:-0.045em; line-height:1; }
#gi-s { position:absolute; left:0; right:0; top:40cqh; text-align:center; font-size:3.6cqw; }
#gi-s .pill { font-size:1em; padding:0 0.4em 0.05em; }
#gi-tl { position:absolute; left:28cqw; width:44cqw; top:66cqh; height:0.2cqw; background:var(--fg); transform-origin:0 50%; }
.gi-n { position:absolute; top:66cqh; width:1.4cqw; height:1.4cqw; margin:-0.6cqw 0 0 -0.7cqw; border-radius:50%; background:var(--accent-strong); border:0.18cqw solid var(--fg); }
.gi-l { position:absolute; top:69cqh; width:24cqw; margin-left:-12cqw; text-align:center; font-size:1.8cqw; }
.gi-l .mono { display:block; font-size:1.1cqw; color:var(--muted); margin-bottom:0.3cqw; }
#gi-ms { position:absolute; left:0; right:0; top:59cqh; text-align:center; font-size:1.1cqw; color:var(--muted); }
.gi-box { top:16cqh; width:34cqw; height:60cqh; }
#gi-b1 { left:11cqw; } #gi-b2 { left:55cqw; }
.gi-box .mono { position:absolute; left:1.4cqw; top:1.2cqw; font-size:1.1cqw; color:var(--muted); }
.gi-box .bt { position:absolute; left:1.4cqw; bottom:1.4cqw; font-size:2.6cqw; letter-spacing:-0.02em; }
.gi-ck { position:absolute; width:7cqw; height:9cqh; background:var(--bg); border:0.1cqw solid var(--fg); border-radius:0.4cqw; }
.gi-g { position:absolute; width:1.6cqw; height:1.6cqw; margin:-0.8cqw 0 0 -0.8cqw; border-radius:50%; background:var(--accent); border:0.16cqw solid var(--fg); }
#gi-svg line { stroke:var(--fg); stroke-width:3; }
`);
{
  const box2 = { l: 55 * PX, t: 16 * PY };
  const gn = [[0.2, 0.3], [0.48, 0.22], [0.75, 0.35], [0.35, 0.58], [0.66, 0.62], [0.5, 0.42]];
  const ge = [[0, 1], [1, 2], [0, 3], [3, 5], [5, 1], [5, 4], [2, 4], [3, 4]];
  const bw = 34 * PX, bh = 60 * PY;
  const P = (p) => [box2.l + p[0] * bw, box2.t + p[1] * bh];
  scene("s-gintro", "b30", "b32", `
<div id="gi-t">GraphRAG</div>
<div id="gi-s">reads everything <span class="serif pill" id="gi-first">first</span></div>
<div class="mono" id="gi-ms">Microsoft Research</div>
<div id="gi-tl"></div>
<span class="gi-n" id="gi-n1" style="left:34cqw"></span><span class="gi-n" id="gi-n2" style="left:66cqw"></span>
<div class="gi-l" id="gi-l1" style="left:34cqw"><span class="mono">April 2024</span>the paper</div>
<div class="gi-l" id="gi-l2" style="left:66cqw"><span class="mono">July 2024</span>open source on GitHub</div>
<div class="card gi-box" id="gi-b1"><span class="mono">plain RAG stores</span>${[0, 1, 2, 3, 4, 5].map((i) => `<span class="gi-ck gi-cks" style="left:${3 + (i % 3) * 10}cqw; top:${12 + Math.floor(i / 3) * 14}cqh"></span>`).join("")}<span class="bt">chunks</span></div>
<div class="card gi-box" id="gi-b2"><span class="mono">GraphRAG builds</span><span class="bt">a map of connections</span></div>
<svg id="gi-svg" style="position:absolute;inset:0;pointer-events:none" viewBox="0 0 1920 1080" width="1920" height="1080">${ge.map(([a, b], i) => { const [x1, y1] = P(gn[a]), [x2, y2] = P(gn[b]); return sline(x1, y1, x2, y2, `gie${i}`); }).join("")}</svg>
${gn.map((p, i) => { const [x, y] = P(p); return `<span class="gi-g" id="gin${i}" style="left:${r2(x)}px; top:${r2(y)}px"></span>`; }).join("")}`);
  js(`
rise("#gi-t", ${T("b30")}, {y:40, d:0.6});
rise("#gi-s", ${T("b30") + 0.4}, {y:20});
land("#gi-first", ${F("b30", 0.7)}, {from:0.5, ease:"back.out(2.2)"});
tl.fromTo("#gi-tl", {scaleX:0}, {scaleX:1, duration:0.8, ease:"power3.inOut"}, ${T("b31")});
fade("#gi-ms", ${T("b31") + 0.2});
land("#gi-n1", ${F("b31", 0.15)}, {from:0, ease:"back.out(2.4)"}); rise("#gi-l1", ${F("b31", 0.2)}, {y:10});
land("#gi-n2", ${F("b31", 0.6)}, {from:0, ease:"back.out(2.4)"}); rise("#gi-l2", ${F("b31", 0.65)}, {y:10});
exit("#gi-t, #gi-s, #gi-ms, #gi-tl, #gi-n1, #gi-n2, #gi-l1, #gi-l2", ${T("b32")}, {y:-30});
land("#gi-b1", ${T("b32") + 0.35}, {from:0.95, y:20});
land(".gi-cks", ${T("b32") + 0.6}, {from:0.5, st:0.06});
land("#gi-b2", ${F("b32", 0.4)}, {from:0.95, y:20});
land(".gi-g", ${r2(F("b32", 0.4) + 0.3)}, {from:0, st:0.08, ease:"back.out(2.2)"});
draw("#gi-svg line", ${r2(F("b32", 0.4) + 0.6)}, {st:0.07, d:0.35});
`);
}

// ============================================================ 4 · step rail (GraphRAG)
stepRail("stG", ["Extract", "Cluster", "Summarize"], "b33", "b40", [T("b33"), T("b37"), T("b39")]);

// ============================================================ 4 · extract
css(`
#ex-c { left:6cqw; top:22cqh; width:40cqw; height:40cqh; padding:1.8cqw; display:flex; flex-direction:column; gap:1.2cqw; }
#ex-c .tx { font-size:2.15cqw; line-height:1.45; letter-spacing:-0.01em; }
.ent { border-radius:0.35cqw; padding:0 0.12em; margin:0 -0.12em; }
#ex-leg { display:flex; gap:0.8cqw; margin-top:auto; }
#ex-leg span { font-size:1.05cqw; padding:0.3cqw 0.7cqw; border-radius:999px; border:0.1cqw solid var(--fg); }
.xn { position:absolute; width:0; height:0; z-index:3; }
.xn span { position:absolute; left:0; top:0; transform:translate(-50%,-50%); white-space:nowrap; font-size:1.5cqw; padding:0.5cqw 1.1cqw;
  border-radius:999px; border:0.14cqw solid var(--fg); box-shadow:0 0.25cqw 0 var(--fg); }
#ex-svg line { stroke:var(--fg); stroke-width:3; }
.xl { position:absolute; width:0; height:0; z-index:4; }
.xl span { position:absolute; left:0; top:0; transform:translate(-50%,-50%); white-space:nowrap; font-size:1.05cqw; padding:0.25cqw 0.6cqw;
  background:var(--fg); color:var(--bg); border-radius:0.35cqw; }
`);
{
  const N = { scr: [67, 26, "Scrooge", "#f0a87a"], bob: [83, 44, "Bob Cratchit", "#f0a87a"], tim: [64, 63, "Tiny Tim", "#f0a87a"], cam: [86, 68, "Camden Town", "#a9c79b"] };
  const P = (k) => [N[k][0] * PX, N[k][1] * PY];
  const ED = [["bob", "scr", "works for"], ["tim", "bob", "son of"], ["bob", "cam", "lives in"]];
  scene("s-extract", "b33", "b34", `
<div class="card" id="ex-c"><div class="mono k">chunk 37</div>
<div class="tx"><span class="ent" id="ent-bob">Bob Cratchit</span>, <span class="ent" id="ent-scr">Scrooge</span>'s clerk, ran home to <span class="ent" id="ent-cam">Camden Town</span> to see his family and his little son, <span class="ent" id="ent-tim">Tiny Tim</span>.</div>
<div id="ex-leg"><span class="mono" style="background:#f0a87a">person</span><span class="mono" style="background:#a9c79b">place</span></div></div>
<svg id="ex-svg" style="position:absolute;inset:0" viewBox="0 0 1920 1080" width="1920" height="1080">${ED.map(([a, b], i) => { const [x1, y1] = P(a), [x2, y2] = P(b); return sline(x1, y1, x2, y2, `exe${i}`); }).join("")}</svg>
${Object.entries(N).map(([k, [x, y, t, c]]) => `<div class="xn" id="xn-${k}" style="left:${x}cqw; top:${y}cqh"><span style="background:${c}">${t}</span></div>`).join("")}
${ED.map(([a, b, t], i) => { const [x1, y1] = P(a), [x2, y2] = P(b); return `<div class="xl" id="xl${i}" style="left:${r2((x1 + x2) / 2)}px; top:${r2((y1 + y2) / 2)}px"><span class="mono">${t}</span></div>`; }).join("")}`);
  js(`
land("#ex-c", ${T("b33")}, {from:0.95, y:20});
${["bob", "scr", "cam", "tim"].map((k, i) => `tl.fromTo("#ent-${k}", {backgroundColor:"rgba(240,168,122,0)"}, {backgroundColor:"${N[k][3]}", duration:0.3, ease:"power1.out"}, ${r2(F("b33", 0.3) + i * 0.3)});
land("#xn-${k}", ${r2(F("b33", 0.3) + i * 0.3 + 0.2)}, {from:0, ease:"back.out(1.8)"});`).join("\n")}
fade("#ex-leg", ${F("b33", 0.85)});
${ED.map((_, i) => `draw("#exe${i}", ${r2(F("b34", 0.3) + i * 0.45)}, {d:0.45});
land("#xl${i}", ${r2(F("b34", 0.3) + i * 0.45 + 0.3)}, {from:0.6});`).join("\n")}
`);
}

// ============================================================ knowledge GRAPH data
const GN = {
  scr: [480, 300, "Scrooge", "office", 1], fred: [330, 165, "Fred", "office"], off: [430, 445, "the office", "office"], cha: [285, 330, "charity collectors", "office"],
  bob: [690, 395, "Bob Cratchit", "cratchit"], tim: [830, 520, "Tiny Tim", "cratchit"], mrs: [870, 395, "Mrs. Cratchit", "cratchit"], pet: [640, 530, "Peter", "cratchit"],
  gpa: [130, 110, "Ghost of Past", "past"], fan: [100, 260, "Fan", "past"], fez: [130, 430, "Fezziwig", "past"], bel: [270, 525, "Belle", "past"],
  mar: [580, 85, "Jacob Marley", "ghosts"], gpr: [780, 150, "Ghost of Present", "ghosts"], gyc: [890, 270, "Ghost of Yet to Come", "ghosts"],
};
const GE = [
  ["bob", "scr", "works for"], ["tim", "bob", "son of"], ["mrs", "bob"], ["pet", "bob"], ["tim", "mrs"], ["pet", "tim"],
  ["fred", "scr"], ["fan", "fred"], ["fan", "scr"], ["fez", "scr"], ["bel", "scr"], ["gpa", "scr"], ["gpa", "fez"], ["gpa", "bel"], ["gpa", "fan"],
  ["mar", "scr"], ["mar", "gpr"], ["gpr", "scr"], ["gpr", "bob"], ["gpr", "fred"], ["gyc", "scr"], ["gyc", "tim"], ["gpr", "gyc"],
  ["off", "scr"], ["off", "bob"], ["mar", "off"], ["cha", "scr"],
];
const GCL = {
  office: { label: "Scrooge's office", color: "#f0c860" },
  cratchit: { label: "The Cratchits", color: "#f0a87a" },
  past: { label: "Scrooge's past", color: "#a9c79b" },
  ghosts: { label: "The ghosts", color: "#bdb2ea" },
};
const GBOX = { l: 18 * PX, t: 13 * PY, w: 1228.8, h: 737.28 }; // px; viewBox 1000 x 600
css(`
.gbox { position:absolute; left:${GBOX.l}px; top:${GBOX.t}px; width:${GBOX.w}px; height:${GBOX.h}px; transform-origin:0% 50%; }
.gbox svg { position:absolute; inset:0; overflow:visible; }
.gbox .ge { stroke:var(--fg); stroke-width:2; opacity:0.5; }
.gbox .gp { stroke:var(--accent-strong); stroke-width:6; stroke-linecap:round; }
.gn { position:absolute; width:0; height:0; z-index:3; }
.gn span { position:absolute; left:0; top:0; transform:translate(-50%,-50%); white-space:nowrap; font-size:1.25cqw; padding:0.4cqw 0.9cqw;
  border-radius:999px; border:0.12cqw solid var(--fg); background:var(--surface); box-shadow:0 0.2cqw 0 var(--fg); }
.gn.big span { font-size:1.75cqw; padding:0.5cqw 1.25cqw; }
.gcl { position:absolute; width:0; height:0; z-index:4; }
.gcl span { position:absolute; left:0; top:0; transform:translate(-50%,-50%); white-space:nowrap; font-size:1.15cqw; padding:0.3cqw 0.8cqw; border-radius:0.4cqw;
  background:var(--fg); color:var(--bg); }
.hop { position:absolute; width:0; height:0; z-index:5; }
.hop span { position:absolute; left:0; top:0; transform:translate(-50%,-50%); width:2.2cqw; height:2.2cqw; border-radius:50%; background:var(--fg); color:var(--bg);
  display:flex; align-items:center; justify-content:center; font-size:1.1cqw; }
.gel { position:absolute; width:0; height:0; z-index:4; }
.gel span { position:absolute; left:0; top:0; transform:translate(-50%,-50%); white-space:nowrap; font-size:1cqw; padding:0.2cqw 0.5cqw; border-radius:0.3cqw;
  background:var(--surface); border:0.1cqw solid var(--fg); }
`);
// blobs: ellipse around each cluster's members
const blobs = Object.entries(GCL).map(([id, c]) => {
  const ms = Object.values(GN).filter((n) => n[3] === id);
  const xs = ms.map((m) => m[0]), ys = ms.map((m) => m[1]);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  return { id, cx, cy, rx: (Math.max(...xs) - Math.min(...xs)) / 2 + 95, ry: (Math.max(...ys) - Math.min(...ys)) / 2 + 55, color: c.color, label: c.label };
});
function graphHtml(p, { blobs: withBlobs = true, colored = false } = {}) {
  const pct = (x, y) => `left:${x / 10}%; top:${y / 6}%`;
  return `<div class="gbox" id="${p}">
<svg viewBox="0 0 1000 600" width="${GBOX.w}" height="${GBOX.h}">
${withBlobs ? blobs.map((b) => `<ellipse class="${p}-blob" id="${p}-bl-${b.id}" cx="${b.cx}" cy="${b.cy}" rx="${r2(b.rx)}" ry="${r2(b.ry)}" fill="${b.color}" fill-opacity="0.32"/>`).join("") : ""}
${GE.map(([a, b], i) => sline(GN[a][0], GN[a][1], GN[b][0], GN[b][1], `${p}-e${i}`, `ge ${p}-e`)).join("")}
<!--paths-->
</svg>
${Object.entries(GN).map(([k, n]) => `<div class="gn ${n[4] ? "big" : ""} ${p}-n" id="${p}-n-${k}" style="${pct(n[0], n[1])}"><span id="${p}-s-${k}"${colored ? ` style="background:${GCL[n[3]].color}"` : ""}>${n[2]}</span></div>`).join("")}
<!--extra-->
</div>`;
}
const edgeIdx = (a, b) => GE.findIndex((e) => (e[0] === a && e[1] === b) || (e[0] === b && e[1] === a));

// ============================================================ 4 · graph: build, path, clusters, summaries
css(`
.sum { position:absolute; left:50cqw; width:45cqw; height:15cqh; padding:0.9cqw 1.3cqw 0.9cqw 2cqw; display:flex; flex-direction:column; justify-content:center; gap:0.3cqw; }
.sum::before { content:""; position:absolute; left:0; top:0; bottom:0; width:0.6cqw; background:var(--c); border-radius:1cqw 0 0 1cqw; }
.sum .h { font-size:1.7cqw; letter-spacing:-0.01em; display:flex; align-items:center; gap:0.6cqw; }
.sum .h .chk { color:var(--fg); font-size:1.1cqw; margin-left:auto; }
.sum .b { font-size:1.3cqw; color:var(--muted); line-height:1.32; }
#leiden { position:absolute; left:4cqw; top:74cqh; display:flex; align-items:center; gap:0.6cqw; font-size:1.25cqw; padding:0.45cqw 0.9cqw;
  border-radius:999px; background:var(--surface); border:0.12cqw solid var(--fg); z-index:6; }
.g1sw { position:absolute; left:8cqw; top:72cqh; z-index:7; transform:rotate(-3deg); }
#g1-stamp { position:static; display:inline-block; font-size:1.5cqw; color:var(--fg); background:var(--butter); border-color:var(--fg); }
`);
{
  const p = "g1";
  const pathE = [["tim", "bob"], ["bob", "scr"]];
  const hops = pathE.map(([a, b]) => [(GN[a][0] + GN[b][0]) / 2, (GN[a][1] + GN[b][1]) / 2]);
  const paths = pathE.map(([a, b], i) => sline(GN[a][0], GN[a][1], GN[b][0], GN[b][1], `${p}-p${i}`, "gp")).join("");
  const labs = [["bob", "scr", "works for", 610, 285], ["tim", "bob", "son of", 712, 505]];
  const extra = `
${hops.map(([x, y], i) => `<div class="hop" id="${p}-hop${i}" style="left:${x / 10}%; top:${y / 6}%"><span>${i + 1}</span></div>`).join("")}
${labs.map(([a, b, t, x, y], i) => `<div class="gel" id="${p}-el${i}" style="left:${x / 10}%; top:${y / 6}%"><span class="mono">${t}</span></div>`).join("")}
${blobs.map((b) => `<div class="gcl ${p}-cl" id="${p}-cl-${b.id}" style="left:${b.cx / 10}%; top:${(b.cy - b.ry) / 6}%"><span class="mono">${b.label}</span></div>`).join("")}`;
  const order = Object.keys(GN).sort((a, b) => Math.hypot(GN[a][0] - 480, GN[a][1] - 300) - Math.hypot(GN[b][0] - 480, GN[b][1] - 300));
  const SUMS = [
    ["cratchit", "The Cratchits", "Scrooge's poor clerk and his family. Tiny Tim is sick. They stay kind and thankful anyway."],
    ["past", "Scrooge's past", "Scrooge as a lonely boy. Joyful Fezziwig. Belle leaves him over his love of money."],
    ["ghosts", "The ghosts", "Marley warns Scrooge. The spirits show him the present, and a dark future."],
    ["office", "Scrooge's office", "Scrooge is greedy and cold. He turns away the charity collectors and his nephew Fred."],
  ];
  const nonPath = Object.keys(GN).filter((k) => !["tim", "bob", "scr"].includes(k));
  const pathEdges = pathE.map(([a, b]) => edgeIdx(a, b));
  scene("s-graph1", "b35", "b40", graphHtml(p).replace("<!--paths-->", paths).replace("<!--extra-->", extra) + `
<div id="leiden"><span class="mono">algorithm:</span><span>Leiden</span></div>
${SUMS.map(([c, h, b], i) => `<div class="card sum" id="sum${i}" style="top:${13 + i * 17}cqh; --c:${GCL[c].color}"><div class="h">${h}<span class="sumck" id="sumck${i}">${check()}</span></div><div class="b">${b}</div></div>`).join("")}
<span class="g1sw"><span class="stamp" id="g1-stamp">summed up before any question</span></span>`, { push: false });
  js(`
${order.map((k, i) => `land("#${p}-n-${k}", ${r2(T("b35") + 0.1 + i * 0.07)}, {from:0, ease:"back.out(1.8)", d:0.38});`).join("\n")}
draw(".${p}-e", ${F("b35", 0.2)}, {st:0.06, d:0.4});
tl.to("${nonPath.map((k) => `#${p}-n-${k}`).join(", ")}", {opacity:0.25, duration:0.4}, ${T("b36")});
tl.to("${GE.map((_, i) => i).filter((i) => !pathEdges.includes(i)).map((i) => `#${p}-e${i}`).join(", ")}", {opacity:0.12, duration:0.4}, ${T("b36")});
tl.to("#${p}-s-tim, #${p}-s-bob, #${p}-s-scr", {backgroundColor:"#f0a87a", duration:0.3}, ${T("b36") + 0.2});
draw("#${p}-p0", ${F("b36", 0.3)}, {d:0.45}); land("#${p}-hop0", ${r2(F("b36", 0.3) + 0.35)}, {from:0, ease:"back.out(2.4)"}); land("#${p}-el1", ${r2(F("b36", 0.3) + 0.4)}, {from:0.6});
draw("#${p}-p1", ${F("b36", 0.55)}, {d:0.45}); land("#${p}-hop1", ${r2(F("b36", 0.55) + 0.35)}, {from:0, ease:"back.out(2.4)"}); land("#${p}-el0", ${r2(F("b36", 0.55) + 0.4)}, {from:0.6});
tl.to("${nonPath.map((k) => `#${p}-n-${k}`).join(", ")}", {opacity:1, duration:0.4}, ${T("b37")});
tl.to("${GE.map((_, i) => i).filter((i) => !pathEdges.includes(i)).map((i) => `#${p}-e${i}`).join(", ")}", {opacity:0.5, duration:0.4}, ${T("b37")});
tl.to("#${p}-p0, #${p}-p1, #${p}-hop0, #${p}-hop1, #${p}-el0, #${p}-el1", {opacity:0, duration:0.35}, ${T("b37")});
${Object.entries(GN).map(([k, n], i) => `tl.to("#${p}-s-${k}", {backgroundColor:"${GCL[n[3]].color}", duration:0.35}, ${r2(F("b37", 0.35) + i * 0.03)});`).join("\n")}
tl.fromTo(".${p}-blob", {opacity:0, scale:0.4, transformOrigin:"50% 50%"}, {opacity:1, scale:1, duration:0.7, ease:"power3.out", stagger:0.12}, ${F("b37", 0.4)});
${["cratchit", "past", "ghosts", "office"].map((c, i) => `land("#${p}-cl-${c}", ${Wd("b38", [1, 3, 6, 8][i])}, {from:0.6, ease:"back.out(2)"});`).join("\n")}
land("#leiden", ${F("b38", 0.62)}, {from:0.8});
exit("#leiden", ${T("b39")});
to("#${p}", {x:${-15 * PX}, scale:0.68, duration:0.8, ease:"power3.inOut"}, ${T("b39")});
${SUMS.map((_, i) => `land("#sum${i}", ${r2(T("b39") + 0.6 + i * 0.32)}, {from:0.94, y:18});`).join("\n")}
${SUMS.map((_, i) => `land("#sumck${i}", ${r2(T("b40") + 0.1 + i * 0.18)}, {from:0, ease:"back.out(2.4)"});`).join("\n")}
land("#g1-stamp", ${F("b40", 0.55)}, {from:1.7, ease:"back.out(2)"});
`);
}

// ============================================================ 4 · map-reduce (global search)
css(`
#mr-q { left:20cqw; top:11.5cqh; width:60cqw; padding:0.8cqw 1.4cqw; font-size:2.2cqw; letter-spacing:-0.01em; }
#mr-q .mono { display:block; font-size:0.95cqw; color:var(--muted); margin-bottom:0.25cqw; }
.mrs { position:absolute; top:27cqh; width:19cqw; height:12cqh; padding:0.7cqw 1cqw 0.7cqw 1.6cqw; display:flex; flex-direction:column; justify-content:center; gap:0.3cqw; }
.mrs::before { content:""; position:absolute; left:0; top:0; bottom:0; width:0.5cqw; background:var(--c); border-radius:1cqw 0 0 1cqw; }
.mrs .mono { font-size:0.9cqw; color:var(--muted); }
.mrs .h { font-size:1.75cqw; }
.mrp { position:absolute; top:47cqh; width:19cqw; height:8cqh; display:flex; align-items:center; justify-content:center; text-align:center; font-size:1.4cqw;
  border-radius:0.8cqw; border:0.12cqw dashed var(--fg); background:var(--bg); padding:0 0.8cqw; }
#mr-svg line { stroke:var(--fg); stroke-width:2.5; }
#mr-f { left:17cqw; top:63cqh; width:66cqw; height:18cqh; padding:1cqw 1.6cqw; background:var(--fg); color:var(--bg); display:flex; flex-direction:column; justify-content:center; gap:0.9cqw; }
#mr-f .mono { font-size:0.95cqw; color:var(--butter); }
#mr-f .pills { display:flex; gap:0.9cqw; flex-wrap:nowrap; }
#mr-f .pills span { font-size:1.9cqw; white-space:nowrap; padding:0.3cqw 1.1cqw; border-radius:999px; color:var(--fg); }
#mr-f .fs { font-size:1cqw; color:rgba(243,236,217,0.65); }
`);
{
  const L = [9, 30, 51, 72];
  const SUM = [["cratchit", "The Cratchits", "family, being thankful"], ["past", "Scrooge's past", "money over love"], ["ghosts", "The ghosts", "it's not too late to change"], ["office", "Scrooge's office", "greed, ignoring the poor"]];
  const cx = (l) => (l + 9.5) * PX;
  const down = L.map((l, i) => sline(cx(l), 39.5 * PY, cx(l), 46.5 * PY, `mrd${i}`)).join("");
  const conv = L.map((l, i) => sline(cx(l), 55.5 * PY, (50 + (i - 1.5) * 4) * PX, 62.5 * PY, `mrc${i}`)).join("");
  const themes = [["Greed", "#f0c860"], ["Redemption", "#bdb2ea"], ["Family", "#f0a87a"], ["Kindness to the poor", "#a9c79b"]];
  scene("s-mr", "b41", "b43", `
<div class="card" id="mr-q"><span class="mono">global question</span>What are the main themes of this book?</div>
${SUM.map(([c, h], i) => `<div class="card mrs" id="mrs${i}" style="left:${L[i]}cqw; --c:${GCL[c].color}"><span class="mono">cluster summary</span><span class="h">${h}</span></div>`).join("")}
<svg id="mr-svg" style="position:absolute;inset:0" viewBox="0 0 1920 1080" width="1920" height="1080">${down}${conv}</svg>
${SUM.map(([, , t], i) => `<div class="mrp" id="mrp${i}" style="left:${L[i]}cqw">${t}</div>`).join("")}
<div class="card" id="mr-f"><span class="mono">final answer</span><span class="mono" id="mr-wait" style="position:absolute; left:1.6cqw; top:50%; color:rgba(243,236,217,0.6)">combining 4 partial answers…</span><div class="pills">${themes.map(([t, c], i) => `<span id="mrt${i}" style="background:${c}">${t}</span>`).join("")}</div><span class="mono fs" id="mr-fs">built from every cluster summary</span></div>`);
  js(`
land("#mr-q", ${T("b41")}, {from:0.95, y:14});
${L.map((_, i) => `land("#mrs${i}", ${r2(F("b41", 0.45) + i * 0.15)}, {from:0.9, y:16});`).join("\n")}
draw("#mr-svg line[id^=mrd]", ${F("b42", 0.08)}, {st:0.12, d:0.35});
${L.map((_, i) => `land("#mrp${i}", ${r2(F("b42", 0.18) + i * 0.22)}, {from:0.8, ease:"back.out(1.8)"});`).join("\n")}
draw("#mr-svg line[id^=mrc]", ${F("b42", 0.62)}, {st:0.08, d:0.4});
land("#mr-f", ${F("b42", 0.82)}, {from:0.94, y:16});
fade("#mr-wait", ${r2(F("b42", 0.82) + 0.3)});
exit("#mr-wait", ${r2(T("b43") - 0.2)}, {y:0, d:0.2});
${themes.map((_, i) => `land("#mrt${i}", ${Wd("b43", [0, 1, 2, 3][i])}, {from:0.5, ease:"back.out(2.2)"});`).join("\n")}
fade("#mr-fs", ${F("b43", 0.6)});
`);
}

// ============================================================ 4 · local search
css(`
#g2 { transform:translateX(${-15 * PX}px) scale(0.66); }
.lg { position:absolute; left:52cqw; width:43cqw; height:24cqh; padding:1.3cqw 1.6cqw; display:flex; flex-direction:column; gap:0.5cqw; }
.lg .mono { font-size:1.1cqw; color:var(--muted); }
.lg .h { font-size:2.6cqw; letter-spacing:-0.02em; }
.lg .b { font-size:1.55cqw; color:var(--muted); line-height:1.35; }
#lg1 { top:16cqh; } #lg2 { top:46cqh; border-color:var(--accent-strong); }
.pulse { position:absolute; width:0; height:0; z-index:2; }
.pulse span { position:absolute; left:-4cqw; top:-4cqw; width:8cqw; height:8cqw; border-radius:50%; border:0.25cqw solid var(--accent-strong); background:rgba(240,168,122,0.2); }
`);
{
  const p = "g2";
  const nb = GE.map((e, i) => ({ e, i })).filter(({ e }) => e[0] === "tim" || e[1] === "tim");
  const nbKeys = nb.map(({ e }) => (e[0] === "tim" ? e[1] : e[0]));
  const paths = nb.map(({ e }, k) => sline(GN[e[0]][0], GN[e[0]][1], GN[e[1]][0], GN[e[1]][1], `${p}-p${k}`, "gp")).join("");
  const extra = `<div class="pulse" id="${p}-pulse" style="left:${GN.tim[0] / 10}%; top:${GN.tim[1] / 6}%"><span id="${p}-pr"></span></div>`;
  BODY += ""; // (graph is static here: CSS transform on #g2 is fine because GSAP never tweens #g2 itself)
  scene("s-local", "b44", "b44", graphHtml(p, { colored: true }).replace("<!--paths-->", paths).replace("<!--extra-->", extra) + `
<div class="card lg" id="lg1"><span class="mono">global search</span><span class="h">Big picture questions</span><span class="b">Ask every cluster summary, then combine the parts.</span></div>
<div class="card lg" id="lg2"><span class="mono">local search</span><span class="h">Detail questions</span><span class="b">Start at one dot, and walk the lines around it.</span></div>`, { push: false });
  js(`
tl.fromTo("#s-local-st", {opacity:0}, {opacity:1, duration:0.4}, ${T("b44")});
tl.set(".${p}-e", {strokeDashoffset:0}, ${T("b44")});
tl.set(".${p}-blob", {opacity:0.55}, ${T("b44")});
land("#lg1", ${T("b44") + 0.2}, {from:0.95, y:16});
land("#lg2", ${F("b44", 0.3)}, {from:0.95, y:16});
tl.fromTo("#${p}-pr", {opacity:0, scale:0}, {opacity:1, scale:1, duration:0.5, ease:"back.out(1.6)"}, ${F("b44", 0.62)});
draw("#${p} .gp", ${F("b44", 0.7)}, {st:0.12, d:0.4});
tl.to("${nbKeys.map((k) => `#${p}-s-${k}`).join(", ")}", {backgroundColor:"#e07a45", color:"#faf6ec", duration:0.3, stagger:0.12}, ${F("b44", 0.78)});
`);
}

// ============================================================ 5 · the test (dark card)
css(`
#ts { left:7cqw; top:13cqh; width:86cqw; height:68cqh; background:var(--fg); color:var(--bg); }
#ts .k2 { position:absolute; left:3cqw; top:3cqw; font-size:1.1cqw; color:var(--butter); }
.ds { position:absolute; left:3cqw; width:30cqw; height:18cqh; border:0.14cqw solid rgba(243,236,217,0.45); border-radius:1cqw; padding:1.2cqw 1.4cqw;
  display:flex; flex-direction:column; justify-content:center; gap:0.5cqw; }
.ds .h { font-size:2.1cqw; letter-spacing:-0.02em; }
.ds .mono { font-size:1.05cqw; color:rgba(243,236,217,0.7); }
#ds1 { top:22cqh; } #ds2 { top:44cqh; }
#ts-n { position:absolute; left:40cqw; top:13cqh; font-size:11cqw; line-height:1; color:var(--butter); white-space:nowrap; }
#ts-l { position:absolute; left:40.5cqw; top:41cqh; width:42cqw; font-size:2.2cqw; line-height:1.3; }
#ts-f { position:absolute; left:40.5cqw; top:58cqh; width:42cqw; font-size:1cqw; color:rgba(243,236,217,0.6); line-height:1.6; }
`);
scene("s-test", "b45", "b46", `
<div class="card" id="ts"><span class="mono k2">the test · Microsoft Research, 2024</span>
<div class="ds" id="ds1"><span class="h">Podcast transcripts</span><span class="mono">about 1M tokens · 1,669 chunks</span></div>
<div class="ds" id="ds2"><span class="h">News articles</span><span class="mono">about 1.7M tokens · 3,197 chunks</span></div>
<div class="serif" id="ts-n">72–83%</div>
<div id="ts-l">of the time, GraphRAG's answers were rated more complete than plain RAG's.</div>
<div class="mono" id="ts-f">big picture questions · rated by an AI judge<br>Edge et al., From Local to Global, 2024</div></div>`);
js(`
land("#ts", ${T("b45")}, {from:0.96, y:20});
fade("#ts .k2", ${T("b45") + 0.4});
rise("#ds1, #ds2", ${F("b45", 0.45)}, {st:0.35, y:20});
tl.fromTo("#ts-n", {opacity:0, y:30, scale:0.9}, {opacity:1, y:0, scale:1, duration:0.6, ease:"back.out(1.6)"}, ${F("b46", 0.62)});
rise("#ts-l", ${F("b46", 0.12)}, {y:14});
fade("#ts-f", ${F("b46", 0.8)});
`);

// ============================================================ 5 · cost receipts
css(`
#cs-h { position:absolute; left:0; right:0; top:11.5cqh; text-align:center; font-size:3cqw; letter-spacing:-0.03em; }
.rc { top:22cqh; width:34cqw; padding:1.5cqw 1.8cqw; display:flex; flex-direction:column; gap:0.9cqw; font-family:"JetBrains Mono"; font-weight:500; }
#rc1 { left:12cqw; height:30cqh; } #rc2 { left:54cqw; height:58cqh; }
.rc .rh { font-family:"Space Grotesk"; font-size:2.4cqw; letter-spacing:-0.02em; }
.rc .rs { font-size:0.95cqw; color:var(--muted); text-transform:uppercase; letter-spacing:0.14em; margin-top:0.4cqw; }
.rc .li { display:flex; font-size:1.3cqw; gap:0.4cqw; }
.rc .li .dots { flex:1; border-bottom:0.14cqw dotted rgba(22,21,19,0.45); margin-bottom:0.4cqw; }
.rc .tot { margin-top:auto; border-top:0.14cqw dashed var(--fg); padding-top:0.8cqw; display:flex; justify-content:space-between; font-size:1.45cqw; text-transform:uppercase; letter-spacing:0.08em; }
.rc .tot b { font-weight:500; padding:0.1cqw 0.6cqw; border-radius:0.3cqw; }
`);
{
  const li = (a, b) => `<div class="li"><span>${a}</span><span class="dots"></span><span>${b}</span></div>`;
  scene("s-cost", "b47", "b49", `
<div id="cs-h">Reading up front isn't <span class="serif pill">free</span></div>
<div class="card rc" id="rc1"><span class="rh">Plain RAG</span><span class="rs">to index the book</span>${li("embed each chunk", "1 small call")}<div class="tot"><span>total</span><b style="background:#a9c79b">cheap · fast</b></div></div>
<div class="card rc" id="rc2"><span class="rh">GraphRAG</span><span class="rs">for every chunk</span>${li("embed it", "1 small call")}${li("AI reads it", "1 big call")}${li("pull out things + links", "same call")}${li("double-check for misses", "sometimes")}
<span class="rs">then for every cluster</span>${li("write a summary", "1 big call")}${li("at every level of clusters", "repeat")}<div class="tot"><span>total</span><b style="background:#e07a45; color:#faf6ec">slow · pricey</b></div></div>`);
  js(`
rise("#cs-h", ${T("b47")}, {y:20});
land("#rc2", ${T("b48")}, {from:0.95, y:20});
rise("#rc2 > *", ${T("b48") + 0.3}, {st:0.42, y:8});
land("#rc1", ${T("b49")}, {from:0.95, y:20});
rise("#rc1 > *", ${T("b49") + 0.3}, {st:0.25, y:8});
`);
}

// ============================================================ 5 · table
css(`
#tb { left:9cqw; top:12.5cqh; width:82cqw; height:69cqh; padding:1.2cqw 1.6cqw; }
.tr { position:absolute; left:1.6cqw; right:1.6cqw; height:10cqh; display:grid; grid-template-columns:24cqw 1fr 1fr; align-items:center; gap:1cqw;
  border-bottom:0.12cqw solid rgba(22,21,19,0.15); }
.tr .c0 { font-size:1.15cqw; color:var(--muted); }
.tr .c { font-size:1.75cqw; letter-spacing:-0.01em; padding:0.5cqw 0.9cqw; border-radius:0.5cqw; }
.tr.hd .c { font-size:2.3cqw; }
.tr .win { background:rgba(240,200,96,0.55); }
`);
{
  const rows = [
    ["Setup cost", "Cheap and fast", "Slow and pricey", 1],
    ["Best at", "Finding one fact", "Connections and themes", 0],
    ["Big picture questions", "Weak", "Strong", 2],
    ["Connect the dots", "Hit or miss", "Strong", 2],
    ["Adding new docs", "Easy", "More work", 1],
  ];
  const times = [F("b50", 0.55), F("b51", 0.0), F("b51", 0.22), F("b51", 0.44), F("b51", 0.66)];
  scene("s-table", "b50", "b51", `
<div class="card" id="tb">
<div class="tr hd" id="tr-h" style="top:1.5cqh"><span></span><span class="c">RAG</span><span class="c">GraphRAG</span></div>
${rows.map(([a, b, c, w], i) => `<div class="tr" id="tr${i}" style="top:${12 + i * 11}cqh"><span class="mono c0">${a}</span><span class="c" id="tc${i}a">${b}</span><span class="c" id="tc${i}b">${c}</span></div>`).join("")}
</div>`);
  js(`
land("#tb", ${T("b50")}, {from:0.97, y:16});
rise("#tr-h .c", ${T("b50") + 0.3}, {st:0.15, y:10});
${rows.map(([, , , w], i) => `rise("#tr${i} > *", ${times[i]}, {st:0.12, y:10});${w ? `
tl.fromTo("#tc${i}${w === 1 ? "a" : "b"}", {backgroundColor:"rgba(240,200,96,0)"}, {backgroundColor:"rgba(240,200,96,0.6)", duration:0.35}, ${r2(times[i] + 0.45)});` : ""}`).join("\n")}
`);
}

// ============================================================ 6 · decision tree
css(`
#dt-root { left:34cqw; top:12.5cqh; width:32cqw; height:10cqh; display:flex; align-items:center; justify-content:center; font-size:2.4cqw; letter-spacing:-0.02em; }
#dt-svg line { stroke:var(--fg); stroke-width:3; }
.dq { position:absolute; width:0; height:0; z-index:3; }
.dq span { position:absolute; left:0; top:0; transform:translate(-50%,-50%); white-space:nowrap; font-size:1.7cqw; padding:0.3cqw 0.8cqw; background:var(--bg); border-radius:0.4cqw; }
.oc { top:45cqh; width:26cqw; height:34cqh; padding:1.5cqw 1.7cqw; display:flex; flex-direction:column; gap:0.7cqw; }
.oc .mono { font-size:1cqw; color:var(--muted); }
.oc .h { font-size:2.7cqw; letter-spacing:-0.03em; }
.oc .b { font-size:1.55cqw; color:var(--muted); line-height:1.35; }
#oc1 { left:7cqw; } #oc2 { left:37cqw; border-color:var(--accent-strong); } #oc3 { left:67cqw; }
#oc2 .st { margin-top:auto; display:flex; align-items:baseline; gap:0.8cqw; }
#oc2 .st .n { font-size:4.6cqw; line-height:1; color:var(--accent-strong); }
#oc2 .st .l { font-size:1.25cqw; line-height:1.3; }
#oc2 .src { font-size:0.9cqw; color:var(--muted); }
`);
{
  const root = [50 * PX, 22.5 * PY];
  const tgt = [[20, 45], [50, 45], [80, 45]].map(([x, y]) => [x * PX, y * PY]);
  scene("s-tree", "b52", "b56", `
<div class="card" id="dt-root">What do people ask?</div>
<svg id="dt-svg" style="position:absolute;inset:0" viewBox="0 0 1920 1080" width="1920" height="1080">${tgt.map((t, i) => sline(root[0], root[1], t[0], t[1], `dtl${i}`)).join("")}</svg>
<div class="dq" id="dq1" style="left:27cqw; top:33cqh"><span class="serif">“find me the fact”</span></div>
<div class="dq" id="dq3" style="left:73cqw; top:33cqh"><span class="serif">“how is this connected?”</span></div>
<div class="dq" id="dq2" style="left:50cqw; top:34cqh"><span class="serif">“a bit of both”</span></div>
<div class="card oc" id="oc1"><span class="mono">start here</span><span class="h">Plain RAG</span><span class="b">Most apps are this. Cheap, fast, and easy to keep updated.</span></div>
<div class="card oc" id="oc3"><span class="mono">worth the cost when</span><span class="h">GraphRAG</span><span class="b">Your questions need connections, or the big picture.</span></div>
<div class="card oc" id="oc2"><span class="mono">the middle ground</span><span class="h">LazyGraphRAG</span><span class="b">Skips most of the up front work.</span>
<div class="st" id="oc2-st"><span class="serif n">0.1%</span><span class="l">of full GraphRAG's<br>indexing cost</span></div><span class="mono src" id="oc2-src">same as plain RAG · Microsoft Research, Nov 2024</span></div>`);
  js(`
land("#dt-root", ${T("b52")}, {from:0.9, y:-10});
draw("#dtl0", ${T("b53")}, {d:0.5}); land("#dq1", ${T("b53") + 0.3}, {from:0.7}); land("#oc1", ${T("b53") + 0.55}, {from:0.94, y:20});
draw("#dtl2", ${T("b54")}, {d:0.5}); land("#dq3", ${T("b54") + 0.3}, {from:0.7}); land("#oc3", ${T("b54") + 0.55}, {from:0.94, y:20});
draw("#dtl1", ${T("b55")}, {d:0.5}); land("#dq2", ${T("b55") + 0.3}, {from:0.7}); land("#oc2", ${F("b55", 0.45)}, {from:0.94, y:20});
tl.to("#oc1, #oc3", {opacity:0.45, duration:0.4}, ${T("b56")});
rise("#oc2-st", ${F("b56", 0.45)}, {y:14});
fade("#oc2-src", ${F("b56", 0.75)});
`);
}

// ============================================================ 7 · recap
css(`
.rcp { top:14cqh; width:39cqw; height:42cqh; padding:1.8cqw; display:flex; flex-direction:column; gap:1cqw; }
#rcp1 { left:9cqw; } #rcp2 { left:52cqw; }
.rcp .mono { font-size:1.15cqw; color:var(--muted); }
.rcp .h { font-size:3.6cqw; line-height:1.02; letter-spacing:-0.035em; }
.rcp .tags { display:flex; gap:0.7cqw; flex-wrap:wrap; margin-top:auto; }
.rcp .tags span { font-size:1.5cqw; padding:0.35cqw 1cqw; border-radius:999px; border:0.12cqw solid var(--fg); }
#rc-end { position:absolute; left:0; right:0; top:63cqh; text-align:center; font-size:4.6cqw; letter-spacing:-0.03em; }
#rc-end .pill { padding:0 0.35em 0.05em; }
`);
// tiny motifs: a pin among dots (RAG), a little graph (GraphRAG); card-relative px
const RD = [[40, 50], [95, 30], [70, 105], [150, 70], [125, 145], [30, 135], [180, 150]];
const RG = [[30, 40], [110, 25], [185, 70], [60, 135], [155, 150], [105, 90]];
const RGE = [[0, 1], [1, 2], [0, 3], [3, 5], [5, 1], [5, 4], [2, 4]];
css(`.rmot { position:absolute; right:2.4cqw; top:2.4cqw; width:210px; height:180px; }
.rmot i { position:absolute; width:16px; height:16px; margin:-8px 0 0 -8px; border-radius:50%; background:var(--fg); }
.rmot i.p { background:var(--accent-strong); width:26px; height:26px; margin:-13px 0 0 -13px; border:3px solid var(--fg); }
.rmot svg { position:absolute; inset:0; } .rmot line { stroke:var(--fg); stroke-width:3; }`);
const RMOT1 = `<div class="rmot">${RD.map(([x, y]) => `<i style="left:${x}px; top:${y}px"></i>`).join("")}<i class="p" style="left:92px; top:88px"></i></div>`;
const RMOT2 = `<div class="rmot"><svg viewBox="0 0 210 180" width="210" height="180">${RGE.map(([a, b]) => `<line x1="${RG[a][0]}" y1="${RG[a][1]}" x2="${RG[b][0]}" y2="${RG[b][1]}"/>`).join("")}</svg>${RG.map(([x, y], i) => `<i ${i === 5 ? 'class="p"' : ""} style="left:${x}px; top:${y}px"></i>`).join("")}</div>`;
scene("s-recap", "b57", "b59", `
<div class="card rcp" id="rcp1">${RMOT1}<span class="mono">RAG</span><span class="h">Finds the<br>closest chunks.</span><div class="tags"><span>fast</span><span>cheap</span><span style="background:#f0c860">great for facts</span></div></div>
<div class="card rcp" id="rcp2">${RMOT2}<span class="mono">GraphRAG</span><span class="h">Builds a map<br>first.</span><div class="tags"><span>slower</span><span>pricier</span><span style="background:#f0a87a">connections</span><span style="background:#a9c79b">big picture</span></div></div>
<div id="rc-end">Pick by the <span class="serif pill" id="rc-q">question</span>, not the hype.</div>`);
js(`
land("#rcp1", ${T("b57") + 0.2}, {from:0.94, y:20}); rise("#rcp1 .tags span", ${F("b57", 0.55)}, {st:0.25, y:10});
land("#rcp2", ${T("b58")}, {from:0.94, y:20}); rise("#rcp2 .tags span", ${F("b58", 0.5)}, {st:0.2, y:10});
rise("#rc-end", ${T("b59")}, {y:20});
land("#rc-q", ${T("b59") + 0.35}, {from:0.6, ease:"back.out(2.2)"});
`);

// ============================================================ end card
css(`
#end { position:absolute; left:0; right:0; top:28cqh; display:flex; flex-direction:column; align-items:center; gap:1.8cqw; }
#end .h { font-size:7cqw; letter-spacing:-0.045em; line-height:1; }
#end .s { font-size:3.2cqw; }
#end .hd { font-size:1.3cqw; padding:0.6cqw 1.3cqw; border-radius:999px; background:var(--fg); color:var(--bg); letter-spacing:0.08em; text-transform:none; }
`);
scene("s-end", "b60", "b60", `
<div id="end"><div class="h" id="end-h">Subscribe</div><div class="serif s" id="end-s">for more AI, explained <span class="pill">simply</span></div><div class="mono hd" id="end-hd">@yourchannel</div></div>`);
js(`
rise("#end-h", ${T("b60")}, {y:30, d:0.6});
rise("#end-s", ${T("b60") + 0.3}, {y:16});
land("#end-hd", ${T("b60") + 0.7}, {from:0.7});
`);

// ============================================================ WRITE
const subs = subtitleChunks(beats);
ensureEdit(path.join(HERE, "edit"));
write(path.join(HERE, "edit", "index.html"), page({ total, css: CSS, body: BODY, js: JS, chapters, subs, showSubs }));

const fmt = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
const table = beats.map((b) => `| ${fmt(b.start)} | ${CHAPTERS[b.ch] || "Intro"} | ${b.text} | ${b.v} |`).join("\n");
write(path.join(HERE, "script.md"), `# ep01 · RAG vs GraphRAG · scene table

Generated by \`build.mjs\` from the beat list. Edit the beats there, not here.
Runtime **${fmt(total)}** (${total}s) at ${2.4} words/sec reading pace, ${beats.length} beats,
${beats.reduce((a, b) => a + b.words, 0)} words of narration.

| Time | Chapter | Narration (subtitled now, voiced later) | On screen |
|---|---|---|---|
${table}
`);
console.log(`built: ${beats.length} beats, ${subs.length} subtitle chunks, ${fmt(total)} (${total}s), ${track - 10} layers`);
write(path.join(HERE, "beats.json"), JSON.stringify(beats.map(({ id, ch, start, end, dur, words }) => ({ id, ch, start, end, dur, words })), null, 1));
write(path.join(HERE, "total.txt"), String(total));
// YouTube captions file (upload it: captions are indexed, burned-in text is not)
const srtT = (t) => { const ms = Math.round(t * 1000), h = Math.floor(ms / 3600000), m = Math.floor(ms / 60000) % 60, s2 = Math.floor(ms / 1000) % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s2).padStart(2, "0")},${String(ms % 1000).padStart(3, "0")}`; };
write(path.join(HERE, "captions.srt"), subs.map((c, i) => `${i + 1}\n${srtT(c.s)} --> ${srtT(c.s + c.d)}\n${c.text}\n`).join("\n"));
// chapter timestamps for the description (YouTube needs the first at 0:00)
write(path.join(HERE, "chapters.txt"), chapters.map((c, i) => `${i === 0 ? "0:00" : fmt(c.s)} ${c.label || "Intro"}`).join("\n"));
