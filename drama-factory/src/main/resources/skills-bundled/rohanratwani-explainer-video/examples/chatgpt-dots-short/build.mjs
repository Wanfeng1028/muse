// s01: ChatGPT Dots, a YouTube Short (1080x1920). News reaction, launched 2026-09-29.
//   node build.mjs                  -> silent cut (beats timed at reading pace) + vo/lines.json
//   node build.mjs --voice af_heart -> every beat timed to its Kokoro clip in vo/af_heart/
// Facts + sources: brief.md. Safe zone: content between 9cqh and 62cqh, captions at 66cqh,
// nothing in the bottom 22% (Shorts title + buttons) or the right 12% (like/comment rail).

import fs from "node:fs";
import path from "node:path";
import { timeBeats, subtitleChunks, page, write, ensureEdit } from "../../engine/core.mjs";

const HERE = path.dirname(new URL(import.meta.url).pathname).replace(/^\/([A-Za-z]:)/, "$1");
const VOICE = process.argv.includes("--voice") ? process.argv[process.argv.indexOf("--voice") + 1] : null;
const W = 1080, H = 1920, PX = W / 100, PY = H / 100;
const r2 = (n) => Math.round(n * 100) / 100;

// ============================================================ BEATS
const beats = [
  { id: "b01", text: "Your ChatGPT can now keep working after you close it.", hold: 0.2, v: "Text hook. Chat window closes and collapses into a peach dot that keeps working" },
  { id: "b02", text: "OpenAI just launched it at DevDay. It's called Dots.", hold: 0.3, v: "Task ticks appear under the dot, DevDay chip" },
  { id: "b03", text: "A dot is an agent with its own computer in the cloud.", v: "Dot wired to a cloud browser window, cursor working, GPT-6 Astra chip" },
  { id: "b04", text: "You give it a job. Watch for bugs. Track a budget. Chase an unpaid invoice.", hold: 0.2, v: "Three job cards land on each job" },
  { id: "b05", text: "It uses over 4,000 apps, then brings you the finished work to approve.", hold: 0.3, v: "App grid + 4,000 count, review card with Approve button" },
  { id: "b06", text: "But the smartest part isn't the agent. It's the brakes.", hold: 0.2, v: "Not the agent (struck through). The BRAKES" },
  { id: "b07", text: "A separate checker reviews risky moves. Passwords and money always come back to you.", hold: 0.4, v: "Flow: dot, auto-review gate, passwords + money locked, routed to YOU" },
  { id: "b08", text: "The catch? You need Pro, from $100 a month. Plus doesn't get it.", hold: 0.3, v: "Plan cards: Pro from $100 has dots, Plus $20 stamped NO DOTS" },
  { id: "b09", text: "Meta's Muse is a similar agent, with a free tier.", hold: 0.4, v: "Meta Muse card: free tier, launched 8 Sep" },
  { id: "b10", text: "Chatbots wait for you. Dots don't.", hold: 0.8, nosub: true, v: "Last line, big. DON'T in a peach pill" },
  { id: "b11", text: "Subscribe for more AI, explained simply.", hold: 1.6, nosub: true, v: "End card + handle" },
];

// what Kokoro says (same words, spelled to be pronounced right)
const say = (t) => t.replace(/\$100/g, "100 dollars").replace(/DevDay/g, "Dev Day").replace(/4,000/g, "four thousand");
write(path.join(HERE, "vo", "lines.json"), JSON.stringify(beats.map((b) => ({ id: b.id, say: say(b.text), text: b.text })), null, 1));
let voice = null;
if (VOICE) {
  const dir = path.join(HERE, "vo", VOICE);
  voice = { durations: JSON.parse(fs.readFileSync(path.join(dir, "durations.json"), "utf8")),
            words: JSON.parse(fs.readFileSync(path.join(dir, "words.json"), "utf8")) };
}
const { total, T, E, F, Wd } = timeBeats(beats, { voice, lead: 0.15, gap: 0.22, wps: 2.7, pad: 0.4 });

