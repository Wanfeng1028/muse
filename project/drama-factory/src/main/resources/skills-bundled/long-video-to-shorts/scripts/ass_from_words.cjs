// Build ANIMATED ASS captions from a transcribe.py slice, in one of 8 selectable styles.
// usage: node ass_from_words.cjs <transcript.json> <startSec> <endSec> [fontFamily] [maxChars] [style]
// Most options come from config.json (accent colour, font family, position, safe zone);
// [style] overrides config.caption_style. Styles:
//   word-pop | capcut | clean | label | karaoke | one-word | boxed | bicolor
const fs = require('fs');
const { load, assColor } = require('./lib_config.cjs');
const CFG = load();

const [, , tp, s0, s1, fontArg, maxCharsArg, styleArg] = process.argv;
const start = parseFloat(s0), end = parseFloat(s1);
const FONT = fontArg || CFG.font_family;
const MAXCHARS = Math.max(6, parseInt(maxCharsArg || CFG.caption_max_chars, 10));
const STYLE = (styleArg || CFG.caption_style || 'word-pop').toLowerCase();
const POSY = CFG.caption_pos_y;
const SAFE = CFG.safe;

const WHITE = '&H00FFFFFF', BLACK = '&H00000000', DARK = '&H00141414';
const ACC = assColor(CFG.accent_color);

const data = JSON.parse(fs.readFileSync(tp, 'utf8'));
let words = (data.words || [])
  .map(w => ({ t: (w.text || '').trim(), a: w.start, b: w.end }))
  .filter(w => w.t && w.b > start && w.a < end)
  .map(w => ({ t: w.t, a: Math.max(0, w.a - start), b: Math.max(0.05, w.b - start) }));
const END = end - start;

const cs = x => { const c = Math.round(Math.max(0, x) * 100); const h = Math.floor(c/360000); const m = Math.floor(c%360000/6000); const s = Math.floor(c%6000/100); const cc = c%100; return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}.${String(cc).padStart(2,'0')}`; };
const esc = t => t.replace(/[{}\\]/g, '');
const UP = t => esc(t).toUpperCase();
const ANCHOR = `{\\an5\\pos(540,${POSY})}`;

function group(ws, n){ const L=[]; for(let i=0;i<ws.length;i+=n) L.push(ws.slice(i,i+n)); return L; }
function packByChars(ws, maxChars, maxWords){ const L=[]; let cur=[],len=0;
  for(const w of ws){ const add=(cur.length?1:0)+w.t.length;
    if(cur.length && (len+add>maxChars || cur.length>=maxWords)){ L.push(cur); cur=[]; len=0; }
    cur.push(w); len+=(cur.length>1?1:0)+w.t.length; }
  if(cur.length) L.push(cur); return L; }

// ordered per-word "active" states -> non-overlapping continuous events
function perWordStates(lines, mk, upper){ const S=[];
  for(const line of lines){ for(let i=0;i<line.length;i++){
    const txt=line.map((w,j)=>mk(upper?UP(w.t):esc(w.t), j===i)).join(' ');
    S.push({ a: line[i].a, text: txt }); } } return S; }
function statesToEvents(S){ const ev=[];
  for(let k=0;k<S.length;k++){ const a=S[k].a, b=(k<S.length-1)?S[k+1].a:END;
    if(b>a) ev.push(`Dialogue: 0,${cs(a)},${cs(b)},Cap,,0,0,0,,${ANCHOR}${S[k].text}`); }
  return ev; }

// style Format line uses MarginL/R from the safe zone
const ML = SAFE.left, MR = SAFE.right;
function styleDef(size, primary, outline, outlineW, shadow, borderStyle){
  return `Style: Cap,${FONT},${size},${primary},${WHITE},${outline},${BLACK},1,0,0,0,100,100,0,0,${borderStyle},${outlineW},${shadow},5,${ML},${MR},0,1`;
}

let styleLine, events;
switch (STYLE) {
  case 'capcut':
    styleLine = styleDef(96, WHITE, BLACK, 8, 4, 1);
    events = statesToEvents(perWordStates(group(words,3), (t,a)=> a?`{\\c${ACC}&}${t}{\\c${WHITE}&}`:t, true));
    break;
  case 'clean':
    styleLine = styleDef(84, WHITE, BLACK, 4, 4, 1);
    events = statesToEvents(perWordStates(group(words,3), (t,a)=> a?`{\\c${ACC}&}${t}{\\c${WHITE}&}`:t, false));
    break;
  case 'label':
    styleLine = styleDef(78, WHITE, DARK, 14, 0, 3);
    events = statesToEvents(perWordStates(group(words,3), (t,a)=> a?`{\\c${ACC}&}${t}{\\c${WHITE}&}`:t, false));
    break;
  case 'one-word':
    styleLine = styleDef(150, WHITE, BLACK, 10, 5, 1);
    events = statesToEvents(perWordStates(words.map(w=>[w]), (t)=>t, true));
    break;
  case 'boxed':
    styleLine = `Style: Cap,${FONT},128,${BLACK},${BLACK},${ACC},${BLACK},1,0,0,0,100,100,0,0,3,22,0,5,${ML},${MR},0,1`;
    events = statesToEvents(perWordStates(words.map(w=>[w]), (t)=>t, true));
    break;
  case 'karaoke': {
    // words start white and fill to the accent colour as spoken
    styleLine = `Style: Cap,${FONT},82,${ACC},${WHITE},${BLACK},&H99000000,1,0,0,0,100,100,0,0,1,5,2,5,${ML},${MR},0,1`;
    events = [];
    for(const line of group(words,3)){ const a=line[0].a,b=line[line.length-1].b;
      const txt=line.map(w=>{const k=Math.max(1,Math.round((w.b-w.a)*100));return `{\\kf${k}}${esc(w.t)} `;}).join('').trim();
      events.push(`Dialogue: 0,${cs(a)},${cs(b)},Cap,,0,0,0,,${ANCHOR}${txt}`); }
    break; }
  case 'bicolor': {
    styleLine = styleDef(84, WHITE, BLACK, 6, 3, 1);
    events = []; let gi=0;
    for(const line of group(words,3)){ const a=line[0].a,b=line[line.length-1].b;
      const txt=line.map(w=>`{\\c${(gi++%2===0)?WHITE:ACC}&}${esc(w.t)}`).join(' ');
      events.push(`Dialogue: 0,${cs(a)},${cs(b)},Cap,,0,0,0,,${ANCHOR}${txt}`); }
    break; }
  case 'word-pop':
  default:
    styleLine = styleDef(84, WHITE, BLACK, 6, 3, 1);
    events = statesToEvents(perWordStates(packByChars(words, MAXCHARS, 3),
      (t,a)=> a?`{\\fscx122\\fscy122\\c${ACC}&}${t}{\\fscx100\\fscy100\\c${WHITE}&}`:t, false));
    break;
}

process.stdout.write(`[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
${styleLine}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
${events.join('\n')}
`);
