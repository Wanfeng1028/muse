#!/usr/bin/env node
// Validate brief.md, sources.json, topics.json and research.md in a folder. Usage: node check.mjs [folder]
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const dir = process.argv[2] || ".";
const errs = [];
const read = (f) => (existsSync(join(dir, f)) ? readFileSync(join(dir, f), "utf8") : null);
const json = (f) => {
  const t = read(f);
  if (t === null) return null;
  try { return JSON.parse(t); } catch (e) { errs.push(`${f}: invalid JSON (${e.message})`); return null; }
};

const brief = read("brief.md");
if (brief !== null) {
  const m = brief.match(/^---\n([\s\S]*?)\n---/);
  if (!m) errs.push("brief.md: missing frontmatter");
  else {
    const fm = Object.fromEntries(m[1].split("\n").map((l) => l.match(/^(\w+):\s*(.*?)(\s+#.*)?$/)).filter(Boolean).map((x) => [x[1], x[2].replace(/^"|"$/g, "")]));
    if (!["draft", "confirmed"].includes(fm.status)) errs.push("brief.md: status must be draft or confirmed");
    if (!["shorts", "reels", "tiktok", "youtube", "linkedin", "x"].includes(fm.platform)) errs.push("brief.md: platform must be shorts|reels|tiktok|youtube|linkedin|x");
    if (!/^\d+(s|m)$/.test(fm.length || "")) errs.push("brief.md: length must look like 45s or 2m");
    if (fm.status === "confirmed") for (const k of ["message", "audience", "aspect", "tone"]) if (!fm[k]) errs.push(`brief.md: confirmed brief is missing ${k}`);
    const script = (brief.split(/^## /m).find((b) => b.startsWith("Script\n")) || "").slice(7);
    const lines = script.split("\n").filter((l) => l.trim());
    const secs = parseInt(fm.length) * (fm.length?.endsWith("m") ? 60 : 1);
    const words = lines.join(" ").split(/\s+/).filter(Boolean).length;
    if (lines.length && secs && Math.abs(words / (secs / 60) - 150) > 45) errs.push(`brief.md: script is ${words} words for ${fm.length} (aim for about ${Math.round((secs / 60) * 150)})`);
  }
}

const sources = json("sources.json");
if (sources) {
  if (!Array.isArray(sources)) errs.push("sources.json: must be an array");
  else sources.forEach((s, i) => {
    if (s.n !== i + 1) errs.push(`sources.json: entry ${i + 1} has n=${s.n}`);
    if (!/^https?:\/\//.test(s.url || "")) errs.push(`sources.json: [${s.n}] bad url`);
    if (s.quote && s.quote.split(/\s+/).length > 25) errs.push(`sources.json: [${s.n}] quote over 25 words`);
    if (s.date !== null && !/^\d{4}-\d{2}-\d{2}$/.test(s.date || "")) errs.push(`sources.json: [${s.n}] date must be YYYY-MM-DD or null`);
  });
}

const topics = json("topics.json");
if (topics) {
  const n = topics.topics?.length ?? 0;
  if (n < 3 || n > 7) errs.push(`topics.json: ${n} topics (want 3-7)`);
  (topics.topics || []).forEach((t) => { if (!t.title || !t.hook || !t.whyNow || !t.sources?.length) errs.push(`topics.json: "${t.title}" needs title, hook, whyNow and a source`); });
}

const cited = new Set();
for (const f of ["research.md", "brief.md"]) for (const [, n] of (read(f) || "").matchAll(/\[(\d+)\]/g)) cited.add([f, +n].join(":"));
if (sources && Array.isArray(sources)) for (const c of cited) { const [f, n] = c.split(":"); if (!sources.some((s) => s.n === +n)) errs.push(`${f}: cites [${n}] but sources.json has no such entry`); }
else if ([...cited].length && existsSync(join(dir, "research.md"))) errs.push("research.md: citations without a sources.json");

if (errs.length) { console.error(errs.join("\n")); process.exit(1); }
console.log("ok");