// ============================================================ BUILD HELPERS
let CSS = "", BODY = "", JS = "", track = 10;
const css = (s) => { CSS += s + "\n"; };
const js = (s) => { JS += s + "\n"; };
function scene(id, from, to, html, { exitAt = null, startAt = null } = {}) {
  const s = startAt ?? T(from), e = exitAt ?? E(to), d = r2(e - s);
  BODY += `<div class="set clip" id="${id}" data-start="${s}" data-duration="${d}" data-track-index="${track++}"><div class="stage" id="${id}-st">${html}</div></div>\n`;
  js(`tl.fromTo("#${id}-st", {scale:1}, {scale:1.03, duration:${d}, ease:"none"}, ${s});`);
  js(`tl.to("#${id}", {opacity:0, duration:0.22, ease:"power1.in"}, ${r2(e - 0.22)});`);
}
function sline(x1, y1, x2, y2, id, cls = "") {
  const len = r2(Math.hypot(x2 - x1, y2 - y1));
  return `<line id="${id}" class="${cls}" x1="${r2(x1)}" y1="${r2(y1)}" x2="${r2(x2)}" y2="${r2(y2)}" stroke-dasharray="${len}" stroke-dashoffset="${len}" data-len="${len}"/>`;
}
const svgWrap = (id, inner) => `<svg id="${id}" style="position:absolute;inset:0" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">${inner}</svg>`;
const P = (xcw, ych) => [xcw * PX, ych * PY];

css(`
.stage { position:absolute; inset:0; transform-origin:50% 40%; }
.hd { position:absolute; left:7cqw; right:7cqw; top:10.5cqh; text-align:center; font-size:8.6cqw; line-height:1.04; letter-spacing:-0.035em; }
.hd .pill { padding:0 0.32em 0.06em; }
.kick { position:absolute; left:0; right:0; top:7.6cqh; text-align:center; font-size:2.7cqw; color:var(--muted); }
.chip { display:inline-block; font-family:"JetBrains Mono"; font-weight:500; text-transform:uppercase; letter-spacing:0.1em; font-size:2.7cqw;
  padding:0.9cqw 2cqw; border-radius:999px; border:0.3cqw solid var(--fg); background:var(--surface); }
.card { border-width:0.4cqw; border-radius:3cqw; box-shadow:0 1cqw 0 var(--fg); }
.dot { position:absolute; border-radius:50%; background:var(--accent-strong); border:0.6cqw solid var(--fg); }
svg line { stroke:var(--fg); stroke-width:6; }
svg line.hot { stroke:var(--accent-strong); stroke-width:9; }
#brl1, #brl2 { opacity:0; }
.stamp { position:absolute; font-family:"JetBrains Mono"; font-weight:500; text-transform:uppercase; letter-spacing:0.12em;
  border:0.45cqw solid currentColor; border-radius:1.2cqw; padding:0.8cqw 1.8cqw; font-size:3.2cqw; }
.ctr { position:absolute; left:0; right:0; text-align:center; }
`);

