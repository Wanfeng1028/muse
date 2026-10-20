// Turn ElevenLabs VO word-timestamps into VO-synced timing:
//   • each scene's duration follows its narration length (tight, no dead air)
//   • each cue (a card raise, a caption, a sound) lands ON the word that names it
//
// Inputs (from `elevenlabs.py tts script.json vo --voice ...`):
//   vo/alignments.json  = { sceneId: { chars:[...], start:[...] } }   per-character start times
//   vo/durations.json   = { sceneId: seconds }
//
// Output: timing.json = { total, head, scenes:[{id,start,dur,cues:[{key,at}]}] }
//   `at` is seconds from scene start (== head + word time, since the VO starts at `head`).
//   Feed `at` to your animation engine, and to an audio event list (see the audio-stems skill)
//   so an SFX/cue fires exactly when the word is spoken.
//
// Adapt the CONFIG below to your project: scene order + which word each cue should land on.
const fs = require('fs');
const AL = JSON.parse(fs.readFileSync('vo/alignments.json'));
const DUR = JSON.parse(fs.readFileSync('vo/durations.json'));

const HEAD = 0.3;   // VO starts this many seconds into each scene (headline reads first)
const TAIL = 0.5;   // breathing room after the VO before the scene ends
const MIN  = {};    // optional per-scene minimum dur (e.g. an outro that must hold)

// scene order + cue→keyword map. Cue keys are yours; keyword is searched (case-insensitive)
// in that scene's VO text. Unmatched/absent cues can be spread (see interpolation note).
const CONFIG = [
  { id: 'intro',   cues: [] },
  { id: 'feature', cues: [ ['cardA','search'], ['cardB','memory'], ['cardC','inference'] ] },
  { id: 'outro',   cues: [] },
];

// start time (sec) of the nth occurrence of `word` within a scene's VO
function wordTime(id, word, occ = 0){
  const a = AL[id]; if(!a) throw new Error('no alignment for '+id);
  const s = a.chars.join('').toLowerCase(), w = word.toLowerCase();
  let i = -1; for(let n=0;n<=occ;n++){ i = s.indexOf(w, i+1); if(i<0) throw new Error(`"${word}" not in ${id}`); }
  return a.start[i];
}

let t = 0; const scenes = [];
for(const sc of CONFIG){
  const vo = DUR[sc.id] || 0;
  const cues = sc.cues.map(([key,word]) => ({ key, at: +(HEAD + wordTime(sc.id, word)).toFixed(3) }))
                      .sort((a,b)=>a.at-b.at);
  const lastCue = cues.length ? cues[cues.length-1].at : 0;
  const dur = +Math.max(HEAD + vo + TAIL, lastCue + 1.0, MIN[sc.id] || 0).toFixed(2);
  scenes.push({ id: sc.id, start: +t.toFixed(3), dur, cues });
  t += dur;
}
fs.writeFileSync('timing.json', JSON.stringify({ total: +t.toFixed(3), head: HEAD, scenes }, null, 1));
console.log('TOTAL', +t.toFixed(2), 's');
for(const s of scenes) console.log(s.id.padEnd(12), 'start', String(s.start).padStart(6), 'dur', String(s.dur).padStart(6),
  s.cues.map(c=>`${c.key}@${c.at}`).join(' '));

// Spreading unnamed cues: if a scene has more cards than named words, anchor the named ones on
// their word and distribute the rest evenly between anchors (linear interpolate the `at` values),
// keeping the cards' engine order. Snap-to-instant (e.g. a list turning green at once): set all
// those cues to ~the same `at` (the word that triggers them) + tiny 0.06s increments.
