/* ===================================================================
   text-motion.js — helpers for the textmotion.css building blocks.
   Every time-driven effect takes a LOGICAL time `t` (seconds) so it stays
   correct under slow-clock rendering. Call the per-frame updaters from your
   render loop / rAF tick, keyed off your own clock — never wall-clock.
   =================================================================== */

/* clamp helper */
const _cl = (x,a,b)=>Math.max(a,Math.min(b,x));

/* --- word-rise: split an element's text into .tm-word spans --------
   Preserves inline markup (a colored/gradient/keyword <span>) as one unit. */
function tmSplit(el, html){
  el.innerHTML = (html ?? el.innerHTML).trim()
    .split(/(\s+)/).map(tok => /^\s+$/.test(tok) ? tok
      : (tok.startsWith('<') ? tok : `<span class="tm-word">${tok}</span>`)).join('');
}
/* reveal words up to logical time; t0..t1 spans the whole line */
function tmReveal(el, t0, t1, t){
  const ws = el.querySelectorAll('.tm-word'); const p=_cl((t-t0)/(t1-t0),0,1);
  const n = Math.floor(p*ws.length + 1e-3);
  ws.forEach((w,i)=>w.classList.toggle('on', i<n));
}

/* --- scramble-decode: text resolves out of random glyphs -----------
   finalHTML lets you swap to markup (e.g. a colored <em>) once decoded. */
const _GLY = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/<>%#";
function tmScramble(el, plain, t0, t1, t, finalHTML){
  const p=_cl((t-t0)/(t1-t0),0,1);
  if(p>=1){ if(el.dataset.tmDone!=='1'){ el.innerHTML=finalHTML??plain; el.dataset.tmDone='1'; } return; }
  el.dataset.tmDone='0';
  const n=Math.floor(p*plain.length); let out='';
  for(let i=0;i<plain.length;i++) out += i<n ? plain[i] : (plain[i]===' '?' ':_GLY[(Math.random()*_GLY.length)|0]);
  el.textContent=out;
}

/* --- keyword sweep: fire the highlight bar + lit state at a cue ----- */
function tmSweep(el, at, t){ const on=t>=at; el.classList.toggle('sweep',on); el.classList.toggle('lit',t>=at+0.35); }

/* --- ticker-roll: <span class="tm-ticker"><span class="tm-roll">…i…</span></span>
   holdFirst = seconds the first word stays before rolling; step = per-word secs */
function tmTicker(roll, t0, t, {holdFirst=1.4, step=0.85}={}){
  const items=roll.children; const n=items.length;
  let k = t < t0+holdFirst ? 0 : Math.min(n-1, 1+Math.floor((t-t0-holdFirst)/step));
  roll.style.transform = `translateY(${-k*1.15}em)`;
  const w = roll.parentElement; if(roll.dataset.w!==String(k)){ roll.dataset.w=String(k);
    w.style.width = items[k].getBoundingClientRect().width+'px'; }
}

/* --- living gradient: apply a scene's palette (color arc) ----------
   grad = {ga,gb,b1,b2,b3}; smooth CSS transition handles the blend. */
function tmGrad(gradbgEl, grad){ const s=gradbgEl.style;
  for(const k of ['ga','gb','b1','b2','b3']) if(grad[k]) s.setProperty('--'+k, grad[k]); }
/* drift the blobs by logical time (cheap transforms, no blur) */
function tmDrift(root, t){
  const b=root.querySelectorAll('.tm-blob'); if(!b.length) return;
  if(b[0]) b[0].style.transform=`translate(${18+Math.sin(t*0.06)*10}%, ${6+Math.cos(t*0.05)*7}%)`;
  if(b[1]) b[1].style.transform=`translate(${52+Math.cos(t*0.045)*11}%, ${40+Math.sin(t*0.055)*8}%)`;
  if(b[2]) b[2].style.transform=`translate(${34+Math.sin(t*0.035+2)*13}%, ${18+Math.cos(t*0.04+1)*9}%)`;
}

/* --- concentric ripple rings: build N rings sized to the frame ----- */
function tmRings(host, n=4, maxPct=180){ host.innerHTML='';
  for(let i=0;i<n;i++){ const r=document.createElement('i');
    r.style.width=r.style.height=maxPct+'%'; r.style.animationDelay=(i/n*6)+'s'; host.appendChild(r); } }