// ============================================================ HOOK (b01-b02)
css(`
#hk-t { position:absolute; left:6cqw; right:6cqw; top:9.5cqh; text-align:center; }
#hk-t .l1 { font-size:13.4cqw; line-height:1; letter-spacing:-0.05em; }
#hk-t .l2 { font-size:6.6cqw; line-height:1.1; letter-spacing:-0.03em; margin-top:2cqw; }
#hk-t .l2 .pill { padding:0 0.3em 0.06em; }
#hk-chat { left:10cqw; top:31cqh; width:80cqw; padding:3.4cqw 4cqw; display:flex; flex-direction:column; gap:2.6cqw; transform-origin:50% 50%; }
#hk-chat > * { flex-shrink:0; }
.ch-h { display:flex; align-items:center; gap:2cqw; font-size:4.2cqw; padding-bottom:2cqw; border-bottom:0.25cqw solid rgba(22,21,19,0.15); }
.ch-h .g { width:2cqw; height:2cqw; border-radius:50%; background:#6fb36a; }
.ch-h .x { margin-left:auto; width:6.4cqw; height:6.4cqw; border-radius:50%; background:var(--fg); color:var(--bg); font-size:4cqw; line-height:6.4cqw; text-align:center; }
.bub { border-radius:3cqw; padding:2.2cqw 3.2cqw; font-size:4.6cqw; line-height:1.25; }
.bub.me { align-self:flex-end; background:var(--fg); color:#f7f2e6; border-bottom-right-radius:0.8cqw; }
.bub.ai { align-self:flex-start; background:var(--bg-deep); border-bottom-left-radius:0.8cqw; }
#hk-dot { left:41cqw; top:33.6cqh; width:18cqw; height:18cqw; }
#hk-ring { position:absolute; left:36cqw; top:30.8cqh; width:28cqw; height:28cqw; border-radius:50%; border:0.5cqw solid var(--accent-strong); opacity:0; }
#hk-st { top:45cqh; }
#hk-ticks { position:absolute; left:17cqw; top:49.5cqh; display:flex; flex-direction:column; gap:1.6cqw; }
.tk { display:flex; align-items:center; gap:2.4cqw; font-size:4.3cqw; }
.tk b { width:5.4cqw; height:5.4cqw; border-radius:50%; background:var(--sage); border:0.35cqw solid var(--fg); flex-shrink:0; position:relative; }
.tk b::after { content:""; position:absolute; left:1.3cqw; top:1.2cqw; width:2.2cqw; height:1.1cqw; border-left:0.5cqw solid var(--fg); border-bottom:0.5cqw solid var(--fg); transform:rotate(-45deg); }
#hk-dd { top:27cqh; }
`);
scene("s-hook", "b01", "b02", `
<div id="hk-t"><div class="l1">ChatGPT Dots</div><div class="l2">keep working after you <span class="serif pill">leave</span></div></div>
<div class="card" id="hk-chat">
  <div class="ch-h"><span class="g"></span><span>ChatGPT</span><span class="x" id="hk-x">×</span></div>
  <div class="bub me" id="hk-q">Chase my unpaid invoices</div>
  <div class="bub ai" id="hk-a">On it. I'll keep going.</div>
</div>
<div id="hk-ring"></div>
<div class="dot" id="hk-dot"></div>
<div class="ctr" id="hk-st"><span class="chip" style="background:var(--butter)">still working</span></div>
<div id="hk-ticks">
  <div class="tk" id="tk1"><b></b>Checked the inbox</div>
  <div class="tk" id="tk2"><b></b>Found 2 late invoices</div>
  <div class="tk" id="tk3"><b></b>Drafted the reminders</div>
</div>
<div class="ctr" id="hk-dd"><span class="chip">OpenAI DevDay · 29 Sep 2026</span></div>`, { startAt: 0 });
{
  const close = Wd("b01", 9);
  js(`
land("#hk-a", ${Math.max(0.9, F("b01", 0.35))}, {from:0.9, y:14});
tl.to("#hk-x", {scale:1.3, backgroundColor:"#e07a45", duration:0.16, ease:"power2.out"}, ${r2(close - 0.25)});
tl.to("#hk-x", {scale:1, duration:0.14, ease:"power2.in"}, ${r2(close - 0.09)});
tl.to("#hk-chat", {scale:0.1, opacity:0, borderRadius:"50%", duration:0.42, ease:"power3.in"}, ${r2(close)});
land("#hk-dot", ${r2(close + 0.32)}, {from:0, ease:"back.out(2.4)", d:0.5});
tl.fromTo("#hk-ring", {opacity:0.9, scale:0.6}, {opacity:0, scale:1.35, duration:1.1, ease:"power2.out", immediateRender:false}, ${r2(close + 0.55)});
tl.fromTo("#hk-ring", {opacity:0.9, scale:0.6}, {opacity:0, scale:1.35, duration:1.1, ease:"power2.out", immediateRender:false}, ${r2(close + 1.7)});
tl.fromTo("#hk-ring", {opacity:0.9, scale:0.6}, {opacity:0, scale:1.35, duration:1.1, ease:"power2.out", immediateRender:false}, ${r2(close + 2.85)});
fade("#hk-st", ${r2(close + 0.7)});
rise("#tk1", ${r2(close + 1.0)}, {y:16});
rise("#tk2", ${Wd("b02", 2)}, {y:16});
rise("#tk3", ${Wd("b02", 7)}, {y:16});
land("#hk-dd", ${Wd("b02", 5)}, {from:0.8});
tl.to("#hk-dot", {scale:1.22, duration:0.18, ease:"power2.out"}, ${Wd("b02", 9)});
tl.to("#hk-dot", {scale:1, duration:0.3, ease:"back.out(2)"}, ${r2(Wd("b02", 9) + 0.18)});
`);
}

