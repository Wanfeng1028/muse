// Build a centered, timed hook-title ASS with one accent-coloured word.
// usage: node hook_ass.cjs "<title with *accent* word>" [fontFamily] [seconds]
// Accent colour, font, duration, position and safe-zone margins come from config.json.
const { load, assColor } = require('./lib_config.cjs');
const CFG = load();

const [, , rawTitle, fontArg, secArg] = process.argv;
const FONT = fontArg || CFG.font_family;
const seconds = Math.min(6, Math.max(2, parseFloat(secArg || CFG.hook_seconds)));
const POSY = CFG.hook_pos_y, SAFE = CFG.safe;

const WHITE = '&H00FFFFFF', BLACK = '&H00000000';
const ACC = assColor(CFG.hook_accent_color);
const esc = t => t.replace(/[{}\\]/g, '');

// extract the *accent* word (first marked); strip markers for wrapping
let accent = null;
const m = rawTitle.match(/\*([^*]+)\*/);
if (m) accent = m[1].trim();
const plain = rawTitle.replace(/\*/g, '');

// greedy wrap to <=16 chars/line, max 2 lines
const words = plain.split(/\s+/).filter(Boolean);
const lines = []; let cur = '';
for (const w of words) {
  if (cur && (cur.length + 1 + w.length) > 16) { lines.push(cur); cur = w; }
  else cur = cur ? cur + ' ' + w : w;
}
if (cur) lines.push(cur);
while (lines.length > 2) { lines[1] = lines[1] + ' ' + lines.pop(); }

const colourLine = line => {
  if (!accent) return esc(line);
  const re = new RegExp('\\b' + accent.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b');
  if (!re.test(line)) return esc(line);
  return esc(line).replace(esc(accent), `{\\c${ACC}&}${esc(accent)}{\\c${WHITE}&}`);
};
const text = lines.map(colourLine).join('\\N');

const cs = x => { const c = Math.round(x*100); const h = Math.floor(c/360000); const mm = Math.floor(c%360000/6000); const s = Math.floor(c%6000/100); const cc = c%100; return `${h}:${String(mm).padStart(2,'0')}:${String(s).padStart(2,'0')}.${String(cc).padStart(2,'0')}`; };

process.stdout.write(`[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,${FONT},88,${WHITE},${WHITE},${BLACK},&H80000000,1,0,0,0,100,100,0,0,1,7,5,8,${SAFE.left},${SAFE.right},${POSY},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,${cs(0)},${cs(seconds)},Hook,,0,0,0,,${text}
`);
