// Build the film's timeline from the voiceover's word timestamps.
//
// INPUT   vo/alignments.json  { "<sceneId>": { chars:[…], start:[…] } }   (character-level alignment,
//                               as ElevenLabs /with-timestamps returns it; word-level works too)
//         vo/durations.json   { "<sceneId>": <clip length in seconds> }
//         the CONFIG table below (ORDER IS THE TIMELINE — a scene's position is its index)
//
// OUTPUT  timing.json    { total, head, scenes:[{ id, start, dur, vo, head, cues:[{key,at}], words:[…] }] }
//         timing.js      window.__TIMING = <the same object>      (the page reads cues from this)
//         vo_events.json { total, events:[{t, clip, gain}] }       (rebuild a VO bed from per-scene clips)
//         captions.js    window.__CAPS = [{s, e, text, scene}]     (sentence captions)
//
//   node compute_timing.js                 # full film
//   CUT=t_ch4,ch4 node compute_timing.js   # same film with those scenes spliced out (short cut)
//
// The rule that matters: dur = max(HEAD + voLength + TAIL, lastCue + 1.0, MIN[id]).
// The `lastCue + 1.0` term ends every chapter one second after its last spoken word.

const fs = require('fs');
const path = require('path');

const VODIR = process.env.VODIR || 'vo';
const OUTDIR = process.env.OUTDIR || '.';
const AL  = JSON.parse(fs.readFileSync(path.join(VODIR, 'alignments.json'), 'utf8'));
const DUR = JSON.parse(fs.readFileSync(path.join(VODIR, 'durations.json'), 'utf8'));

// ---- knobs -----------------------------------------------------------------
const HEAD = 0.45;                       // default silence before a scene's clip starts
const TAIL = 0.70;                       // default silence after it
const HEADS = {                          // per-scene overrides: title cards need the mark to land first
  // t_ch1: 0.7, close: 2.0,
};
const TAILS = {
  // t_ch1: 0.15, close: 2.4,
};
const MIN = {                            // floors where the action outruns the voice (a live run, a
  // ch1: 25.8, t_ch1: 2.4,              // scrolling list, a report that must stay readable)
};

// ---- the timeline ----------------------------------------------------------
// Each cue is [key, spokenWord, occurrenceIndex?]. The key is what the page asks for; the word is
// matched (case-insensitively) inside the scene's alignment text. Scenes with no cues still take a slot.
const CONFIG = [
  { id: 'hook',   cues: [['open', 'racing'], ['payoff', 'everywhere']] },
  { id: 'intro',  cues: [['meet', 'Meet'], ['name', '<product>'], ['tag', 'trust layer']] },
  { id: 't_ch1',  cues: [] },
  { id: 'ch1',    cues: [['start', 'Red team'], ['byo', 'Bring your own'], ['report', 'report']] },
  { id: 't_ch2',  cues: [] },
  { id: 'ch2',    cues: [['count', 'thirty two'], ['real', 'real time']] },
  { id: 'roll',   cues: [['many', 'many more']] },
  { id: 'close',  cues: [['name', '<product>'], ['tag', 'tagline word']] },
];

const CUT = (process.env.CUT || '').split(',').filter(Boolean);
if (CUT.length) {
  for (let i = CONFIG.length - 1; i >= 0; i--) if (CUT.includes(CONFIG[i].id)) CONFIG.splice(i, 1);
  console.log('CUT', CUT.join(' '));
}

// ---- word lookup -----------------------------------------------------------
function wordTime(id, word, occ = 0) {
  const a = AL[id];
  if (!a) throw new Error(`no alignment for scene "${id}"`);
  const s = a.chars.join('').toLowerCase(), w = word.toLowerCase();
  let i = -1;
  for (let n = 0; n <= occ; n++) { i = s.indexOf(w, i + 1); if (i < 0) throw new Error(`"${word}" not in ${id}`); }
  return a.start[i];
}