// ============================================================ COMPUTER (b03)
css(`
#cp-dot { left:44cqw; top:25.4cqh; width:12cqw; height:12cqw; }
#cp-win { left:8cqw; top:37cqh; width:84cqw; height:24cqh; overflow:hidden; padding:0; }
.cp-tabs { display:flex; gap:1cqw; padding:2cqw 2.4cqw 0; background:var(--bg-deep); border-bottom:0.3cqw solid var(--fg); }
.cp-tabs span { font-family:"JetBrains Mono"; font-size:2.6cqw; padding:1cqw 1.8cqw; border:0.3cqw solid var(--fg); border-bottom:none; border-radius:1.2cqw 1.2cqw 0 0; background:var(--bg); opacity:0.6; }
.cp-tabs span.on { background:var(--surface); opacity:1; }
.cp-url { margin:2cqw 2.4cqw; font-family:"JetBrains Mono"; font-size:2.7cqw; padding:1cqw 2cqw; border-radius:999px; background:var(--bg); border:0.25cqw solid rgba(22,21,19,0.3); }
.cp-row { margin:0 2.4cqw 1.6cqw; display:flex; align-items:center; gap:2cqw; font-size:3.4cqw; }
.cp-row i { flex:1; height:1.1cqw; background:rgba(22,21,19,0.18); border-radius:1cqw; }
.cp-row .tag { font-family:"JetBrains Mono"; font-size:2.5cqw; padding:0.5cqw 1.4cqw; border-radius:999px; background:var(--accent); }
#cp-cur { position:absolute; left:60cqw; top:50cqh; width:0; height:0; border-left:2.2cqw solid transparent; border-right:2.2cqw solid transparent; border-bottom:4.4cqw solid var(--fg); }
#cp-cl { top:33.5cqh; }
#cp-ax { top:auto; bottom:2.6cqw; }
`);
{
  const [x1, y1] = P(50, 31.6), [x2, y2] = P(50, 36.6);
  scene("s-comp", "b03", "b03", `
<div class="hd" id="cp-hd">An agent with its own <span class="serif pill">computer</span></div>
${svgWrap("cp-svg", sline(x1, y1, x2, y2, "cp-l"))}
<div class="dot" id="cp-dot"></div>
<div class="card" id="cp-win">
  <div class="cp-tabs"><span class="on">inbox</span><span>invoices.xlsx</span><span>billing</span></div>
  <div class="cp-url">cloud-computer://your-dot</div>
  <div class="cp-row"><span>Acme Co.</span><i></i><span class="tag">late</span></div>
  <div class="cp-row"><span>Northwind</span><i></i><span class="tag" style="background:var(--sage)">paid</span></div>
  <div class="cp-row"><span>Globex</span><i></i><span class="tag">late</span></div>
  <div class="ctr" id="cp-ax" style="opacity:0"><span class="chip" style="background:var(--butter)">runs on GPT-6 Astra</span></div>
</div>
<div id="cp-cur"></div>`);
  js(`
rise("#cp-hd", ${T("b03")}, {y:24});
land("#cp-dot", ${T("b03") + 0.1}, {from:0, ease:"back.out(2.2)"});
draw("#cp-l", ${Wd("b03", 4)}, {d:0.3});
land("#cp-win", ${Wd("b03", 6)}, {from:0.94, y:24});
fade("#cp-cur", ${Wd("b03", 9)}, {d:0.2});
tl.fromTo("#cp-cur", {x:0, y:0}, {x:${-26 * PX}, y:${-3 * PY}, duration:0.7, ease:"power2.inOut"}, ${r2(Wd("b03", 9) + 0.1)});
tl.to("#cp-cur", {x:${-8 * PX}, y:${4.2 * PY}, duration:0.6, ease:"power2.inOut"}, ${r2(Wd("b03", 9) + 0.9)});
fade("#cp-ax", ${F("b03", 0.85)});
`);
}