/* --- oversized demo cursor path: pts=[[t,xPct,yPct,click?],…] ------ */
function tmCursor(el, pts, t){
  let cur=null; for(const p of pts) if(t>=p[0]) cur=p;
  if(!cur){ el.style.opacity=0; return; }
  el.style.opacity=1; el.style.left=cur[1]+'%'; el.style.top=cur[2]+'%';
}

/* --- keyword punch (scale-pop) ------------------------------------- */
function tmPunch(el, at, t){ el.classList.toggle('pop', t>=at); }

/* ===================================================================
   THE PLATTER — helpers for the added recipes (see PLATTER.md).
   All time-driven; pass LOGICAL time t. No filter:blur anywhere.
   =================================================================== */

/* A7 · Motion-Blur Slide — reveal .tm-blurin words up to time (like tmReveal) */
function tmBlurIn(el, t0, t1, t){ const ws=el.querySelectorAll('.tm-blurin');
  const p=_cl((t-t0)/(t1-t0),0,1), n=Math.floor(p*ws.length+1e-3);
  ws.forEach((w,i)=>w.classList.toggle('on', i<n)); }

/* B2 · Mesh Wash — glide the soft light-sweep across the frame by logical time */
function tmMesh(el, t){ if(!el) return;
  el.style.transform=`translate(${Math.sin(t*0.08)*12}%, ${Math.cos(t*0.06)*8}%) rotate(${Math.sin(t*0.03)*6}deg)`; }

/* B5 · Neon Path Travellers — move dot(s) along an SVG <path>; pts=[{el,speed,off}] */
function tmTravel(pathEl, dots, t){ if(!pathEl||!pathEl.getTotalLength) return;
  const L=pathEl.getTotalLength();
  dots.forEach(d=>{ const u=((t*(d.speed||0.12)+(d.off||0))%1+1)%1; const pt=pathEl.getPointAtLength(u*L);
    d.el.setAttribute('cx',pt.x); d.el.setAttribute('cy',pt.y); }); }

/* C2 · Floating Rings (Bokeh) — build N rings at varied size/depth, then drift */
function tmBokeh(host, specs){ host.innerHTML='';
  specs.forEach(s=>{ const i=document.createElement('i'); if(s.soft)i.className='soft';
    i.style.width=i.style.height=s.d+'%'; i.dataset.x=s.x; i.dataset.y=s.y; i.dataset.sp=s.sp||0.04;
    host.appendChild(i); }); }
function tmBokehDrift(host, t){ host.querySelectorAll('i').forEach((i,k)=>{ const sp=+i.dataset.sp;
  i.style.transform=`translate(${(+i.dataset.x)+Math.sin(t*sp+k)*6}%, ${(+i.dataset.y)+Math.cos(t*sp*0.9+k)*7}%)`; }); }

/* C3 · Orb Bloom — fire the small-ring→big-glow bloom at a cue */
function tmOrb(el, at, t){ if(!el) return; el.classList.toggle('bloom', t>=at); }

/* C4 · Converge — pull scattered nodes toward a focal point over t0..t1.
   nodes=[{el,fromX,fromY,toX,toY}] in %; sets transform each frame. */
function tmConverge(nodes, t0, t1, t){ const p=_cl((t-t0)/(t1-t0),0,1), e=p<.5?2*p*p:1-Math.pow(-2*p+2,2)/2;
  nodes.forEach(n=>{ const x=n.fromX+(n.toX-n.fromX)*e, y=n.fromY+(n.toY-n.fromY)*e;
    n.el.style.transform=`translate(${x}%, ${y}%)`; }); }

/* C5 · Metaball Merge — fire the two-circles-fuse bridge at a cue */
function tmMeta(el, at, t){ if(!el) return; el.classList.toggle('merged', t>=at); }

/* D4 · Glass Card Float — gentle parallax tilt by logical time */
function tmFloat(el, t, amp=6){ if(!el) return;
  el.style.transform=`perspective(1400px) rotateX(${Math.sin(t*0.5)*amp*0.4}deg) rotateY(${Math.cos(t*0.4)*amp}deg) translateY(${Math.sin(t*0.6)*1.5}%)`; }