// ---- scenes ----------------------------------------------------------------
let t = 0;
const scenes = [];
for (const sc of CONFIG) {
  const vo = DUR[sc.id] || 0;                       // 0 for a silent scene
  const H = HEADS[sc.id] ?? HEAD;
  const cues = sc.cues
    .map(([key, word, occ]) => ({ key, at: +(H + wordTime(sc.id, word, occ || 0)).toFixed(3) }))
    .sort((a, b) => a.at - b.at);
  const lastCue = cues.length ? cues[cues.length - 1].at : 0;
  const dur = +Math.max(H + vo + (TAILS[sc.id] ?? TAIL), lastCue + 1.0, MIN[sc.id] || 0).toFixed(2);

  // per-word times, for scenes whose headline lands word by word on the voice
  const words = [];
  if (AL[sc.id]) {
    const a = AL[sc.id], txt = a.chars.join('');
    let i = 0;
    for (const w of txt.split(' ')) {
      const k = txt.indexOf(w, i);
      if (k >= 0) { words.push({ w, at: +(H + a.start[k]).toFixed(3) }); i = k + w.length; }
    }
  }
  scenes.push({ id: sc.id, start: +t.toFixed(3), dur, vo: +vo.toFixed(2), head: H, cues, words });
  t += dur;
}

const out = { total: +t.toFixed(3), head: HEAD, scenes };
fs.writeFileSync(path.join(OUTDIR, 'timing.json'), JSON.stringify(out, null, 1));
fs.writeFileSync(path.join(OUTDIR, 'timing.js'), 'window.__TIMING=' + JSON.stringify(out) + ';');
console.log('TOTAL', +t.toFixed(2), 's');
for (const s of scenes) {
  console.log(s.id.padEnd(10), 'start', String(s.start).padStart(8), 'dur', String(s.dur).padStart(6),
              'vo', String(s.vo).padStart(6), '|', s.cues.map(c => `${c.key}@${c.at}`).join(' '));
}

// ---- VO bed events (only scenes that actually speak) -----------------------
const ev = {
  total: out.total,
  events: scenes.filter(s => s.vo > 0).map(s => ({
    t: +(s.start + s.head).toFixed(3),
    clip: String(scenes.indexOf(s) + 1).padStart(2, '0') + '_' + s.id,
    gain: 1.0,
  })),
};
fs.writeFileSync(path.join(OUTDIR, 'vo_events.json'), JSON.stringify(ev, null, 1));

// ---- captions: one per sentence, long ones halved at the nearest comma -----
const caps = [];
for (const s of scenes) {
  const a = AL[s.id];
  if (!a) continue;                                  // silent scene: skip, or the loop throws
  const text = a.chars.join(''), st = a.start;
  const parts = [];
  let cur = 0;
  for (let i = 0; i < text.length; i++) {
    if (/[.?:;]/.test(text[i]) && (i === text.length - 1 || text[i + 1] === ' ')) { parts.push([cur, i]); cur = i + 1; }
  }
  if (cur < text.length - 1) parts.push([cur, text.length - 1]);
  for (let [a0, b0] of parts) {
    while (a0 < b0 && text[a0] === ' ') a0++;
    const segTxt = text.slice(a0, b0 + 1).trim();
    if (!segTxt) continue;
    const pieces = [];
    if (segTxt.length > 78) {
      const mid = Math.floor(segTxt.length / 2);
      let k = -1, best = 1e9;
      for (let i = 0; i < segTxt.length; i++) if (segTxt[i] === ',' && Math.abs(i - mid) < best) { best = Math.abs(i - mid); k = i; }
      if (k > 0) { pieces.push([a0, a0 + k]); pieces.push([a0 + k + 1, b0]); } else pieces.push([a0, b0]);
    } else pieces.push([a0, b0]);
    for (let [x, y] of pieces) {
      while (x < y && text[x] === ' ') x++;
      const tx = text.slice(x, y + 1).trim();
      if (!tx) continue;
      caps.push({
        s: +(s.start + s.head + st[x]).toFixed(3),
        e: +(s.start + s.head + st[Math.min(y, st.length - 1)] + 0.45).toFixed(3),
        text: tx, scene: s.id,
      });
    }
  }
}
for (let i = 0; i < caps.length - 1; i++) if (caps[i].e > caps[i + 1].s - 0.05) caps[i].e = +(caps[i + 1].s - 0.05).toFixed(3);
fs.writeFileSync(path.join(OUTDIR, 'captions.js'), 'window.__CAPS=' + JSON.stringify(caps) + ';');
console.log('captions', caps.length);