// ============================================================ JOBS (b04)
css(`
.job { left:9cqw; width:82cqw; height:8.6cqh; padding:0 4cqw; display:flex; align-items:center; gap:3.4cqw; }
.job .n { font-family:"JetBrains Mono"; font-size:3.4cqw; background:var(--fg); color:var(--bg); border-radius:1.2cqw; padding:0.6cqw 1.4cqw; }
.job .t { font-size:5.4cqw; letter-spacing:-0.02em; }
.job .s { margin-left:auto; font-family:"JetBrains Mono"; text-transform:uppercase; letter-spacing:0.08em; font-size:2.6cqw; padding:0.8cqw 1.6cqw; border-radius:999px; border:0.3cqw solid var(--fg); }
#jb1 { top:27cqh; } #jb2 { top:38.5cqh; } #jb3 { top:50cqh; }
`);
scene("s-jobs", "b04", "b04", `
<div class="hd" id="jb-hd">You give it a <span class="serif pill">job</span></div>
<div class="card job" id="jb1"><span class="n">01</span><span class="t">Watch for bugs</span><span class="s" style="background:var(--butter)">watching</span></div>
<div class="card job" id="jb2"><span class="n">02</span><span class="t">Track a budget</span><span class="s" style="background:var(--sage)">tracking</span></div>
<div class="card job" id="jb3"><span class="n">03</span><span class="t">Chase an invoice</span><span class="s" style="background:var(--accent)">chasing</span></div>`);
js(`
rise("#jb-hd", ${T("b04")}, {y:24});
land("#jb1", ${Wd("b04", 5)}, {from:0.92, y:26});
land("#jb2", ${Wd("b04", 8)}, {from:0.92, y:26});
land("#jb3", ${Wd("b04", 11)}, {from:0.92, y:26});
`);

// ============================================================ APPS + REVIEW (b05)
const tileCols = ["#f0c860", "#f0a87a", "#a9c79b", "#bdb2ea", "#faf6ec", "#ece2c9"];
const letters = "MCSDNGTJFBKLPRWHQV";
css(`
#ap-grid { position:absolute; left:11cqw; top:27cqh; width:78cqw; display:grid; grid-template-columns:repeat(6, 1fr); gap:2.6cqw; }
#ap-grid i { display:block; height:10.6cqw; border-radius:2.6cqw; border:0.35cqw solid var(--fg); font-style:normal; font-size:4.2cqw; text-align:center; line-height:9.9cqw; }
#ap-n { font-variant-numeric:tabular-nums; }
#ap-rv { left:8cqw; top:43.5cqh; width:84cqw; padding:3.4cqw 4cqw; display:flex; flex-direction:column; gap:2cqw; }
#ap-rv .k { font-family:"JetBrains Mono"; text-transform:uppercase; letter-spacing:0.1em; font-size:2.7cqw; color:var(--muted); }
#ap-rv .b { font-size:4.6cqw; line-height:1.22; }
#ap-rv .row { display:flex; gap:2.4cqw; margin-top:0.6cqw; }
#ap-rv .btn { font-size:4.2cqw; padding:1.4cqw 4.4cqw; border-radius:999px; border:0.35cqw solid var(--fg); }
#ap-ok { background:var(--fg); color:var(--bg); }
`);
scene("s-apps", "b05", "b05", `
<div class="hd" id="ap-hd">Over <span id="ap-n">0</span> <span class="serif pill">apps</span></div>
<div id="ap-grid">${Array.from({ length: 12 }, (_, i) => `<i style="background:${tileCols[(i * 5) % 6]}">${letters[i]}</i>`).join("")}</div>
<div class="card" id="ap-rv"><span class="k">Ready for your review</span><span class="b">Reminder email to Acme Co. for invoice #1042</span>
<div class="row"><span class="btn" id="ap-ok">Approve</span><span class="btn">Edit</span></div></div>`);
js(`
rise("#ap-hd", ${T("b05")}, {y:24});
land("#ap-grid i", ${T("b05") + 0.15}, {from:0.4, st:0.035, ease:"back.out(2)"});
count("#ap-n", 4000, ${T("b05") + 0.1}, ${r2(Math.max(0.8, Wd("b05", 4) - T("b05") - 0.1))}, function(n){ return Math.round(n).toLocaleString("en-US"); });
tl.to("#ap-grid", {opacity:0.35, duration:0.3}, ${Wd("b05", 6)});
land("#ap-rv", ${Wd("b05", 6)}, {from:0.94, y:40});
tl.to("#ap-ok", {scale:1.12, backgroundColor:"#e07a45", duration:0.2, ease:"power2.out"}, ${Wd("b05", 13)});
tl.to("#ap-ok", {scale:1, duration:0.25, ease:"back.out(2)"}, ${r2(Wd("b05", 13) + 0.2)});
`);

