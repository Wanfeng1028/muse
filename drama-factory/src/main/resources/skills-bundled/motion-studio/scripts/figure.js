// motion-studio figures: flat, rigged human characters drawn in SVG, posed as a pure function of t.
// Load after kit.js. A figure is built once and posed every frame:
//
//   const you = F.figure(parent, { skin: 1, hair: "short", shirt: K.C.ACCENT, face: "right" });
//   K.run(t => F.place(you, 700, 900, 1.0, F.at(t, [[0, "stand"], [2.1, "phone"], [4.0, "worried"]])));
//
// Poses are plain objects of joint angles (degrees) plus face settings, so they blend: F.blend(a, b, p).
// F.at(t, keys) eases between named or literal poses on a timeline; F.walk(phase) is a walk cycle;
// F.idle(t, seed) adds breathing, blinks and small weight shifts so a held pose never freezes.
// Angles: 0 = limb hanging straight down; positive swings it toward the way the figure faces.
// Elbows bend positive (forearm forward/up); knees bend negative (shin back).
(function () {
  const K = window.K;
  const F = {};
  window.F = F;

  F.SKIN = ["#f3cfb1", "#e0ac86", "#c18a62", "#8d5b3c", "#5c3a26"];
  F.HAIR = ["#1d1a17", "#3b2a1f", "#6b4a2e", "#a8763f", "#c9c4bb"];
  const D = Math.PI / 180;

  // ── poses ────────────────────────────────────────────────
  // lean: torso tilt; head: head tilt; ls/le: back (far) shoulder/elbow; rs/re: front (near) shoulder/elbow;
  // lh/lk, rh/rk: hips/knees; look: eye offset (-1..1, 1 = toward facing side); brow: -1 angry .. 1 worried;
  // mouth: -1 frown .. 1 smile; open: 0..1; crouch: lowers the hips (0..1); prop: what the near hand holds.
  const base = { lean: 0, head: 0, ls: 6, le: 8, rs: -6, re: 8, lh: 3, lk: -2, rh: -3, rk: -2,
                 look: 0.3, lookY: 0, brow: 0, mouth: 0.25, open: 0, crouch: 0, blink: 0 };
  F.POSES = {
    stand:   {},
    relaxed: { lean: -2, ls: 10, le: 14, rs: 4, re: 22, mouth: 0.4 },
    phone:   { prop: "phone", head: 12, lean: 3, rs: 14, re: 132, ls: 4, le: 10, look: 0.9, lookY: 0.7, mouth: 0, brow: 0.2 },
    read:    { prop: "phone", head: 14, lean: 4, rs: 16, re: 128, ls: 22, le: 110, look: 0.8, lookY: 0.8, mouth: -0.1, brow: 0.35 },
    worried: { head: -6, lean: -3, rs: 30, re: 140, ls: 26, le: 140, look: 0.1, brow: 1, mouth: -0.8, open: 0.25 },
    shocked: { head: -10, lean: -8, rs: 70, re: 70, ls: 60, le: 80, look: 0, brow: 1, mouth: -0.2, open: 0.9 },
    shrug:   { head: 8, rs: 20, re: 95, ls: 22, le: 95, brow: 0.6, mouth: -0.4, look: 0 },
    point:   { lean: 3, rs: 88, re: 6, ls: 6, le: 12, look: 1, brow: -0.1, mouth: 0.1 },
    present: { lean: 0, rs: 52, re: 40, ls: 10, le: 14, look: 0.2, mouth: 0.5 },
    think:   { head: 10, rs: 24, re: 150, ls: 12, le: 80, look: 0.6, lookY: -0.6, brow: 0.3, mouth: -0.1 },
    angry:   { lean: 6, rs: 18, re: 50, ls: 14, le: 50, brow: -1, mouth: -0.7, open: 0.15, look: 0.9 },
    happy:   { head: -4, rs: 8, re: 30, ls: 8, le: 30, brow: 0.2, mouth: 1, open: 0.35, look: 0.2 },
    cheer:   { head: -8, lean: -3, rs: 150, re: 20, ls: 145, le: 20, brow: 0.3, mouth: 1, open: 0.7 },
    type:    { head: 12, lean: 6, rs: 50, re: 60, ls: 46, le: 60, look: 0.7, lookY: 0.6, mouth: 0 },
    sit:     { lh: 88, lk: -88, rh: 86, rk: -86, crouch: 0.42, rs: 24, re: 40, ls: 20, le: 40 },
    sitphone:{ prop: "phone", lh: 88, lk: -88, rh: 86, rk: -86, crouch: 0.42, head: 14, rs: 14, re: 132, ls: 18, le: 40, look: 0.9, lookY: 0.7, mouth: 0 },
    slump:   { head: 22, lean: 10, rs: -2, re: 4, ls: 0, le: 4, look: 0.2, lookY: 0.9, brow: 0.9, mouth: -0.9 },
  };
  for (const k in F.POSES) F.POSES[k] = Object.assign({}, base, F.POSES[k]);
  const resolve = p => typeof p === "string" ? (F.POSES[p] || F.POSES.stand) : Object.assign({}, base, p);
  F.blend = (a, b, p) => { a = resolve(a); b = resolve(b); const o = {}; for (const k in base) o[k] = K.lerp(a[k], b[k], p); o.prop = p < 0.5 ? a.prop : b.prop; return o; };
  // keys: [[t, pose], ...]; each change takes `dur` seconds with a slight overshoot so moves land, not slide
  F.at = (t, keys, dur = 0.45) => {
    let cur = resolve(keys[0][1]);
    for (let i = 1; i < keys.length; i++) {
      if (t < keys[i][0]) break;
      const s = Math.min(1.08, K.step(t, keys[i][0], 13, 0.68)) ;
      cur = F.blend(cur, keys[i][1], K.clamp01(dur > 0 ? s : 1));
      if (s < 1) { const over = s - 1; if (over > 0) cur = F.blend(cur, keys[i][1], 1 + over); }
    }
    return cur;
  };
  // walk cycle: phase in steps (one full cycle = 2 steps); returns a pose plus the vertical bob
  F.walk = (phase, over = {}) => {
    const ph = phase * Math.PI, sR = Math.sin(ph), cR = Math.cos(ph);
    const knee = c => -5 - 40 * Math.pow(Math.max(0, c), 1.5);   // the swinging leg folds, the standing leg stays long
    return Object.assign({}, resolve(over), {
      rh: 22 * sR, rk: knee(cR), lh: -22 * sR, lk: knee(-cR),
      rs: -26 * sR + (over.rs || 0), ls: 26 * sR + (over.ls || 0), re: 16 + 10 * Math.max(0, -sR), le: 16 + 10 * Math.max(0, sR),
      lean: 3 + (over.lean || 0), bob: -1.3 * Math.abs(cR) + 1.3,
    });
  };

  // idle motion on top of any pose: breath, a blink every few seconds, a slow sway. Deterministic per seed.
  F.idle = (t, seed = 1, pose = "stand") => {
    const p = Object.assign({}, resolve(pose));
    const breath = Math.sin(t * 2 * Math.PI / 3.6 + seed);
    p.lean += breath * 0.8; p.head += Math.sin(t * 0.9 + seed * 2) * 1.6;
    p.ls += breath * 1.5; p.rs -= breath * 1.5;
    const period = 3.1 + (seed % 5) * 0.37, ph = (t + seed * 1.7) % period;
    p.blink = ph < 0.13 ? Math.sin(ph / 0.13 * Math.PI) : 0;
    p.breath = breath;
    return p;
  };

  // ── hair shapes, drawn around a head of radius 1 centred at 0,0 (facing right) ──
  const HAIRS = {
    bald: null,
    short: "M -1.02 0.05 C -1.15 -0.9 -0.4 -1.32 0.25 -1.2 C 0.85 -1.1 1.12 -0.55 1.02 -0.15 C 0.75 -0.55 0.2 -0.62 -0.35 -0.55 C -0.6 -0.35 -0.75 -0.05 -1.02 0.05 Z",
    long: "M -1.05 0.9 C -1.3 -0.4 -0.8 -1.3 0.15 -1.22 C 0.95 -1.15 1.2 -0.5 1.05 -0.1 C 0.7 -0.6 0.1 -0.62 -0.35 -0.5 C -0.5 0.1 -0.45 0.7 -0.2 1.25 C -0.6 1.3 -0.95 1.15 -1.05 0.9 Z",
    bun: "M -1.02 0.0 C -1.1 -0.9 -0.4 -1.3 0.2 -1.2 C 0.85 -1.1 1.12 -0.55 1.02 -0.15 C 0.7 -0.6 0.1 -0.6 -0.4 -0.5 C -0.65 -0.3 -0.8 -0.1 -1.02 0.0 Z M -0.95 -1.05 a 0.42 0.42 0 1 0 0.01 0 Z",
    curly: "M -1.1 0.2 C -1.4 -0.3 -1.1 -1.1 -0.5 -1.25 C -0.2 -1.5 0.4 -1.45 0.6 -1.2 C 1.1 -1.15 1.3 -0.6 1.05 -0.2 C 0.9 -0.5 0.4 -0.7 -0.1 -0.6 C -0.5 -0.5 -0.8 -0.2 -1.1 0.2 Z",
    cap: "M -1.05 -0.25 C -1.05 -1.0 -0.4 -1.28 0.15 -1.25 C 0.75 -1.2 1.05 -0.8 1.05 -0.35 L 1.75 -0.3 C 1.8 -0.18 1.6 -0.12 1.0 -0.15 L -1.05 -0.15 Z",
    hood: "M -1.35 1.1 C -1.6 -0.2 -1.0 -1.55 0.1 -1.5 C 1.1 -1.45 1.5 -0.6 1.35 0.3 C 1.1 -0.4 0.6 -0.95 -0.1 -0.95 C -0.8 -0.9 -1.0 -0.2 -0.95 0.6 Z",
  };

  // ── build ────────────────────────────────────────────────
  // opts: skin (0-4 or colour), hair (style), hairColor (0-4 or colour), shirt, pants, shoes, face ("right"|"left"),
  //       kind ("person" | "silhouette"): a silhouette has no face and a rim line, for people the story must not identify.
  F.figure = (parent, opts = {}) => {
    const o = Object.assign({ skin: 1, hair: "short", hairColor: 0, shirt: "#5b6b7a", pants: "#2c3440", shoes: "#151515",
                              face: "right", kind: "person", props: {} }, opts);
    const sil = o.kind === "silhouette";
    // a silhouette is a flat mid-grey shape: visible on the dark house background, but nobody in particular
    const SIL = "#34342f";
    const skin = sil ? SIL : (typeof o.skin === "number" ? F.SKIN[o.skin] : o.skin);
    const hairC = sil ? "#2b2b27" : (typeof o.hairColor === "number" ? F.HAIR[o.hairColor] : o.hairColor);
    const shirt = sil ? SIL : o.shirt, pants = sil ? "#2b2b27" : o.pants, shoes = sil ? "#222220" : o.shoes;
    const rim = {};
    const shade = c => c.startsWith("#") ? K.mix(c, "#000000", 0.28) : c;
    const root = K.el("g", {}, parent);
    const flip = K.el("g", {}, root);
    const limb = (color, w, parentG) => K.el("path", Object.assign({ fill: "none", stroke: color, "stroke-width": w, "stroke-linecap": "round", "stroke-linejoin": "round" }, parentG ? {} : {}), parentG || flip);
    const g = {};
    // far limbs first (darker), then torso, head, near limbs
    g.legL = limb(shade(pants), 9); g.shoeL = K.el("ellipse", { fill: shoes }, flip);
    g.armL = limb(shade(shirt), 7); g.handL = K.el("circle", { fill: shade(skin) }, flip);
    g.legR = limb(pants, 9); g.shoeR = K.el("ellipse", { fill: shoes }, flip);
    g.torso = K.el("path", Object.assign({ fill: shirt }, rim), flip);
    g.neck = K.el("rect", { fill: shade(skin) }, flip);
    g.head = K.el("g", {}, flip);
    g.hairBack = o.hair === "long" || o.hair === "hood" ? K.el("path", { fill: hairC === skin ? shade(hairC) : shade(hairC) }, g.head) : null;
    g.skull = K.el("circle", { cx: 0, cy: 0, r: 1, fill: skin }, g.head);
    g.ear = sil ? null : K.el("ellipse", { fill: shade(skin) }, g.head);
    g.hair = HAIRS[o.hair] ? K.el("path", { d: HAIRS[o.hair], fill: o.hair === "hood" ? shirt : hairC }, g.head) : null;
    if (!sil) {
      g.eyeL = K.el("ellipse", { fill: "#1a1714" }, g.head); g.eyeR = K.el("ellipse", { fill: "#1a1714" }, g.head);
      g.browL = K.el("path", { fill: "none", stroke: hairC, "stroke-width": 0.11, "stroke-linecap": "round" }, g.head);
      g.browR = K.el("path", { fill: "none", stroke: hairC, "stroke-width": 0.11, "stroke-linecap": "round" }, g.head);
      g.mouth = K.el("path", { fill: "#3a1f1a", stroke: "#3a1f1a", "stroke-width": 0.08, "stroke-linecap": "round", "stroke-linejoin": "round" }, g.head);
      g.cheek = K.el("ellipse", { fill: "#e0705a", opacity: 0.18 }, g.head);
    }
    g.armR = limb(shirt, 7); g.handR = K.el("circle", { fill: skin }, flip);
    // props in the near hand
    g.phone = K.el("g", {}, flip);
    K.el("rect", { x: -2.4, y: -4.4, width: 4.8, height: 8.8, rx: 0.9, fill: "#0e0e0e", stroke: "#3c3c3a", "stroke-width": 0.5 }, g.phone);
    g.phoneScreen = K.el("rect", { x: -1.85, y: -3.7, width: 3.7, height: 7.2, rx: 0.5, fill: "#2a3d52" }, g.phone);
    return { root, flip, g, o, sil };
  };

  // forward kinematics for a two-bone limb from (x, y): angles in degrees, 0 = down
  const fk = (x, y, a1, l1, a2, l2) => {
    const r1 = a1 * D, r2 = (a1 + a2) * D;
    const x1 = x + Math.sin(r1) * l1, y1 = y + Math.cos(r1) * l1;
    return [x1, y1, x1 + Math.sin(r2) * l2, y1 + Math.cos(r2) * l2];
  };
  const rot = (x, y, cx, cy, a) => { const c = Math.cos(a * D), s = Math.sin(a * D); return [cx + (x - cx) * c + (y - cy) * s, cy - (x - cx) * s + (y - cy) * c]; };

  // place and pose: (x, y) is the ground point between the feet; h is the figure's full height in px
  F.place = (fig, x, y, h, pose, opts = {}) => {
    const p = resolve(pose), g = fig.g, face = opts.face || fig.o.face;
    const u = h / 92;
    fig.root.setAttribute("transform", `translate(${x} ${y - (p.bob || 0) * u}) scale(${u})`);
    fig.flip.setAttribute("transform", face === "left" ? "scale(-1 1)" : "");
    // skeleton in figure units (y down, ground = 0)
    const hipY = -40 + p.crouch * 17, hipX = p.crouch * -5;
    const lean = p.lean, tl = 27 + (p.breath || 0) * 0.25;
    const [shX, shY] = rot(hipX, hipY - tl, hipX, hipY, -lean);
    // legs (from just either side of the hip)
    const legs = (hx, a1, a2) => fk(hx, hipY, a1, 19.5, a2, 19.5);
    const L = legs(hipX - 1.5, p.lh, p.lk), R = legs(hipX + 1.5, p.rh, p.rk);
    g.legL.setAttribute("d", `M ${hipX - 1.5} ${hipY} L ${L[0]} ${L[1]} L ${L[2]} ${L[3]}`);
    g.legR.setAttribute("d", `M ${hipX + 1.5} ${hipY} L ${R[0]} ${R[1]} L ${R[2]} ${R[3]}`);
    K.set(g.shoeL, { cx: L[2] + 2.4, cy: L[3] + 0.4, rx: 5, ry: 2.5 }); K.set(g.shoeR, { cx: R[2] + 2.4, cy: R[3] + 0.4, rx: 5, ry: 2.5 });
    // torso: a soft trapezoid from shoulders to hips, rotated by lean
    const pts = [[-9.5, 0], [9.5, 0], [8.2, tl], [-8.2, tl]].map(([dx, dy]) => rot(shX + dx, shY + dy, hipX, hipY, -lean));
    const c = (a, b, k) => [K.lerp(a[0], b[0], k), K.lerp(a[1], b[1], k)];
    const [a, b, cc, d] = pts;
    g.torso.setAttribute("d", `M ${c(a, b, 0.15)} Q ${a} ${c(a, d, 0.15)} L ${c(a, d, 0.97)} Q ${d} ${c(d, cc, 0.08)} L ${c(d, cc, 0.92)} Q ${cc} ${c(cc, b, 0.03)} L ${c(cc, b, 0.85)} Q ${b} ${c(b, a, 0.15)} Z`.replace(/,/g, " "));
    // neck and head
    const [nx, ny] = rot(shX, shY - 3, hipX, hipY, -lean);
    K.set(g.neck, { x: nx - 2, y: ny - 2, width: 4, height: 6, rx: 1.5 });
    const hr = 10.5, [hx, hy] = rot(shX + 0.6, shY - 3 - hr, hipX, hipY, -lean);
    g.head.setAttribute("transform", `translate(${hx} ${hy}) rotate(${p.head + lean * 0.5}) scale(${hr})`);
    if (g.hairBack) g.hairBack.setAttribute("d", fig.o.hair === "hood" ? "M -1.3 1.2 C -1.5 0 -1.2 -1.2 0 -1.35 C 1.1 -1.3 1.5 -0.4 1.3 1.2 Z" : "M -1.0 0.2 C -1.2 0.8 -1.1 1.4 -0.6 1.55 C -0.3 1.6 0 1.5 0.1 1.3 L -0.3 0.1 Z");
    if (!fig.sil) {
      const lx = p.look * 0.32 + 0.12, ly = p.lookY * 0.22;
      const eh = 0.15 * (1 - p.blink * 0.92);
      K.set(g.eyeL, { cx: lx - 0.18, cy: -0.05 + ly, rx: 0.11, ry: eh }); K.set(g.eyeR, { cx: lx + 0.3, cy: -0.05 + ly, rx: 0.11, ry: eh });
      K.set(g.ear, { cx: -0.45 + lx * 0.2, cy: 0.08, rx: 0.16, ry: 0.24 });
      const by = -0.38 + ly * 0.5 - Math.abs(p.brow) * 0.05, tilt = p.brow * 0.12;
      g.browL.setAttribute("d", `M ${lx - 0.34} ${by + tilt} L ${lx - 0.04} ${by - tilt}`);
      g.browR.setAttribute("d", `M ${lx + 0.18} ${by - tilt} L ${lx + 0.48} ${by + tilt}`);
      const mx = lx + 0.1, my = 0.42 + ly * 0.4, mw = 0.24, curve = p.mouth * 0.16, op = p.open * 0.22;
      g.mouth.setAttribute("d", op > 0.01
        ? `M ${mx - mw} ${my} Q ${mx} ${my + curve * 1.4 - op} ${mx + mw} ${my} Q ${mx} ${my + curve * 1.4 + op * 1.6 + 0.04} ${mx - mw} ${my} Z`
        : `M ${mx - mw} ${my - curve * 0.5} Q ${mx} ${my + curve * 1.5} ${mx + mw} ${my - curve * 0.5}`);
      g.mouth.setAttribute("fill", op > 0.01 ? "#3a1f1a" : "none");
      K.set(g.cheek, { cx: lx + 0.42, cy: 0.3, rx: 0.2, ry: 0.12 });
    }
    // arms from the shoulders (far shoulder a little behind)
    const [s1x, s1y] = rot(shX - 6.5, shY + 2.6, hipX, hipY, -lean), [s2x, s2y] = rot(shX + 6.5, shY + 2.6, hipX, hipY, -lean);
    const AL = fk(s1x, s1y, p.ls - lean, 13, p.le, 12), AR = fk(s2x, s2y, p.rs - lean, 13, p.re, 12);
    g.armL.setAttribute("d", `M ${s1x} ${s1y} L ${AL[0]} ${AL[1]} L ${AL[2]} ${AL[3]}`);
    g.armR.setAttribute("d", `M ${s2x} ${s2y} L ${AR[0]} ${AR[1]} L ${AR[2]} ${AR[3]}`);
    K.set(g.handL, { cx: AL[2], cy: AL[3], r: 2.8 }); K.set(g.handR, { cx: AR[2], cy: AR[3], r: 2.8 });
    // phone: shown when the pose (or opts) says so, held in the near hand, screen toward the face
    const showPhone = opts.prop === "phone" || (opts.prop == null && p.prop === "phone") || (opts.prop == null && p.prop == null && fig.o.props.phone);
    K.show(g.phone, !!showPhone);
    if (showPhone) {
      const ang = p.rs - lean + p.re;
      g.phone.setAttribute("transform", `translate(${AR[2] + 0.8} ${AR[3] - 2.4}) rotate(${180 - ang + 12})`);
      if (opts.glow != null) g.phoneScreen.setAttribute("fill", K.mix("#2a3d52", "#cfe3ff", opts.glow));
    }
    return { head: [x + (face === "left" ? -hx : hx) * u, y + hy * u], hand: [x + (face === "left" ? -AR[2] : AR[2]) * u, y + AR[3] * u] };
  };

  // a crowd of small figures, e.g. rows of workers: returns figures with deterministic variety
  F.crowd = (parent, n, seed = 3, opts = {}) => {
    const r = K.rng(seed), out = [];
    const shirts = opts.shirts || ["#3f4a55", "#4b4136", "#36433d", "#4a3a44", "#555046"];
    const hairs = opts.hairs || ["short", "short", "long", "bun", "curly", "cap", "bald"];
    for (let i = 0; i < n; i++) out.push(F.figure(parent, Object.assign({ skin: Math.floor(r() * 5), hairColor: Math.floor(r() * 4),
      hair: hairs[Math.floor(r() * hairs.length)], shirt: shirts[Math.floor(r() * shirts.length)] }, opts.each || {})));
    return out;
  };
})();
