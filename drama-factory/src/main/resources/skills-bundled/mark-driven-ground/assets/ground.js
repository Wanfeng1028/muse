/* ===================================================================
   ground.js — MARK-DRIVEN GROUND (drop-in, dependency-free).

   A background that is built AROUND one travelling element (a logo, a
   dot, a cursor — "the mark"). For every mark it draws:

     · two path rings centred on the LANDING point, radius = the flight
       distance R and .62R, plus the sampled flight path itself;
     · the lit arc BEHIND the mark: a stroke-dasharray window .32 of the
       path long that follows the mark and collapses into the landing;
     · a wide soft colour field that blooms where the mark lands and
       then settles down-left for the whole chapter, while the previous
       chapter's field fades out;
     · between marks, three colour fields carrying C(t+lead) / C(t) /
       C(t-lag) off a piecewise-linear colour TRACK, so the frame is
       always drifting toward the next chapter's colour.

   EVERYTHING IS A PURE FUNCTION OF LOGICAL TIME t. No timers, no rAF,
   no wall clock, no frame-to-frame state: GROUND.update(t) drawn twice
   with the same t produces the same pixels, so seek-and-shoot renders
   (see the smooth-render skill) are frame-exact and any scene renders
   identically whether or not the scene before it was ever played.

   API
     GROUND.init({stage, marks, track, theme, ...})   -> builds the DOM
     GROUND.update(t)                                 -> one frame
     GROUND.markAt(t)  -> {x,y,size,acc,id} | null    -> drive your mark
     GROUND.colorAt(t) -> '#rrggbb'                   -> the track colour
     GROUND.fit()      -> re-scale after a stage resize
     GROUND.destroy()
   =================================================================== */