// ============================================================ BRAKES (b06-b07)
css(`
#br-0 { position:absolute; left:0; right:0; top:12cqh; text-align:center; font-size:7cqw; letter-spacing:-0.03em; }
#br-a { position:absolute; left:0; right:0; top:24cqh; text-align:center; font-size:10cqw; letter-spacing:-0.04em; line-height:1.05; }
#br-a .not { position:relative; display:inline-block; color:var(--muted); }
#br-strike { position:absolute; left:-2%; top:52%; width:104%; height:1.1cqw; background:var(--accent-strong); border-radius:1cqw; transform-origin:0 50%; }
#br-b { position:absolute; left:0; right:0; top:37cqh; text-align:center; font-size:14cqw; letter-spacing:-0.05em; line-height:1; }
#br-b .pill { padding:0 0.28em 0.08em; }
#br-top { position:absolute; left:0; right:0; top:10.5cqh; text-align:center; font-size:8.6cqw; letter-spacing:-0.035em; opacity:0; }
#br-top .pill { padding:0 0.32em 0.06em; }
#br-dot { left:45cqw; top:22.8cqh; width:10cqw; height:10cqw; }
#br-gate { left:18cqw; top:32cqh; width:64cqw; padding:2.6cqw 3cqw; text-align:center; }
#br-gate .k { font-family:"JetBrains Mono"; text-transform:uppercase; letter-spacing:0.12em; font-size:3.6cqw; }
#br-gate .s { font-size:3.8cqw; color:var(--muted); margin-top:0.8cqw; }
.lk { position:absolute; top:44cqh; width:36cqw; padding:2.2cqw 0; text-align:center; font-family:"JetBrains Mono"; text-transform:uppercase; letter-spacing:0.1em; font-size:3.4cqw;
  background:var(--butter); border:0.4cqw solid var(--fg); border-radius:2cqw; }
#br-pw { left:9cqw; } #br-mn { left:55cqw; }
#br-you { position:absolute; left:32cqw; top:54.5cqh; width:36cqw; padding:2.4cqw 0; text-align:center; font-size:6cqw; letter-spacing:-0.02em;
  background:var(--fg); color:var(--bg); border-radius:999px; }
`);
{
  const L = [
    sline(...P(27, 50.2), ...P(42, 54.7), "brl1", "hot"),
    sline(...P(73, 50.2), ...P(58, 54.7), "brl2", "hot"),
  ];
  scene("s-brakes", "b06", "b07", `
<div id="br-0">The smartest part</div>
<div id="br-a"><span class="not">Not the agent.<span id="br-strike"></span></span></div>
<div id="br-b">The <span class="serif pill" id="br-pill">brakes</span>.</div>
<div id="br-top">The <span class="serif pill">brakes</span></div>
${svgWrap("br-svg", L.join(""))}
<div class="dot" id="br-dot" style="opacity:0"></div>
<div class="card" id="br-gate" style="opacity:0"><div class="k">Auto-review</div><div class="s">a separate checker</div></div>
<div class="lk" id="br-pw" style="opacity:0">Passwords</div>
<div class="lk" id="br-mn" style="opacity:0">Money</div>
<div id="br-you" style="opacity:0">you</div>`);
  js(`
rise("#br-0", ${T("b06")}, {y:24});
rise("#br-a", ${Wd("b06", 4)}, {y:24});
tl.fromTo("#br-strike", {scaleX:0}, {scaleX:1, duration:0.35, ease:"power2.inOut"}, ${Wd("b06", 6)});
rise("#br-b", ${Wd("b06", 7)}, {y:30});
land("#br-pill", ${Wd("b06", 9)}, {from:0.6, ease:"back.out(2.2)"});
exit("#br-0, #br-a, #br-b", ${T("b07")}, {y:-30});
fade("#br-top", ${r2(T("b07") + 0.15)});
land("#br-dot", ${r2(T("b07") + 0.2)}, {from:0, ease:"back.out(2.2)"});
land("#br-gate", ${Wd("b07", 1)}, {from:0.92, y:20});
land("#br-pw", ${Wd("b07", 6)}, {from:0.85, y:16});
land("#br-mn", ${Wd("b07", 8)}, {from:0.85, y:16});
tl.set("#brl1, #brl2", {opacity:1}, ${Wd("b07", 10)});
draw("#brl1, #brl2", ${Wd("b07", 10)}, {d:0.35});
land("#br-you", ${Wd("b07", 12)}, {from:0.7, ease:"back.out(2.2)"});
`);
}