/* E1/E2 · Integrations Orbit — place icons on a ring (or scatter), reveal + spokes.
   icons=[{el,spokeEl}]; radiusPct; reveal staggered from t0. scatter=jitter for constellation. */
function tmOrbit(icons, cx, cy, radius, t0, t, {scatter=0, step=0.12}={}){
  const n=icons.length;
  icons.forEach((ic,k)=>{ const ang=(k/n)*Math.PI*2 - Math.PI/2;
    const jit = scatter ? (Math.sin(k*12.9)*scatter) : 0;
    const r = radius + jit;
    const x = cx + Math.cos(ang)*r, y = cy + Math.sin(ang)*r*1.0;
    ic.el.style.left=x+'%'; ic.el.style.top=y+'%'; ic.el.style.transform='translate(-50%,-50%)';
    const on = t >= t0 + k*step; ic.el.classList.toggle('on', on);
    if(ic.spokeEl){ ic.spokeEl.style.width=r+'%';
      ic.spokeEl.style.transform=`rotate(${ang}rad)`; ic.spokeEl.classList.toggle('on', on); }
  }); }

/* G3 · Counter-Tick — roll a number up to its value over t0..t1 (odometer) */
function tmCount(el, to, t0, t1, t, {prefix='',suffix='',decimals=0}={}){ if(!el) return;
  const p=_cl((t-t0)/(t1-t0),0,1), e=1-Math.pow(1-p,3); const val=to*e;
  el.textContent = prefix + val.toLocaleString(undefined,{minimumFractionDigits:decimals,maximumFractionDigits:decimals}) + suffix; }

/* G2/C8 · Line-Draw — measure a path's length into --len, then toggle .drawn at a cue */
function tmDrawInit(svgEl){ svgEl.querySelectorAll('path,line,polyline').forEach(p=>{
  try{ p.style.setProperty('--len', Math.ceil(p.getTotalLength?p.getTotalLength():1000)); }catch(e){} }); }
function tmDraw(svgEl, at, t){ if(!svgEl) return; svgEl.classList.toggle('drawn', t>=at); }

/* B6 · Starfield — build N twinkling stars (deterministic; no Math.random for capture stability) */
function tmStars(host, n){ host.innerHTML='';
  for(let i=0;i<n;i++){ const s=document.createElement('i');
    const x=(Math.sin(i*12.9898)*43758.5453)%1, y=(Math.sin(i*78.233)*12543.123)%1;
    s.style.left=(Math.abs(x)*100).toFixed(2)+'%'; s.style.top=(Math.abs(y)*100).toFixed(2)+'%';
    s.style.animationDuration='calc('+(2+Math.abs(x)*4).toFixed(2)+'s * var(--R))';
    host.appendChild(s); } }

/* G8 · Timeline Scrubber — slide the playhead across a [t0..t1] window to fraction 0..1 */
function tmScrub(headEl, t0, t1, t){ if(!headEl) return; headEl.style.left=(_cl((t-t0)/(t1-t0),0,1)*100)+'%'; }

/* ===================================================================
   A″ · SPARK-DRIVEN TEXT (Sep 2026, from the walkthrough-film build)
   A typewriter whose cursor is the mark travelling through the frame,
   a highlighter pill on the payoff word, and ghost echoes. Every
   updater is a pure function of logical time `t` — call per frame.
   Classes live in textmotion.css (.tm-type / .tm-tw / .tm-tl /
   .tm-pay / .tm-pw / .tm-echo / .tm-gz).
   =================================================================== */
const _esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');
const _gz  = t => [-2,-1,1,2].map(g=>`<i class="tm-gz" data-g="${g}">${_esc(t)}</i>`).join('');

/* A17/A18 · build a typewriter line ONCE, in its final layout.
   words: ['One','line.'] or [{w:'One',at:0.4},…] (at = VO time, line-local)
   o.pay:[i0,i1] the payoff run that gets the pill · o.echo: add ghost echoes
   o.step: seconds per letter (default min(.035, 1.1/chars) — the whole line
   is capped at 1.1s however long it is). */
