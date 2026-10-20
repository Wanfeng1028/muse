/* mark.js — TRAVELLING MARK (drop-in, dependency-free, pure functions of time).
   window.MARK = { ENTER, EXIT, pathAt, place, cursorRide, breath, orbitRound, defaults }
   Every helper takes the scene-local time (or a 0..1 progress) and returns a pose {x, y, s, tr, clip, pageOpacity, pageScale};
   your frame loop writes the pose to the DOM with MARK.place(el, pose). Nothing here keeps state or uses timers. */
(function () {
  var clamp = function (v, a, b) { return v < a ? a : v > b ? b : v; };
  var lerp = function (a, b, p) { return a + (b - a) * p; };
  var seg = function (t, a, b) { return clamp((t - a) / (b - a), 0, 1); };
  var ez = function (p) { return p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2; };   // ease in-out cubic
  var eo = function (p) { return 1 - Math.pow(1 - p, 3); };                                    // ease out cubic
  var eb = function (p) { var c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(p - 1, 3) + c1 * Math.pow(p - 1, 2); }; // back out

  var D = { T_IN: .7, S_LAND: 250, EXIT_DUR: .7, T_RIDE: .27, T_BACK: .35, CUR_SIZE: 180, CUR_ARC: 240, CUR_GAP: 24, BREATH_HZ: 3.2, BREATH_AMP: .02 };

  /* ---- entrance paths: p in [0,1], L = landing point, S = start (the previous logo's centre) ---- */
  var ENTER = {
    zip: function (p, L, S) { return { x: lerp(S.x, L.x, eo(p)), y: lerp(S.y, L.y, eo(p)) - Math.sin(p * Math.PI) * 260 }; },
    drop: function (p, L, S) {
      if (p < .3) { var q = ez(p / .3); return { x: lerp(S.x, L.x, q), y: lerp(S.y, -300, q) }; }
      var u = (p - .3) / .7, y;
      if (u < .5) { var a = u / .5; y = lerp(-300, L.y, a * a); }
      else if (u < .8) { var b = (u - .5) / .3; y = L.y - Math.sin(b * Math.PI) * 240; }
      else { var c = (u - .8) / .2; y = L.y - Math.sin(c * Math.PI) * 70; }
      return { x: L.x, y: y };
    },
    spiral: function (p, L, S) {
      var th = lerp(Math.PI * 1.1, Math.PI * 3.6, p), r = lerp(Math.hypot(S.x - L.x, S.y - L.y), 0, eo(p)), k = ez(Math.min(1, p * 3));
      var sx = L.x + Math.cos(th) * r, sy = L.y + Math.sin(th) * r * .6;
      return { x: lerp(S.x, sx, k), y: lerp(S.y, sy, k) };
    },
    hops: function (p, L, S) { var hop = Math.abs(Math.sin(p * Math.PI * 3)) * lerp(340, 90, p); return { x: lerp(S.x, L.x, p), y: lerp(S.y, L.y, p) - hop }; },
    orbit: function (p, L, S) {
      var th = lerp(Math.PI * .9, Math.PI * 2.55, eo(p)), r = lerp(Math.hypot(S.x - L.x, S.y - L.y), 0, ez(p)), k = ez(Math.min(1, p * 4));
      var ox = L.x + Math.cos(th) * r, oy = L.y + Math.sin(th) * r * .5;
      return { x: lerp(S.x, ox, k), y: lerp(S.y, oy, k) };
    }
  };
  function pathAt(kind, p, L, S) { var f = typeof kind === 'function' ? kind : (ENTER[kind] || ENTER.zip); return f(clamp(p, 0, 1), L, S); }

  /* ---- the flight into a title: lt = scene-local seconds. Returns the pose up to (and holding at) the landing. ---- */
  function flight(kind, lt, L, S, o) {
    o = o || {}; var T_IN = o.T_IN || D.T_IN, land = o.S_LAND || D.S_LAND;
    var pe = seg(lt, 0, T_IN), c = pathAt(kind, pe, L, S);
    return { x: c.x, y: c.y, s: lerp(S.s || 44, land, ez(Math.min(1, pe * 2.5))), tr: '' };
  }

  /* ---- the hold breath: uniform scale, phase 0 at t0, amplitude dies over the last .5 s before the cut ---- */
  function breath(lt, t0, dur, o) {
    o = o || {}; if (lt < t0) return 1;
    var amp = (o.amp || D.BREATH_AMP) * (1 - ez(seg(lt, dur - .6, dur - .1)));
    return 1 + Math.sin((lt - t0) * (o.hz || D.BREATH_HZ)) * amp;
  }

  /* ---- cursor ride: after landing the mark hops to the end of the typed line, rides it, and hops back.
       rightEdge(lt) -> x of the right edge of the last visible letter (continuous); cy = the line's centre y;
       TE = time typing ends. Returns {x,y,s} or null when the mark is simply on L. ---- */
  function cursorRide(lt, L, cy, rightEdge, TE, o) {
    o = o || {}; var T_IN = o.T_IN || D.T_IN, land = o.S_LAND || D.S_LAND, cs = o.CUR_SIZE || D.CUR_SIZE, arc = o.CUR_ARC || D.CUR_ARC, gap = o.CUR_GAP || D.CUR_GAP;
    var TR = TE + (o.T_BACK || D.T_BACK); if (lt <= T_IN || lt >= TR) return null;
    var cur = function (t) { return { x: rightEdge(t) + gap + cs / 2, y: cy }; };
    if (lt <= TE) { var cu = cur(lt), q = eo(seg(lt, T_IN, T_IN + (o.T_RIDE || D.T_RIDE))); return { x: lerp(L.x, cu.x, q), y: lerp(L.y, cu.y, q) - Math.sin(q * Math.PI) * arc, s: lerp(land, cs, q) }; }
    var e = cur(TE), q2 = ez(seg(lt, TE, TR)); return { x: lerp(e.x, L.x, q2), y: lerp(e.y, L.y, q2) - Math.sin(q2 * Math.PI) * arc, s: lerp(cs, land, q2) };
  }

  /* ---- exits: px = lt / EXIT_DUR (the chapter's first .7 s), from L (landing) to G (the next page's logo centre, with G.s = its size).
       Returns {x,y,s,tr,clip,pageOpacity,pageScale}; clip is a CSS clip-path for the dashboard, or 'none'. ---- */
  var EXIT = {
    inflate: function (px, L, G, o) {
      var land = (o && o.S_LAND) || D.S_LAND, g = ez(seg(px, 0, .42)), h = ez(seg(px, .48, 1));
      var s = h > 0 ? lerp(6400, G.s, h) : lerp(land, 6400, g);
      var c = h > 0 ? { x: lerp(L.x, G.x, h), y: lerp(L.y, G.y, h) } : L;
      return { x: c.x, y: c.y, s: s, tr: '', clip: h > 0 ? 'none' : 'inset(0 100% 0 0)', pageOpacity: 1, pageScale: 1 };
    },
    roll: function (px, L, G, o) {
      var land = (o && o.S_LAND) || D.S_LAND, q = ez(px);
      return { x: lerp(L.x, G.x, q), y: lerp(L.y, G.y, q) - Math.abs(Math.sin(q * Math.PI * 1.5)) * 220 * (1 - q * .5), s: lerp(land, G.s, q),
        tr: 'rotate(' + (-q * 540).toFixed(1) + 'deg)', clip: 'circle(' + lerp(60, 3400, eo(seg(px, 0, .9))).toFixed(0) + 'px at ' + G.x.toFixed(0) + 'px ' + G.y.toFixed(0) + 'px)', pageOpacity: 1, pageScale: 1 };
    },
    dive: function (px, L, G, o) {
      var land = (o && o.S_LAND) || D.S_LAND, q = ez(px);
      return { x: lerp(L.x, G.x, q), y: lerp(L.y, G.y, q) - Math.sin(q * Math.PI) * 380, s: lerp(land, G.s, q), tr: '', clip: 'none',
        pageOpacity: eo(seg(px, .1, .8)), pageScale: lerp(.94, 1, eo(seg(px, .1, .85))) };
    }
  };

  /* ---- the opening round: one clockwise orbit on a drifting, shrinking ellipse into the sidebar glyph centre G, arc-length parametrised ---- */
  var OTH0 = -80 * Math.PI / 180, OTH1 = 230 * Math.PI / 180, OC0 = { x: 1280, y: 660 }, OR0 = { x: 1120, y: 360 }, OR1 = { x: 260, y: 110 };
  function orbitPt(e, G) { var w = e * e * e, th = lerp(OTH0, OTH1, e), rx = lerp(OR0.x, OR1.x, w), ry = lerp(OR0.y, OR1.y, w);
    var cx = lerp(OC0.x, G.x - OR1.x * Math.cos(OTH1), w), cy = lerp(OC0.y, G.y - OR1.y * Math.sin(OTH1), w); return { x: cx + rx * Math.cos(th), y: cy + ry * Math.sin(th) }; }
  function orbitArcE(u, G) { var N = 120, cum = [0], p = orbitPt(0, G); for (var i = 1; i <= N; i++) { var q = orbitPt(i / N, G); cum[i] = cum[i - 1] + Math.hypot(q.x - p.x, q.y - p.y); p = q; }
    var tg = u * cum[N], j = 1; while (j < N && cum[j] < tg) j++; var f = (tg - cum[j - 1]) / Math.max(1e-9, cum[j] - cum[j - 1]); return (j - 1 + f) / N; }
  function orbitRound(u, G) { return orbitPt(orbitArcE(clamp(u, 0, 1), G), G); }

  /* ---- writing a pose: the container is placed square, the transform (uniform scale / rotation) goes on an inner wrapper, the image is never touched ---- */
  function place(el, pose, inner) {
    el.style.left = (pose.x - pose.s / 2).toFixed(1) + 'px'; el.style.top = (pose.y - pose.s / 2).toFixed(1) + 'px';
    el.style.width = el.style.height = pose.s.toFixed(1) + 'px'; if (pose.o != null) el.style.opacity = pose.o;
    if (inner) inner.style.transform = pose.tr || '';
  }
  /* measure a logo rect -> {x,y,s} (centre + size): the start of every flight, the target of every exit */
  function centreOf(el) { var r = el.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2, s: r.width || 44 }; }

  window.MARK = { defaults: D, ENTER: ENTER, EXIT: EXIT, pathAt: pathAt, flight: flight, breath: breath, cursorRide: cursorRide, orbitRound: orbitRound, place: place, centreOf: centreOf, ease: { ez: ez, eo: eo, eb: eb, seg: seg, lerp: lerp } };
})();
