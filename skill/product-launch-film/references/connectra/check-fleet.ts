// Collision audit for the v4 fleet diagram. Run: node scripts/check-fleet.ts
// Checks, for every scene config: box↔box, box↔label, label↔label, hub↔box/label,
// spoke↔other boxes, spoke↔labels, plus the allowed screen region. Exit 1 on any violation.
import {fleetGeom, hubPoly, type FleetCfg, type Pt, type Rect} from '../src/v4/components/fleetGeom.ts';
import {FLEET_CFGS as BASE, FLEET_MORPHS} from '../src/v4/components/fleetCfgs.ts';

// add in-between states of every morph (region = union of both ends)
const FLEET_CFGS: Record<string, (typeof BASE)[keyof typeof BASE]> = {...BASE};
for (const [a, b] of FLEET_MORPHS) {
  for (const t of [0.25, 0.5, 0.75]) {
    const A = BASE[a], B = BASE[b];
    const l = (x: number, y: number) => x + (y - x) * t;
    FLEET_CFGS[`${a}→${b}@${t}`] = {
      cfg: {cx: l(A.cfg.cx, B.cfg.cx), cy: l(A.cfg.cy, B.cfg.cy), rx: l(A.cfg.rx, B.cfg.rx), ry: l(A.cfg.ry, B.cfg.ry), s: l(A.cfg.s, B.cfg.s), font: l(A.cfg.font ?? 18, B.cfg.font ?? 18)},
      region: {x0: Math.min(A.region.x0, B.region.x0), y0: Math.min(A.region.y0, B.region.y0), x1: Math.max(A.region.x1, B.region.x1), y1: Math.max(A.region.y1, B.region.y1)},
      labels: A.labels, spokes: A.spokes,
    };
  }
}

const rectPoly = (r: Rect): Pt[] => [{x: r.x0, y: r.y0}, {x: r.x1, y: r.y0}, {x: r.x1, y: r.y1}, {x: r.x0, y: r.y1}];
const sub = (a: Pt, b: Pt) => ({x: a.x - b.x, y: a.y - b.y});
const dot = (a: Pt, b: Pt) => a.x * b.x + a.y * b.y;
const segPt = (p: Pt, a: Pt, b: Pt) => {
  const ab = sub(b, a);
  const t = Math.max(0, Math.min(1, dot(sub(p, a), ab) / (dot(ab, ab) || 1)));
  return Math.hypot(p.x - (a.x + ab.x * t), p.y - (a.y + ab.y * t));
};
const cross = (o: Pt, a: Pt, b: Pt) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
const segsCross = (a: Pt, b: Pt, c: Pt, d: Pt) => cross(a, b, c) * cross(a, b, d) < 0 && cross(c, d, a) * cross(c, d, b) < 0;
const segSeg = (a: Pt, b: Pt, c: Pt, d: Pt) => (segsCross(a, b, c, d) ? 0 : Math.min(segPt(a, c, d), segPt(b, c, d), segPt(c, a, b), segPt(d, a, b)));
const inside = (p: Pt, poly: Pt[]) => {
  let s = 0;
  for (let i = 0; i < poly.length; i++) {
    const c = cross(poly[i], poly[(i + 1) % poly.length], p);
    if (c !== 0) { if (s === 0) s = Math.sign(c); else if (Math.sign(c) !== s) return false; }
  }
  return true;
};
const edges = (p: Pt[]) => p.map((q, i) => [q, p[(i + 1) % p.length]] as const);
/** 0 if overlapping, otherwise the minimum gap between two convex polygons / polylines. */
const gap = (A: Pt[], B: Pt[]) => {
  if (A.length > 2 && B.some((p) => inside(p, A))) return 0;
  if (B.length > 2 && A.some((p) => inside(p, B))) return 0;
  const ea = A.length === 2 ? [[A[0], A[1]] as const] : edges(A);
  const eb = B.length === 2 ? [[B[0], B[1]] as const] : edges(B);
  let m = Infinity;
  for (const [a, b] of ea) for (const [c, d] of eb) m = Math.min(m, segSeg(a, b, c, d));
  return m;
};

const MIN = {boxBox: 14, boxLabel: 8, labelLabel: 10, spokeLabel: 10, spokeBox: 6, hub: 14};
let bad = 0;
for (const [name, {cfg, region, labels, spokes}] of Object.entries(FLEET_CFGS)) {
  const g = fleetGeom(cfg);
  const hub = hubPoly(cfg);
  const issues: string[] = [];
  const tag = (i: number) => `mini-${String(i + 1).padStart(2, '0')}`;
  const worst: Record<string, number> = {};
  const rec = (k: string, v: number, min: number, what: string) => {
    worst[k] = Math.min(worst[k] ?? Infinity, v);
    if (v < min) issues.push(`${what}: gap ${v.toFixed(1)}px < ${min}`);
  };
  for (const a of g) {
    for (const b of g) if (b.i > a.i) rec('boxBox', gap(a.poly, b.poly), MIN.boxBox, `box ${tag(a.i)} ↔ box ${tag(b.i)}`);
    rec('hub', gap(a.poly, hub), MIN.hub, `box ${tag(a.i)} ↔ hub`);
    if (labels) {
      const la = rectPoly(a.label.rect);
      for (const b of g) {
        if (b.i !== a.i) rec('boxLabel', gap(la, b.poly), MIN.boxLabel, `label ${tag(a.i)} ↔ box ${tag(b.i)}`);
        else rec('boxLabel', gap(la, b.poly), 6, `label ${tag(a.i)} ↔ own box`);
        if (b.i > a.i) rec('labelLabel', gap(la, rectPoly(b.label.rect)), MIN.labelLabel, `label ${tag(a.i)} ↔ label ${tag(b.i)}`);
      }
      rec('hub', gap(la, hub), MIN.hub, `label ${tag(a.i)} ↔ hub`);
    }
    if (spokes) {
      const seg = [{x: cfg.cx, y: cfg.cy}, {x: a.x, y: a.y}];
      for (const b of g) {
        if (b.i !== a.i) rec('spokeBox', gap(seg, b.poly), MIN.spokeBox, `spoke ${tag(a.i)} ↔ box ${tag(b.i)}`);
        if (labels) rec('spokeLabel', gap(seg, rectPoly(b.label.rect)), MIN.spokeLabel, `spoke ${tag(a.i)} ↔ label ${tag(b.i)}`);
      }
    }
    const pts = [...a.poly, ...(labels ? rectPoly(a.label.rect) : [])];
    for (const p of pts) {
      if (p.x < region.x0 || p.x > region.x1 || p.y < region.y0 || p.y > region.y1) {
        issues.push(`${tag(a.i)} leaves region at (${p.x.toFixed(0)}, ${p.y.toFixed(0)})`);
        break;
      }
    }
  }
  const ext = g.flatMap((m) => [...m.poly, ...(labels ? rectPoly(m.label.rect) : [])]);
  const bb = {x0: Math.min(...ext.map((p) => p.x)), x1: Math.max(...ext.map((p) => p.x)), y0: Math.min(...ext.map((p) => p.y)), y1: Math.max(...ext.map((p) => p.y))};
  console.log(`${issues.length ? '✗' : '✓'} ${name.padEnd(12)} extent x ${bb.x0.toFixed(0)}–${bb.x1.toFixed(0)}, y ${bb.y0.toFixed(0)}–${bb.y1.toFixed(0)} | min gaps ${Object.entries(worst).map(([k, v]) => `${k} ${v.toFixed(0)}`).join(', ')}`);
  for (const s of issues) console.log('   ', s);
  bad += issues.length;
}
process.exit(bad ? 1 : 0);