function tmTypeBuild(el, words, o){
  o = o || {};
  const W = words.map(w => typeof w==='string' ? {w} : w);
  const n = W.length, pay = o.pay || null;
  const chars = W.reduce((a,w)=>a+w.w.length,0);
  const step = o.step || Math.min(0.035, 1.1/Math.max(1,chars));
  let at = 0, html = '';
  for(let i=0;i<n;i++){
    const last = i===n-1;
    if(pay && i===pay[0]) html += `<span class="tm-pay${pay[1]===n-1?' tm-last':''}"><i class="tm-pw"></i>`;
    const t0 = W[i].at!==undefined ? +W[i].at : at;
    html += `<span class="tm-tw${last?' tm-last':''}" data-i="${i}" data-at="${t0}">`
          + [...W[i].w].map((c,j)=>`<i class="tm-tl" data-t="${(t0+j*step).toFixed(4)}">${_esc(c)}</i>`).join('')
          + '</span>';
    at = t0 + W[i].w.length*step;
    if(pay && i===pay[1]) html += (o.echo ? _gz(W.slice(pay[0],pay[1]+1).map(w=>w.w).join(' ')) : '') + '</span>';
  }
  el.classList.add('tm-type'); if(o.echo) el.classList.add('tm-echo');
  el.innerHTML = html; el.dataset.tmStep = step.toFixed(5);
  el.dataset.tmPay = pay ? pay.join(',') : ''; delete el.__tmc;
  return el;
}

/* A17 · one frame of the typed line. Letter i of a word appears at its
   word's `at` + i*step and eases from +.18em of tracking to none over
   .25s. The tracking is carried on TRANSFORMS (an accumulator, letter by
   letter), so the line never reflows and never re-wraps while typing. */
function tmType(el, t, o){
  o = o || {}; const t0 = o.t0 || 0, lt = t - t0;
  const step = +el.dataset.tmStep || 0.035;
  const trk = o.track!==undefined ? o.track : 0.18, set = o.settle || 0.25;
  let acc = 0, pStart = 1e9, pEnd = 0;
  const pay = (el.dataset.tmPay||'').split(',').map(Number);
  el.querySelectorAll('.tm-tw').forEach(sp=>{
    const at = +sp.dataset.at, i = +sp.dataset.i, a0 = acc, L = sp.children;
    sp.style.transform = `translateX(${a0.toFixed(4)}em)`;
    for(let j=0;j<L.length;j++){
      const ta = at + j*step;
      L[j].style.opacity = _cl((lt-ta)/0.09,0,1).toFixed(3);
      L[j].style.transform = `translateX(${(acc-a0).toFixed(4)}em)`;
      acc += trk * (1 - (1-Math.pow(1-_cl((lt-ta)/set,0,1),3)));
      if(el.dataset.tmPay && i===pay[0] && j===0) pStart = ta;
      if(el.dataset.tmPay && i===pay[1]) pEnd = ta;
    }
  });
  /* A18 pill wipe (from the payoff's FIRST letter) + A20 tilt-settle
     (from its LAST letter) + A19 echoes once the run has landed */
  const w = el.querySelector('.tm-pay'); if(!w) return el;
  const e = p => 1-Math.pow(1-_cl(p,0,1),3);
  const pw = w.querySelector('.tm-pw');
  if(pw) pw.style.setProperty('--wipe', (100*(1-e((lt-pStart)/(o.wipe||0.3)))).toFixed(2)+'%');
  w.style.transform = `rotate(${((o.deg||6)*(1-e((lt-pEnd)/(o.tilt||0.35)))).toFixed(3)}deg)`;
  if(el.classList.contains('tm-echo')) tmEcho(w, (lt-pEnd)/0.6);
  return el;
}

/* the settled end-state (a line that has finished and is now just sitting there) */
function tmTypeSettle(el){
  el.querySelectorAll('.tm-tw').forEach(sp=>{ sp.style.transform='';
    [...sp.children].forEach(L=>{ L.style.opacity=1; L.style.transform=''; }); });
  const w = el.querySelector('.tm-pay'); if(!w) return el;
  w.style.transform=''; const pw=w.querySelector('.tm-pw'); if(pw) pw.style.setProperty('--wipe','0%');
  w.querySelectorAll('.tm-gz').forEach(g=>{ g.style.opacity=0; });
  return el;
}