// ============================================================ PRICE + MUSE (b08-b09)
css(`
.pl { top:25cqh; width:39cqw; height:21cqh; padding:3cqw; display:flex; flex-direction:column; gap:1.2cqw; }
#pl-pro { left:7cqw; } #pl-plus { left:54cqw; }
.pl .k { font-family:"JetBrains Mono"; text-transform:uppercase; letter-spacing:0.12em; font-size:3cqw; color:var(--muted); }
.pl .h { font-size:9cqw; letter-spacing:-0.04em; line-height:1; }
.pl .s { font-size:3.6cqw; color:var(--muted); }
.pl .ok { margin-top:auto; align-self:flex-start; font-size:2.6cqw; background:var(--sage); }
#pl-st-w { position:absolute; left:63cqw; top:40.2cqh; transform:rotate(-8deg); }
#pl-st { color:var(--accent-strong); background:var(--surface); }
#mu { left:7cqw; top:49cqh; width:86cqw; padding:3cqw 4cqw; display:flex; align-items:center; gap:3cqw; }
#mu .h { font-size:6.2cqw; letter-spacing:-0.03em; }
#mu .s { font-family:"JetBrains Mono"; text-transform:uppercase; letter-spacing:0.08em; font-size:2.5cqw; color:var(--muted); margin-top:0.6cqw; }
#mu .free { margin-left:auto; font-size:3.4cqw; padding:1.2cqw 2.6cqw; border-radius:999px; background:var(--butter); border:0.35cqw solid var(--fg); white-space:nowrap; }
`);
scene("s-price", "b08", "b09", `
<div class="hd" id="pl-hd">The <span class="serif pill">catch</span></div>
<div class="card pl" id="pl-pro"><span class="k">ChatGPT Pro</span><span class="h" id="pl-n">$0</span><span class="s">a month, and up</span><span class="chip ok">dots included</span></div>
<div class="card pl" id="pl-plus"><span class="k">ChatGPT Plus</span><span class="h">$20</span><span class="s">a month</span></div>
<div id="pl-st-w"><div class="stamp" id="pl-st">no dots</div></div>
<div class="card" id="mu"><div><div class="h">Meta Muse</div><div class="s">similar agent · out since 8 Sep</div></div><span class="free">free tier</span></div>`);
js(`
rise("#pl-hd", ${T("b08")}, {y:24});
land("#pl-pro", ${Wd("b08", 4)}, {from:0.92, y:26});
count("#pl-n", 100, ${Wd("b08", 5)}, 0.6, function(n){ return "$" + Math.round(n); });
land("#pl-plus", ${Wd("b08", 9)}, {from:0.92, y:26});
land("#pl-st", ${Wd("b08", 10)}, {from:1.6, ease:"back.out(1.6)", d:0.35});
land("#mu", ${T("b09")}, {from:0.92, y:30});
land("#mu .free", ${Wd("b09", 8)}, {from:0.6, ease:"back.out(2.2)"});
`);

