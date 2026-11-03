// motion-studio kit: the engine every film is built on. Copied into each film folder by `studio.py new`.
// Rule of the engine: every style is a pure function of t. No CSS transitions, timers, or state between frames,
// so any frame can be rendered alone (stills, subframe motion blur, scrubbing in the preview).
(function () {
  const VERSION = "1.0.0";
  const NS = "http://www.w3.org/2000/svg";

  // frame + caption band per format; scenes are clipped above `band` so nothing crosses a caption
  const FORMATS = {
    "4x5": { w: 1080, h: 1350, capTop: 1150, band: 1098, capSize: 50 },
    "9x16": { w: 1080, h: 1920, capTop: 1560, band: 1500, capSize: 54 },
    "16x9": { w: 1920, h: 1080, capTop: 930, band: 900, capSize: 48 },
  };
  const HOUSE = { BG: "#0b0b0b", INK: "#e8e6e1", GREY: "#969691", ACCENT: "#e8772e", PANEL: "#141414" };

  const K = { VERSION, FORMATS };
  window.K = K;

  // ── math ───────────────────────────────────────────────
  K.clamp01 = x => Math.max(0, Math.min(1, x));
  K.lerp = (a, c, p) => a + (c - a) * p;
  K.prog = (t, a, c) => K.clamp01((t - a) / (c - a));
  K.eio = x => x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
  K.eout = x => 1 - Math.pow(1 - x, 3);
  K.ein = x => x * x * x;
  K.smooth = x => x * x * (3 - 2 * x);
  // closed-form spring step 0 → 1; z < 1 overshoots
  K.step = (t, t0, w = 14, z = 0.62) => {
    if (t <= t0) return 0;
    const d = t - t0, wd = w * Math.sqrt(1 - z * z);
    return 1 - Math.exp(-z * w * d) * (Math.cos(wd * d) + (z * w / wd) * Math.sin(wd * d));
  };
  // keyframes [[t, v], ...], eased between neighbours; kfLog interpolates in log space (use it for zoom)
  K.kf = (t, keys, ease = K.eio) => {
    if (t <= keys[0][0]) return keys[0][1];
    for (let i = 1; i < keys.length; i++) if (t <= keys[i][0]) {
      const [t0, v0] = keys[i - 1], [t1, v1] = keys[i];
      return K.lerp(v0, v1, ease(K.prog(t, t0, t1)));
    }
    return keys[keys.length - 1][1];
  };
  K.kfLog = (t, keys) => Math.exp(K.kf(t, keys.map(([k, v]) => [k, Math.log(v)])));
  // a decaying pulse after an event (hits, landings)
  K.bump = (t, t0, k = 9) => t < t0 ? 0 : Math.exp(-(t - t0) * k) * Math.sin(Math.min(Math.PI, (t - t0) * 18));
  const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
  K.mix = (a, c, p) => { const A = hex(a), C = hex(c); return "rgb(" + A.map((v, i) => Math.round(K.lerp(v, C[i], p))).join(",") + ")"; };
  // seeded random, so layouts are identical on every render
  K.rng = (seed = 7) => () => (seed = (seed * 16807) % 2147483647) / 2147483647;

  // ── setup: format, beat grid, palette, stage ───────────
  K.setup = ({ format = "4x5", bpm = 120, bars = 16, palette = {}, title = "" } = {}) => {
    const F = FORMATS[format];
    if (!F) throw new Error(`unknown format ${format}: use one of ${Object.keys(FORMATS).join(", ")}`);
    Object.assign(K, { FORMAT: format, W: F.w, H: F.h, CAP_TOP: F.capTop, BAND: F.band, CAP_SIZE: F.capSize });
    K.C = Object.assign({}, HOUSE, palette);
    K.BPM = bpm; K.BEAT = 60 / bpm; K.BAR = 4 * K.BEAT;
    K.b = (bar, beat = 0) => (bar * 4 + beat) * K.BEAT;
    K.DUR = K.b(bars);
    window.STUDIO = { kit: VERSION, title, bg: K.C.BG, format: { name: format, w: F.w, h: F.h, capTop: F.capTop, band: F.band }, bpm, bars, scenes: [], text: [] };
    const stage = document.getElementById("stage"), svg = document.getElementById("svg");
    stage.style.width = F.w + "px"; stage.style.height = F.h + "px"; stage.style.background = K.C.BG;
    document.body.style.background = K.C.BG;
    svg.setAttribute("width", F.w); svg.setAttribute("height", F.h); svg.setAttribute("viewBox", `0 0 ${F.w} ${F.h}`);
    K.svg = svg; K.defs = svg.querySelector("defs"); K.top = document.getElementById("top");
    // the caption band clip: put scene groups inside K.banded() so they stop above the captions
    K.clipRect("band", -10, -10, F.w + 20, F.band + 10);
    return K;
  };
  K.scene = (name, fromBar, toBar) => { window.STUDIO.scenes.push({ name, from: K.b(fromBar), to: K.b(toBar), bars: [fromBar, toBar] }); };
  // register in-scene text that is not a caption, so the blind read and the preview know about it
  K.label = (text, t0, t1, where = "in scene") => { window.STUDIO.text.push({ t0, t1, where, text }); };

  // ── dom ────────────────────────────────────────────────
  K.el = (tag, attrs = {}, parent) => {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    (parent || K.top).appendChild(e);
    return e;
  };
  K.set = (e, attrs) => { for (const k in attrs) e.setAttribute(k, attrs[k]); };
  K.show = (e, on) => { e.style.display = on ? "" : "none"; };
  K.rect = (x, y, w, h, rx = 0) => { w = Math.max(0, w); h = Math.max(0, h); return { x, y, width: w, height: h, rx: Math.min(rx, w / 2, h / 2) }; };
  K.text = (str, attrs, parent) => { const e = K.el("text", Object.assign({ "font-family": "Georgia, serif", fill: K.C.INK }, attrs), parent); e.textContent = str; return e; };
  K.group = (id, parent) => K.el("g", id ? { id } : {}, parent || K.svg.querySelector("#world") || K.svg);
  K.banded = id => { const g = K.group(id); g.setAttribute("clip-path", "url(#band)"); return g; };
  // camera on a group: world point (cx, cy) at frame centre, zoom z (drive z with K.kfLog)
  K.cam = (g, cx, cy, z) => g.setAttribute("transform", `translate(${K.W / 2} ${K.H / 2}) scale(${z}) translate(${-cx} ${-cy})`);
  K.toScreen = (v, x, y) => [(x - v.cx) * v.z + K.W / 2, (y - v.cy) * v.z + K.H / 2];
  // clip paths you animate each frame: set their attributes in render(t)
  K.clipRect = (id, x = 0, y = 0, w = 0, h = 0) => K.el("rect", { x, y, width: w, height: h }, K.el("clipPath", { id }, K.defs));
  K.clipCircle = (id) => K.el("circle", { r: 0 }, K.el("clipPath", { id }, K.defs));
  K.cursor = parent => {
    const g = K.el("g", {}, parent);
    K.el("path", { d: "M 0 0 L 0 34 L 8 26 L 14 40 L 20 37 L 14 24 L 25 24 Z", fill: "#ffffff", stroke: "#000", "stroke-width": 2, "stroke-linejoin": "round" }, g);
    return g;
  };

  // ── captions: whole phrases rise out of one mask line and leave through it ──
  // parts: [["text"], ["accent words", K.C.ACCENT], ["italic", color, true]]
  K._caps = [];
  K.caption = (parts, tIn, tOut = null, { top = K.CAP_TOP, size = K.CAP_SIZE, where = "caption" } = {}) => {
    const d = document.createElement("div");
    const lh = Math.round(size * 1.35);
    Object.assign(d.style, { position: "absolute", left: "60px", width: (K.W - 120) + "px", top: top + "px", height: lh + "px",
      overflow: "hidden", textAlign: "center", fontFamily: "Georgia, serif", fontSize: size + "px", color: K.C.INK });
    const inner = document.createElement("div");
    inner.style.lineHeight = lh + "px";
    parts.forEach(([s, color, italic]) => {
      const sp = document.createElement("span");
      sp.textContent = s; sp.style.whiteSpace = "pre"; sp.style.color = color || K.C.INK; if (italic) sp.style.fontStyle = "italic";
      inner.appendChild(sp);
    });
    d.appendChild(inner);
    document.getElementById("caps").appendChild(d);
    window.STUDIO.text.push({ t0: tIn, t1: tOut, where, text: parts.map(p => p[0]).join("") });
    K._caps.push(t => {
      const up = K.eout(K.prog(t, tIn, tIn + 0.26)), gone = tOut == null ? 0 : K.ein(K.prog(t, tOut, tOut + 0.22));
      inner.style.transform = `translateY(${(1 - up) * 110 - gone * 110}%)`;
      d.style.visibility = t < tIn || (tOut != null && t > tOut + 0.22) ? "hidden" : "visible";
    });
    return d;
  };

  // ── run: wire render(t) to window.seek; captions update after the scene ──
  K.run = render => {
    const seek = t => { const tt = Math.min(Math.max(t, 0), K.DUR - 1e-6); render(tt); K._caps.forEach(c => c(tt)); return true; };
    window.seek = seek;
    window.DUR = K.DUR;
    window.STUDIO.text.sort((a, b) => a.t0 - b.t0);
    // lint: a caption wider than the frame gets clipped by its own mask; warn instead of shipping it
    window.STUDIO.warnings = [];
    document.querySelectorAll("#caps > div").forEach(d => {
      const inner = d.firstChild, over = inner.scrollWidth - d.clientWidth;
      if (over > 1) window.STUDIO.warnings.push(`caption too wide by ${over}px: "${inner.textContent}"`);
    });
    seek(0);
  };
})();
