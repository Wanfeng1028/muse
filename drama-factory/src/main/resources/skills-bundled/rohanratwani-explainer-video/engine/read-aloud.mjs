// Turn an episode's generated script.md into a script to read aloud: one beat per
// paragraph, grouped by chapter, with recording notes on top.
//   node engine/read-aloud.mjs videos/<id>
// Reads videos/<id>/script.md (written by build.mjs), writes videos/<id>/read-aloud.md.
import fs from "node:fs";
import path from "node:path";

const dir = process.argv[2];
const src = fs.readFileSync(path.join(dir, "script.md"), "utf8");
const title = (src.match(/^# (.+)$/m) || [, path.basename(dir)])[1].replace(/ · scene table$/, "");
const rows = src.split("\n").filter((l) => /^\| \d+:\d\d \|/.test(l)).map((l) => l.split("|").slice(1, -1).map((c) => c.trim()));
// 16:9 tables: time | chapter | narration | on screen. Shorts: time | narration | on screen.
const beats = rows.map((r) => (r.length >= 4 ? { ch: r[1], text: r[2] } : { ch: "", text: r[1] }));
const words = beats.reduce((a, b) => a + b.text.split(/\s+/).length, 0);

let out = `# ${title} · read-aloud script

${beats.length} paragraphs, ${words} words. About ${Math.round(words / 150)} to ${Math.round(words / 130)} minutes at a relaxed pace.

**How to record**
- One take, start to finish. Phone voice memo is fine, about a hand's width from your mouth, in a quiet room.
- Leave a one-second pause between paragraphs. That's where the scenes change.
- Fumbled a line? Stop, pause, and say the whole sentence again. I cut the bad one out.
- Read it like you're explaining it to a friend, not reading. Your own pace is fine:
  every animation gets retimed to your delivery.
- Drop the file in \`${path.basename(dir)}/vo/raw/\` and tell me it's in.
`;
let last = null;
for (const b of beats) {
  if (b.ch !== last && b.ch) { out += `\n## ${b.ch}\n`; last = b.ch; }
  out += `\n${b.text}\n`;
}
fs.writeFileSync(path.join(dir, "read-aloud.md"), out, "utf8");
console.log(`${path.join(dir, "read-aloud.md")}: ${beats.length} paragraphs, ${words} words`);