(function (root) {
  'use strict';

  /* ---------- small maths ---------------------------------------- */
  var clamp = function (v, a, b) { return v < a ? a : v > b ? b : v; };
  var lerp  = function (a, b, p) { return a + (b - a) * p; };
  var sstep = function (u) { var x = clamp(u, 0, 1); return x * x * (3 - 2 * x); };   // smoothstep
  var seg   = function (t, a, b) { return clamp((t - a) / (b - a || 1e-6), 0, 1); };  // 0..1 across a window
  var hx    = function (c) { return [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)]; };
  var h2    = function (n) { return (n < 16 ? '0' : '') + n.toString(16); };
  function mixHex(a, b, p) {                                   // sRGB channel lerp
    var A = hx(a), B = hx(b);
    return '#' + A.map(function (v, i) { return h2(Math.round(clamp(lerp(v, B[i], p), 0, 255))); }).join('');
  }

  /* ---------- flight paths (p in 0..1, from S to LP) --------------
     Generic shapes; pass your own as a function (p, LP, S) => {x,y}. */
  var eo = function (p) { return 1 - Math.pow(1 - p, 3); };     // ease-out cubic
  var ez = function (p) { return p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2; };  // ease-in-out
  var PATHS = {
    line: function (p, L, S) { var e = eo(p); return { x: lerp(S.x, L.x, e), y: lerp(S.y, L.y, e) }; },
    zip: function (p, L, S) { var e = eo(p), d = Math.hypot(S.x - L.x, S.y - L.y);
      return { x: lerp(S.x, L.x, e), y: lerp(S.y, L.y, e) - Math.sin(p * Math.PI) * d * .45 }; },
    drop: function (p, L, S) {
      if (p < .3) { var q = ez(p / .3); return { x: lerp(S.x, L.x, q), y: lerp(S.y, L.y - 900, q) }; }
      var u = (p - .3) / .7, y0 = L.y - 900, y;
      if (u < .5) { var q2 = u / .5; y = lerp(y0, L.y, q2 * q2); }
      else if (u < .8) { var q3 = (u - .5) / .3; y = L.y - Math.sin(q3 * Math.PI) * 240; }
      else { var q4 = (u - .8) / .2; y = L.y - Math.sin(q4 * Math.PI) * 70; }
      return { x: L.x, y: y };
    },
    spiral: function (p, L, S) {
      var th = lerp(Math.PI * 1.1, Math.PI * 3.6, p);
      var r = lerp(Math.hypot(S.x - L.x, S.y - L.y), 0, eo(p)), k = ez(Math.min(1, p * 3));
      return { x: lerp(S.x, L.x + Math.cos(th) * r, k), y: lerp(S.y, L.y + Math.sin(th) * r * .6, k) };
    },
    hops: function (p, L, S) {
      var hop = Math.abs(Math.sin(p * Math.PI * 3)) * lerp(340, 90, p);
      return { x: lerp(S.x, L.x, p), y: lerp(S.y, L.y, p) - hop };
    },
    orbit: function (p, L, S) {
      var th = lerp(Math.PI * .9, Math.PI * 2.55, eo(p));
      var r = lerp(Math.hypot(S.x - L.x, S.y - L.y), 0, ez(p)), k = ez(Math.min(1, p * 4));
      return { x: lerp(S.x, L.x + Math.cos(th) * r, k), y: lerp(S.y, L.y + Math.sin(th) * r * .5, k) };
    }
  };
  var pathFn = function (p) { return typeof p === 'function' ? p : (PATHS[p] || PATHS.zip); };

  /* ---------- defaults -------------------------------------------- */
  var D = {
    w: 2560, h: 1440,              // design space (all coordinates are px in this grid)
    theme: 'light',
    flight: 0.7,                   // T_IN: how long a mark takes to land
    dur: 2.4,                      // the title beat (mark + heading) before the chapter cuts in
    arc: 0.32,                     // the lit window, as a fraction of the path
    strength: 3,                   // 1 soft tint · 2 colour · 3 full colour · 4 bold, wide core
    blur: 0,                       // px; 0 = falloff only (render-safe). Production used 110-140.
    lead: 12, lag: 9,              // the three fields carry C(t+lead) / C(t) / C(t-lag)
    glowLift: null,                // lighten the product colours toward white (default .3 on dark)
    darkPull: '#5b21b6', darkPullAmt: .55,  // track colours are pulled here on a dark ground
    ambient: '#c4b5fd',            // the third, always-on field
    wavePeriod: 12,                // seconds for one pass of the brightness wave
    rings: true, dots: true, wave: true
  };

  var O = null, EL = null, GEO = {}, MARKS = [], TRACK = [], curGeo = null;

  /* ---------- the colour track ------------------------------------ */
  function colorAt(t) {
    if (!TRACK.length) return O ? O.ambient : '#c4b5fd';
    if (t <= TRACK[0][0]) return TRACK[0][1];
    for (var i = 1; i < TRACK.length; i++) {
      if (t <= TRACK[i][0]) {
        var a = TRACK[i - 1], b = TRACK[i];
        return mixHex(a[1], b[1], (t - a[0]) / (b[0] - a[0] || 1e-6));
      }
    }
    return TRACK[TRACK.length - 1][1];
  }
  var lift = function (c) { return O.glowLift > 0 ? mixHex(c, '#ffffff', O.glowLift) : c; };
  var fieldColor = function (c) {
    return O.dark ? mixHex(c, O.darkPull, O.darkPullAmt)
                  : (O.strength >= 2 ? c : mixHex(c, '#ffffff', .12));
  };
  /* the wash: a small solid core, then a LONG fade. A solid plateau with
     a hard edge reads as a patch however much blur you add. */
  function core(c) {
    return O.strength >= 4
      ? 'radial-gradient(closest-side,' + c + ' 0%,' + c + ' 14%,transparent 76%)'
      : 'radial-gradient(closest-side,' + c + ',transparent 72%)';
  }

  /* ---------- DOM ------------------------------------------------- */
  function build(stage) {
    var g = document.createElement('div');
    g.className = 'mg-ground' + (O.dark ? ' mg-dark' : '');
    var space = document.createElement('div'); space.className = 'mg-space';
    space.style.width = O.w + 'px'; space.style.height = O.h + 'px';
    g.appendChild(space);

    var dots = null, wave = null;
    if (O.dots) { dots = document.createElement('div'); dots.className = 'mg-dots'; space.appendChild(dots); }
    if (O.wave) { wave = document.createElement('div'); wave.className = 'mg-wave'; space.appendChild(wave); }
    var grid = O.grid || Math.round(O.w / 53);                 // ~48px at 2560
    var tile = O.waveTile || Math.round(O.w * 1.64);           // ~4200px at 2560
    var mask = 'linear-gradient(120deg, rgba(0,0,0,0) 0, rgba(0,0,0,0) ' + Math.round(tile * .619) +
               'px, rgba(0,0,0,1) ' + Math.round(tile * .738) + 'px, rgba(0,0,0,0) ' + Math.round(tile * .857) + 'px)';
    if (dots) dots.style.backgroundSize = grid + 'px ' + grid + 'px';
    if (wave) {
      wave.style.backgroundSize = grid + 'px ' + grid + 'px';
      wave.style.webkitMaskImage = mask; wave.style.maskImage = mask;
      wave.style.webkitMaskSize = tile + 'px ' + tile + 'px'; wave.style.maskSize = tile + 'px ' + tile + 'px';
    }
    O.waveTile = tile;

    var rings = [];
    if (O.rings) {
      var RD = O.ringBoxes || [[-.082, -.229, .469], [.656, .361, .375], [.273, .653, .320]];
      RD.forEach(function (r) {
        var i = document.createElement('i'); i.className = 'mg-ring';
        i.style.left = (r[0] * O.w).toFixed(0) + 'px'; i.style.top = (r[1] * O.h).toFixed(0) + 'px';
        i.style.width = i.style.height = (r[2] * O.w).toFixed(0) + 'px';
        space.appendChild(i); rings.push(i);
      });
    }

    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'mg-orb'); svg.setAttribute('viewBox', '0 0 ' + O.w + ' ' + O.h);
    svg.innerHTML = '<circle class="mg-c"/><circle class="mg-c"/><path class="mg-pb"/><path class="mg-pl"/>';
    space.appendChild(svg);

    var glows = [0, 1, 2].map(function () {
      var b = document.createElement('i'); b.className = 'mg-glow'; space.appendChild(b); return b;
    });
    if (O.blur) g.style.setProperty('--mg-blur', 'blur(' + O.blur + 'px)');
    if (O.bg) g.style.setProperty('--mg-bg', O.bg);

    stage.insertBefore(g, stage.firstChild);
    var cs = svg.querySelectorAll('.mg-c');
    return { root: g, space: space, dots: dots, wave: wave, rings: rings, svg: svg,
             c1: cs[0], c2: cs[1], pb: svg.querySelector('.mg-pb'), pl: svg.querySelector('.mg-pl'),
             glows: glows, stage: stage };
  }

  function fit() {
    if (!EL) return;
    var r = EL.stage.getBoundingClientRect();
    if (!r.width) return;
    EL.space.style.transform = 'scale(' + (r.width / O.w) + ',' + (r.height / O.h) + ')';
  }

  /* ---------- per-mark geometry (measured once, then cached) ------- */
  function geo(m) {
    if (GEO[m.id]) return GEO[m.id];
    var f = pathFn(m.path), pts = [], i, c;
    for (i = 0; i <= 120; i++) { c = f(i / 120, m.LP, m.S); pts.push([c.x, c.y]); }
    var d = pts.map(function (q, k) { return (k ? 'L' : 'M') + q[0].toFixed(1) + ' ' + q[1].toFixed(1); }).join('');
    GEO[m.id] = { d: d, R: Math.hypot(m.S.x - m.LP.x, m.S.y - m.LP.y), fn: f, len: 0 };
    return GEO[m.id];
  }
  /* The geometry is swapped only while the rings are at opacity 0 (the
     first .5s of a beat), so a switch is never visible. */
  function setGeo(m) {
    if (curGeo === m.id) return;
    curGeo = m.id;
    var g = geo(m);
    EL.pb.setAttribute('d', g.d); EL.pl.setAttribute('d', g.d);
    g.len = EL.pl.getTotalLength ? EL.pl.getTotalLength() : 1000;   // once per mark, never per frame
    EL.c1.setAttribute('cx', m.LP.x); EL.c1.setAttribute('cy', m.LP.y); EL.c1.setAttribute('r', g.R.toFixed(1));
    EL.c2.setAttribute('cx', m.LP.x); EL.c2.setAttribute('cy', m.LP.y); EL.c2.setAttribute('r', (g.R * .62).toFixed(1));
  }

  /* which mark owns time t, and which one is fading out behind it */
  function ctx(t) {
    var cur = null, prev = null;
    for (var i = 0; i < MARKS.length; i++) {
      if (t >= MARKS[i].t0) { prev = cur; cur = MARKS[i]; }
    }
    if (!cur || t >= cur.end) return null;
    return { cur: cur, prev: prev };
  }

  /* ---------- the mark's own position (drive your element with it) -- */
  function markAt(t) {
    var o = ctx(t); if (!o) return null;
    var m = o.cur, lt = t - m.t0;
    if (lt > m.dur) return null;                                  // the beat is over; the mark has left
    var g = geo(m), pe = clamp(lt / m.flight, 0, 1), c = g.fn(pe, m.LP, m.S);
    return { x: c.x, y: c.y, size: lerp(m.size0, m.size1, ez(Math.min(1, pe * 2.5))),
             acc: m.acc, id: m.id, landed: lt >= m.flight, p: pe };
  }

  /* ---------- one frame ------------------------------------------- */
  function placeGlow(el, cx, cy, w, color, op) {
    el.style.width = el.style.height = w.toFixed(0) + 'px';
    el.style.transform = 'translate(' + (cx - w / 2).toFixed(1) + 'px,' + (cy - w / 2).toFixed(1) + 'px)';
    el.style.background = core(color);
    el.style.opacity = op.toFixed(3);
  }

  function ambient(t) {
    /* between marks: the three fields carry lead / current / lag colours */
    var F = O.fields;
    for (var i = 0; i < 3; i++) {
      var B = F[i];
      var x = B.x * O.w + B.ax * O.w * Math.sin(2 * Math.PI * t / B.px + B.ph);
      var y = B.y * O.h + B.ay * O.h * Math.cos(2 * Math.PI * t / B.py + B.ph);
      placeGlow(EL.glows[i], x, y, B.w * O.w, fieldColor(colorAt(t + B.off)), O.dark ? .8 : .6);
    }
  }

  function chapter(t, o) {
    var m = o.cur, lt = t - m.t0, inBeat = lt < m.dur;
    setGeo(m);
    EL.svg.style.display = 'block';

    /* -- rings: in over .5s, .55 while the mark flies, .30 through the
          chapter, out over the chapter's last .6s -------------------- */
    var fin = Math.min(1, lt / .5), fout = clamp((m.end - t) / .6, 0, 1);
    var ro = (inBeat ? .55 : .30) * fin * fout;
    var rs = O.dark ? 'rgba(196,181,253,' + Math.min(1, ro * 1.6).toFixed(3) + ')'
                    : 'rgba(124,58,237,' + ro.toFixed(3) + ')';
    [EL.c1, EL.c2, EL.pb].forEach(function (e) { e.setAttribute('stroke', rs); e.setAttribute('stroke-width', O.ringW); });

    /* -- the lit arc: a dasharray WINDOW .32 of the path long, ending
          at the mark; after the landing it shrinks into the landing
          point over 1s and fades out ------------------------------- */
    var g = geo(m), L = g.len || 1, pe = clamp(lt / m.flight, 0, 1);
    var head = pe * L, tail = Math.max(0, head - O.arc * L), lo = 1;
    if (lt > m.flight) { var q = Math.min(1, (lt - m.flight) / 1); tail = lerp(tail, head, q); lo = 1 - q; }
    var win = Math.max(0, head - tail);
    EL.pl.setAttribute('stroke', lift(m.acc));
    EL.pl.setAttribute('stroke-width', O.arcW);
    /* The window is ONE dash pushed along the path by a negative dashoffset.
       Do NOT write it as "0 tail win 2L": a zero-length leading dash with a
       round linecap paints a visible DOT at the start of the path. */
    EL.pl.setAttribute('stroke-dasharray', win.toFixed(1) + ' ' + (L * 2).toFixed(1));
    EL.pl.setAttribute('stroke-dashoffset', (-tail).toFixed(1));
    EL.pl.setAttribute('opacity', (win < .5 ? 0 : lo * fin).toFixed(3));

    /* -- glow 1: rides the mark, blooms at the landing, then settles
          down-left for the chapter and drifts there ----------------- */
    var cx, cy, w;
    if (inBeat && lt < m.flight) {
      var c = g.fn(pe, m.LP, m.S);
      cx = c.x; cy = c.y; w = lerp(.43 * O.w, .66 * O.w, pe);
    } else {
      var e = sstep((lt - m.flight) / .7);
      var e2 = inBeat ? 0 : sstep((t - (m.t0 + m.dur)) / 2.2);
      w = lerp(.66 * O.w, .86 * O.w, e);
      cx = lerp(m.LP.x, m.LP.x + O.settle[0] * O.w, e2) + .035 * O.w * Math.sin(2 * Math.PI * t / 43) * e;
      cy = lerp(m.LP.y, m.LP.y + O.settle[1] * O.h, e2) + .049 * O.h * Math.cos(2 * Math.PI * t / 57) * e;
    }
    placeGlow(EL.glows[0], cx, cy, w, lift(inBeat ? m.acc : mixHex(m.acc, '#ffffff', .10)), 1);

    /* -- glow 2: the PREVIOUS landing, fading over this beat + 4s --- */
    if (o.prev) {
      var p = o.prev, f = 1 - Math.min(1, lt / (m.dur + 4)), w2 = .86 * O.w;
      placeGlow(EL.glows[1],
        p.LP.x + O.settle[0] * O.w + .035 * O.w * Math.sin(2 * Math.PI * t / 43),
        p.LP.y + O.settle[1] * O.h + .049 * O.h * Math.cos(2 * Math.PI * t / 57),
        w2, lift(p.acc), f);
    } else EL.glows[1].style.opacity = '0';

    /* -- glow 3: the ambient field, away from the action ------------ */
    var B = O.fields[2], w3 = .66 * O.w;
    placeGlow(EL.glows[2],
      .78 * O.w + B.ax * O.w * Math.sin(2 * Math.PI * t / B.px + B.ph),
      .26 * O.h + B.ay * O.h * Math.cos(2 * Math.PI * t / B.py + B.ph),
      w3, O.dark ? '#6d28d9' : O.ambient, O.dark ? .6 : .7);
  }

  function update(t) {
    if (!EL) return;
    t = +t || 0;

    /* the brightness wave: only the MASK moves, the dots never do.
       One tile per period, so it repeats exactly. */
    if (EL.wave) {
      var mx = (((t / O.wavePeriod) % 1) * O.waveTile).toFixed(1) + 'px 0px';
      EL.wave.style.webkitMaskPosition = mx; EL.wave.style.maskPosition = mx;
    }
    /* ambient orbit rings: <= ~60px of travel over ~40s */
    EL.rings.forEach(function (el, i) {
      var R = O.ringDrift[i % O.ringDrift.length];
      el.style.transform = 'translate(' + (R.ax * Math.sin(2 * Math.PI * t / R.px + R.ph)).toFixed(1) + 'px,' +
                                          (R.ay * Math.cos(2 * Math.PI * t / R.py + R.ph)).toFixed(1) + 'px)';
    });

    var o = ctx(t);
    if (o) { chapter(t, o); return; }
    EL.svg.style.display = 'none';
    curGeo = null;
    ambient(t);
  }

  /* ---------- init ------------------------------------------------ */
  function init(cfg) {
    cfg = cfg || {};
    var stage = typeof cfg.stage === 'string' ? document.querySelector(cfg.stage) : cfg.stage;
    if (!stage) throw new Error('GROUND.init: no stage element');
    destroy();

    O = {};
    Object.keys(D).forEach(function (k) { O[k] = (cfg[k] !== undefined ? cfg[k] : D[k]); });
    O.dark = O.theme === 'dark';
    if (O.glowLift === null || O.glowLift === undefined) O.glowLift = O.dark ? .3 : 0;
    O.bg = cfg.bg || (O.dark ? '#07050f' : '#f7f5fd');
    O.grid = cfg.grid; O.waveTile = cfg.waveTile; O.ringBoxes = cfg.ringBoxes;
    O.settle = cfg.settle || [-.102, .299];              // where the landing glow parks, as fractions of w/h
    O.ringW = cfg.ringW || Math.max(2, Math.round(O.w / 640));
    O.arcW  = cfg.arcW  || Math.max(6, Math.round(O.w / 160));
    O.fields = cfg.fields || [
      { x: .203, y: .333, w: .586, ax: .086, ay: .104, px: 47, py: 61, ph: 0,    off: 0 },
      { x: .813, y: .361, w: .527, ax: .094, ay: .118, px: 53, py: 67, ph: 1.9,  off: 0 },
      { x: .508, y: .833, w: .625, ax: .078, ay: .139, px: 59, py: 71, ph: 3.7,  off: 0 }
    ];
    O.fields[0].off = +O.lead; O.fields[1].off = 0; O.fields[2].off = -O.lag;
    O.ringDrift = cfg.ringDrift || [
      { ax: 26, ay: 18, px: 44, py: 57, ph: .4 },
      { ax: 22, ay: 26, px: 52, py: 63, ph: 2.2 },
      { ax: 28, ay: 16, px: 61, py: 49, ph: 4.1 }
    ];
    if (O.strength >= 4) O.fields.forEach(function (f) { f.w *= 1.25; });

    TRACK = (cfg.track || []).slice().sort(function (a, b) { return a[0] - b[0]; });

    /* marks: {id:{S,LP,acc,path,t0,dur,flight,end,size0,size1}} */
    MARKS = []; GEO = {}; curGeo = null;
    var ids = Object.keys(cfg.marks || {});
    ids.forEach(function (id) {
      var m = cfg.marks[id];
      MARKS.push({
        id: id, S: m.S, LP: m.LP, acc: m.acc || '#7c3aed', path: m.path || 'zip',
        t0: +m.t0 || 0, dur: m.dur !== undefined ? +m.dur : O.dur,
        flight: m.flight !== undefined ? +m.flight : O.flight,
        end: m.end !== undefined ? +m.end : Infinity,
        size0: m.size0 !== undefined ? +m.size0 : Math.round(O.w / 58),
        size1: m.size1 !== undefined ? +m.size1 : Math.round(O.w / 10)
      });
    });
    MARKS.sort(function (a, b) { return a.t0 - b.t0; });
    MARKS.forEach(function (m, i) {                        // a chapter runs to the next mark unless told otherwise
      if (m.end === Infinity && MARKS[i + 1]) m.end = MARKS[i + 1].t0;
    });

    EL = build(stage);
    fit();
    if (typeof ResizeObserver !== 'undefined') {
      O.ro = new ResizeObserver(fit); O.ro.observe(stage);
    } else if (root.addEventListener) { root.addEventListener('resize', fit); }
    update(0);
    return API;
  }

  function destroy() {
    if (O && O.ro) O.ro.disconnect();
    if (root.removeEventListener) root.removeEventListener('resize', fit);
    if (EL && EL.root && EL.root.parentNode) EL.root.parentNode.removeChild(EL.root);
    EL = null; GEO = {}; curGeo = null;
  }

  var API = { init: init, update: update, markAt: markAt, colorAt: colorAt, fit: fit,
              destroy: destroy, paths: PATHS, mixHex: mixHex, smoothstep: sstep };
  root.GROUND = API;
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
})(typeof window !== 'undefined' ? window : this);
