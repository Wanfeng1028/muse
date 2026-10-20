// Set up a workspace (where your videos live) from the installed skill.
//   node <skill>/engine/init.mjs <dir>
// Copies engine/, fonts/ and templates/ into <dir> and creates <dir>/videos/. Safe to re-run:
// it updates the engine and never touches videos/.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const skill = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dir = path.resolve(process.argv[2] || ".");
if (dir === skill) { console.log("this folder is already a workspace"); process.exit(0); }
for (const d of ["engine", "fonts", "templates"]) fs.cpSync(path.join(skill, d), path.join(dir, d), { recursive: true });
fs.mkdirSync(path.join(dir, "videos"), { recursive: true });
const gi = path.join(dir, ".gitignore");
if (!fs.existsSync(gi)) fs.writeFileSync(gi, "videos/*/edit/\nvideos/*/renders/\nvideos/*/vo/\nvideos/*/snaps/\nnode_modules/\n");
console.log(`workspace ready: ${dir}
next:
  node engine/doctor.mjs          # checks ffmpeg, HyperFrames, and the voice tools
  node engine/new.mjs my-first-video`);