/* A″ · MARK AS CURSOR — where the typing edge is right now, so your
   travelling element can sit at it. Returns {x,y} in px relative to
   `o.space` (default el.offsetParent). Letter boxes are measured ONCE
   in the final layout and cached, so this is free per frame.
   Inside the payoff run the "end of the text" is the PILL's own wiping
   edge, so the mark never sits on top of the pill. */
function tmTypeCursor(el, t, o){
  o = o || {}; const t0 = o.t0 || 0, lt = t - t0, gap = o.gap!==undefined ? o.gap : 24;
  const space = o.space || el.offsetParent || document.body;
  let M = el.__tmc;
  if(!M){
    const sr = space.getBoundingClientRect();
    const ls = [...el.querySelectorAll('.tm-tl')].map(L=>{ const r=L.getBoundingClientRect();
      return {right:r.right-sr.left, at:+L.dataset.t}; });
    if(!ls.length || !ls[ls.length-1].right) return null;          // not laid out yet — retry next frame
    const er = el.getBoundingClientRect(), w = el.querySelector('.tm-pay');
    const pw = w ? w.querySelector('.tm-pw') : null, pr = pw ? pw.getBoundingClientRect() : null;
    M = el.__tmc = {ls, left:er.left-sr.left, cy:er.top-sr.top+er.height/2,
      pillL: pr?pr.left-sr.left:0, pillR: pr?pr.right-sr.left:0,
      payAt: w ? +w.querySelector('.tm-tw').dataset.at : null};
  }
  const step = +el.dataset.tmStep || 0.035, N = M.ls.length;
  /* the edge walks CONTINUOUSLY between letter boxes, so the ride is smooth
     instead of snapping one letter-width at a time */
  let k = 0; while(k < N && lt >= M.ls[k].at) k++;
  const r0 = k<=0 ? M.left : M.ls[k-1].right, r1 = M.ls[Math.min(N-1,k)].right;
  const prevAt = k<=0 ? M.ls[0].at - step : M.ls[k-1].at;
  const fr = _cl((lt - prevAt)/step, 0, 1);
  let right = k>=N ? M.ls[N-1].right : r0 + (r1-r0)*fr;
  if(M.payAt!==null && M.pillR && lt >= M.payAt){
    const e = 1-Math.pow(1-_cl((lt-M.payAt)/(o.wipe||0.3),0,1),3);
    right = Math.max(right, M.pillL + (M.pillR-M.pillL)*e);
  }
  return {x: right + gap, y: M.cy};
}

/* A19 · GHOST ECHOES — 2 faint copies above and 2 below that slide
   outward and fade over the .6s after the word lands. `span` (px)
   overrides the 1.05em spacing for a wrapped label. */
function tmEchoInto(el, text){ el.classList.add('tm-echo');
  el.insertAdjacentHTML('beforeend', _gz(text ?? el.textContent)); return el; }
function tmEcho(el, p, span){ if(!el) return;
  const e = 1-Math.pow(1-_cl(p,0,1),3);
  el.querySelectorAll('.tm-gz').forEach(g=>{
    const d = +g.dataset.g, s = d<0?-1:1, n = Math.abs(d);
    const base = span!=null ? (d*span).toFixed(1)+'px' : (d*1.05).toFixed(2)+'em';
    g.style.opacity = (p<=0 ? 0 : (n===1?0.10:0.06)*(1-e)).toFixed(3);
    g.style.transform = `translateY(calc(${base} + ${(s*40*e).toFixed(1)}px))`;
  }); }

if (typeof module!=='undefined') module.exports = {
  tmSplit,tmReveal,tmScramble,tmSweep,tmTicker,tmGrad,tmDrift,tmRings,tmCursor,tmPunch,
  tmBlurIn,tmMesh,tmTravel,tmBokeh,tmBokehDrift,tmOrb,tmConverge,tmMeta,tmFloat,tmOrbit,
  tmCount,tmDrawInit,tmDraw,tmStars,tmScrub,
  tmTypeBuild,tmType,tmTypeSettle,tmTypeCursor,tmEchoInto,tmEcho };
