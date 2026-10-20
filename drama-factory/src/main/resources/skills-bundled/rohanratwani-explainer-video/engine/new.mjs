// New episode from the template.
//   node engine/new.mjs <slug>        -> videos/<slug>/build.mjs + brief.md
// Then: cd videos/<slug> && node build.mjs, and replace the template's beats and scenes.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const slug = process.argv[2];
if (!slug || !/^[a-z0-9][a-z0-9-]*$/.test(slug)) {
  console.error("usage: node engine/new.mjs <slug>   (lowercase letters, digits, dashes)");
  process.exit(1);
}
const dst = path.join(root, "videos", slug);
if (fs.existsSync(dst)) { console.error(`${dst} already exists`); process.exit(1); }
// templates/ in an exported skill or workspace, skill/templates/ in the source repo
const tpl = [path.join(root, "templates", "episode"), path.join(root, "skill", "templates", "episode")].find((p) => fs.existsSync(p));
fs.cpSync(tpl, dst, { recursive: true });
console.log(`created ${dst}
next:
  cd videos/${slug}
  node build.mjs                      # silent cut + script.md (the scene table to approve)
  cd edit && npx --yes hyperframes lint`);
