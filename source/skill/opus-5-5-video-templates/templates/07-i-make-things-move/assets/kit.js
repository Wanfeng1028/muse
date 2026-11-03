// Shared helpers for the Opus 5.5 motion templates.
// Every template draws the whole frame from a single time value t, so any
// frame can be rendered on its own (HyperFrames seeks frames out of order).
(function () {
  const K = {};
  K.clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  K.prog = (t, t0, t1) => K.clamp((t - t0) / (t1 - t0));
  K.lerp = (a, b, u) => a + (b - a) * u;
  K.E = {
    linear: (u) => u,
    inQuad: (u) => u * u,
    outQuad: (u) => 1 - (1 - u) * (1 - u),
    inCubic: (u) => u * u * u,
    outCubic: (u) => 1 - Math.pow(1 - u, 3),
    inOutCubic: (u) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2),
    outExpo: (u) => (u >= 1 ? 1 : 1 - Math.pow(2, -10 * u)),
    inOutExpo: (u) => (u <= 0 ? 0 : u >= 1 ? 1 : u < 0.5 ? Math.pow(2, 20 * u - 10) / 2 : (2 - Math.pow(2, -20 * u + 10)) / 2),
    outBack: (u, s = 1.70158) => 1 + (s + 1) * Math.pow(u - 1, 3) + s * Math.pow(u - 1, 2),
    outElastic: (u) => (u <= 0 ? 0 : u >= 1 ? 1 : Math.pow(2, -10 * u) * Math.sin((u * 10 - 0.75) * ((2 * Math.PI) / 3)) + 1),
    outBounce: (u) => {
      const n = 7.5625, d = 2.75;
      if (u < 1 / d) return n * u * u;
      if (u < 2 / d) return n * (u -= 1.5 / d) * u + 0.75;
      if (u < 2.5 / d) return n * (u -= 2.25 / d) * u + 0.9375;
      return n * (u -= 2.625 / d) * u + 0.984375;
    },
  };
  // deterministic pseudo-random in [0,1)
  K.rnd = (i) => { const x = Math.sin(i * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
  K.$ = (id) => document.getElementById(id);
  K.show = (el, on) => { el.style.display = on ? "" : "none"; };
  // stroke draw-on for paths that carry pathLength="1"
  K.draw = (el, u) => { el.style.strokeDasharray = "1"; el.style.strokeDashoffset = String(1 - K.clamp(u)); el.style.visibility = u > 0 ? "visible" : "hidden"; };
  // left-to-right reveal of a clipPath rect
  K.reveal = (rect, u, w) => rect.setAttribute("width", String(Math.max(0, w * K.clamp(u))));
  // typewriter
  K.type = (el, text, u) => { el.textContent = text.slice(0, Math.round(text.length * K.clamp(u))); };

  // Template variables: defaults come from <html data-composition-variables>,
  // overrides from `npx hyperframes render --variables '{...}'`.
  K.vars = () => {
    let decl = [];
    try { decl = JSON.parse(document.documentElement.getAttribute("data-composition-variables") || "[]"); } catch (e) {}
    const v = {};
    decl.forEach((d) => { v[d.id] = d.default; });
    try {
      const o = window.__hyperframes && window.__hyperframes.getVariables && window.__hyperframes.getVariables();
      if (o) Object.assign(v, o);
    } catch (e) {}
    return v;
  };
  // fill [data-var] text nodes and expose colour variables as CSS custom properties
  K.bind = (v) => {
    document.querySelectorAll("[data-var]").forEach((el) => { el.textContent = v[el.dataset.var]; });
    Object.keys(v).forEach((k) => { if (/^#|^rgb|^hsl/.test(String(v[k]))) document.documentElement.style.setProperty("--" + k, v[k]); });
  };
  // split an element's text into inline-block spans (spaces kept as nbsp)
  K.chars = (el, text) => {
    el.textContent = "";
    return [...text].map((c) => { const s = document.createElement("span"); s.className = "ch"; s.textContent = c === " " ? " " : c; el.appendChild(s); return s; });
  };
  // register one paused GSAP timeline that re-renders the frame from t
  K.run = (compId, duration, render) => {
    render(0);
    const st = { t: 0 };
    const tl = gsap.timeline({ paused: true });
    tl.to(st, { t: duration, duration, ease: "none", onUpdate: () => render(st.t) }, 0);
    window.__timelines = window.__timelines || {};
    window.__timelines[compId] = tl;
    tl.seek(0);
  };
  window.K = K;
})();
