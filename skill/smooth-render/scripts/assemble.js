// Build an ffmpeg concat list from frames.json (per-frame durations = logical-time diffs).
// The final frame is held until TOTAL, which naturally pads the static outro tail.
const fs = require('fs');
const path = require('path');
const dir = process.argv[2] || 'frames';
const { frames, total } = JSON.parse(fs.readFileSync(path.join(dir, 'frames.json')));
let out = '';
for (let i = 0; i < frames.length; i++) {
  const next = (i + 1 < frames.length) ? frames[i + 1] : total;
  const dur = Math.max(0.001, next - frames[i]);
  out += `file 'f${String(i).padStart(6,'0')}.jpg'\n`;
  out += `duration ${dur.toFixed(4)}\n`;
}
// concat demuxer requires the last file repeated (its duration is ignored)
out += `file 'f${String(frames.length-1).padStart(6,'0')}.jpg'\n`;
fs.writeFileSync(path.join(dir, 'list.txt'), out);
console.log(`wrote ${dir}/list.txt — ${frames.length} frames, total ${total}s`);