// ============================================================ LAST LINE (b10) + END (b11)
css(`
#ll { position:absolute; left:0; right:0; top:24cqh; text-align:center; }
#ll .a { font-size:10.6cqw; letter-spacing:-0.045em; line-height:1.05; color:var(--muted); }
#ll .b { font-size:15cqw; letter-spacing:-0.05em; line-height:1; margin-top:4cqw; }
#ll .pill { padding:0 0.26em 0.08em; }
#ll-dot { left:44cqw; top:52cqh; width:12cqw; height:12cqw; }
#end { position:absolute; left:0; right:0; top:27cqh; display:flex; flex-direction:column; align-items:center; gap:4cqw; }
#end .h { font-size:15cqw; letter-spacing:-0.05em; line-height:1; }
#end .s { font-size:7cqw; text-align:center; line-height:1.15; }
#end .hd2 { font-size:3.6cqw; padding:1.4cqw 3.4cqw; border-radius:999px; background:var(--fg); color:var(--bg); letter-spacing:0.06em; text-transform:none; }
`);
scene("s-last", "b10", "b10", `
<div id="ll"><div class="a" id="ll-a">Chatbots wait<br>for you.</div><div class="b" id="ll-b">Dots <span class="serif pill" id="ll-p">don't.</span></div></div>
<div class="dot" id="ll-dot"></div>`);
js(`
rise("#ll-a", ${T("b10")}, {y:26});
rise("#ll-b", ${Wd("b10", 4)}, {y:30});
land("#ll-p", ${Wd("b10", 5)}, {from:0.6, ease:"back.out(2.2)"});
land("#ll-dot", ${r2(Wd("b10", 5) + 0.3)}, {from:0, ease:"back.out(2.4)"});
`);
scene("s-end", "b11", "b11", `
<div id="end"><div class="h" id="end-h">Subscribe</div><div class="serif s" id="end-s">for more AI,<br>explained <span class="pill">simply</span></div><div class="mono hd2" id="end-hd">@yourchannel</div></div>`, { exitAt: total });
js(`
rise("#end-h", ${T("b11")}, {y:30, d:0.5});
rise("#end-s", ${T("b11") + 0.25}, {y:16});
land("#end-hd", ${T("b11") + 0.6}, {from:0.7});
`);

// ============================================================ WRITE
const subs = subtitleChunks(beats.filter((b) => !b.nosub), { maxWords: 4 });
ensureEdit(path.join(HERE, "edit"));
write(path.join(HERE, "edit", "index.html"), page({ total, css: CSS, body: BODY, js: JS, chapters: [], subs, w: W, h: H, vertical: true }));
const fmt = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
write(path.join(HERE, "script.md"), `# s01 · ChatGPT Dots (Short) · scene table

Generated by \`build.mjs\`. Runtime **${fmt(total)}** (${total}s), ${beats.length} beats, ${beats.reduce((a, b) => a + b.words, 0)} words.

| Time | Narration | On screen |
|---|---|---|
${beats.map((b) => `| ${fmt(b.start)} | ${b.text} | ${b.v} |`).join("\n")}
`);
write(path.join(HERE, "beats.json"), JSON.stringify(beats.map(({ id, start, end, dur, words }) => ({ id, start, end, dur, words })), null, 1));
write(path.join(HERE, "total.txt"), String(total));
const srtT = (t) => { const ms = Math.round(t * 1000), h = Math.floor(ms / 3600000), m = Math.floor(ms / 60000) % 60, s2 = Math.floor(ms / 1000) % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s2).padStart(2, "0")},${String(ms % 1000).padStart(3, "0")}`; };
const allSubs = subtitleChunks(beats, { maxWords: 7 });
write(path.join(HERE, "captions.srt"), allSubs.map((c, i) => `${i + 1}\n${srtT(c.s)} --> ${srtT(c.s + c.d)}\n${c.text}\n`).join("\n"));
console.log(`built: ${beats.length} beats, ${subs.length} caption chunks, ${fmt(total)} (${total}s), ${track - 10} layers`);
