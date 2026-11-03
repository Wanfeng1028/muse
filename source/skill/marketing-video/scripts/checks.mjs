// The checks that catch what the eye misses on a contact sheet, in every format:
// each click lands inside its button, and the pointer never sits on text that
// is meant to be read. The scene declares both in window.CHECKS.
// Usage: node checks.mjs [scene.built.html] [WxH ...]      exits 1 on any failure
import { chromium } from "playwright";
import path from "path";

// arguments in any order: sizes look like 1920x1080, anything else is the scene
const argv = process.argv.slice(2), isSize = (a) => /^\d+x\d+$/.test(a);
const html = path.resolve(argv.find((a) => !isSize(a)) || "scene.built.html");
const sizes = (argv.some(isSize) ? argv.filter(isSize) : ["1440x1440", "1080x1920"])
  .map((s) => s.split("x").map(Number));
const browser = await chromium.launch();
let failed = 0;
for (const [W, H] of sizes) {
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  await page.goto("file://" + html);
  await page.evaluate(() => document.fonts.ready);
  const checks = await page.evaluate(() => window.CHECKS || { clicks: [], cover: [] });
  for (const c of checks.clicks || []) {
    const r = await page.evaluate(([t, sel]) => window.hitTest(t, sel), [c.t, c.sel]);
    if (!r.inside) failed++;
    console.log(`${W}x${H}  ${r.inside ? "HIT " : "MISS"}  click "${c.name}" at ${c.t.toFixed(2)}s` +
      (r.inside ? "" : `  (${r.dx}px, ${r.dy}px outside ${c.sel})`));
  }
  for (const c of checks.cover || []) {
    const r = await page.evaluate(([sel, a, b]) => {
      let hits = 0, first = null, seen = 0;
      const overlap = (p, q) => !(p.right < q.left || p.left > q.right || p.bottom < q.top || p.top > q.bottom);
      for (let t = a; t < b; t += 1 / 60) {
        window.seek(t);
        const e = document.querySelector(sel), k = document.getElementById("cursor");
        if (!e) continue;
        // computed values, not inline ones: a container often sets no opacity of its own
        const shown = (n) => { const cs = getComputedStyle(n); return cs.display !== "none" && +cs.opacity >= .05; };
        if (!shown(e)) continue;
        // an absolutely positioned container measures 0x0: test what is actually drawn inside it
        const rects = [e, ...e.querySelectorAll("*")].filter(shown)
          .map((n) => n.getBoundingClientRect()).filter((q) => q.width > 0 && q.height > 0);
        if (!rects.length) continue;
        seen++;
        if (k.style.display === "none") continue;
        const y = k.getBoundingClientRect();
        if (rects.some((q) => overlap(y, q))) { hits++; first ??= t; }
      }
      return { hits, first, seen };
    }, [c.sel, c.from, c.to]);
    const bad = r.hits > 0 || r.seen === 0;
    if (bad) failed++;
    console.log(`${W}x${H}  ${bad ? "FAIL" : "OK  "}  pointer over ${c.name}: ` + (r.seen === 0
      ? `"${c.sel}" is never visible between ${c.from.toFixed(2)}s and ${c.to.toFixed(2)}s, so nothing was checked`
      : `${r.hits} frames` + (r.first !== null ? ` (first at ${r.first.toFixed(2)}s)` : "")));
  }
  await page.close();
}
await browser.close();
console.log(failed ? `\n${failed} check(s) failed` : "\nall checks pass");
process.exit(failed ? 1 : 0);
